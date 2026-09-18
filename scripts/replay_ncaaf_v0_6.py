from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.project_ncaaf_from_apex as production  # noqa: E402
from scripts.ncaaf_replay_snapshot import (  # noqa: E402
    load_ratings_snapshot,
    parse_timestamp,
    sha256_file,
)


MODEL_VERSION = "NCAAF v0.6 frozen production logic"
HOLDOUT_SEASON = 2025
DEVELOPMENT_SEASONS = {2022, 2023, 2024}

GAME_FIELDS = {
    "event_id",
    "season",
    "week",
    "kickoff",
    "home_team",
    "away_team",
    "provider",
    "home_spread",
    "home_spread_price",
    "away_spread_price",
    "opening_home_spread",
    "home_score",
    "away_score",
    "line_source",
}

ELIGIBILITY_FIELDS = {
    "season",
    "display_team",
    "model_team",
    "classification",
    "source",
    "source_url",
    "notes",
}

OUTPUT_FIELDS = [
    "event_id",
    "season",
    "week",
    "kickoff",
    "home_team",
    "away_team",
    "selected_team",
    "selected_side",
    "provider",
    "line_source",
    "historical_market_line",
    "market_price",
    "price_available",
    "opening_market_line",
    "model_line",
    "projected_selected_margin",
    "edge_points",
    "recommendation",
    "actionability",
    "confidence_score",
    "model_suggested_units",
    "signal_source",
    "home_score",
    "away_score",
    "actual_selected_side_margin",
    "signed_forecast_error",
    "absolute_forecast_error",
    "market_absolute_error",
    "ats_result",
    "ratings_season",
    "ratings_target_week",
    "ratings_source",
    "ratings_source_label",
    "ratings_source_url",
    "ratings_published_at",
    "ratings_safe_after",
    "ratings_sha256",
    "replay_as_of",
    "model_version",
    "production_code_sha256",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Leakage-controlled, replay-only historical runner for "
            "frozen NCAAF v0.6 production logic."
        )
    )
    parser.add_argument("--ratings", required=True, type=Path)
    parser.add_argument("--games-lines", required=True, type=Path)
    parser.add_argument("--eligibility", required=True, type=Path)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--week", required=True, type=int)
    parser.add_argument("--replay-as-of", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=("development", "holdout", "forward"),
        default="development",
    )
    parser.add_argument(
        "--unlock-holdout",
        type=int,
        help=(
            "Required explicit season token for holdout mode. "
            "For the reserved holdout use --unlock-holdout 2025."
        ),
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate inputs and isolation rules without writing replay artifacts.",
    )
    return parser.parse_args()


def enforce_holdout_policy(args):
    if args.mode == "development":
        if args.season not in DEVELOPMENT_SEASONS:
            raise RuntimeError(
                "Development mode is restricted to 2022-2024. "
                "2025 remains the untouched historical holdout."
            )
        if args.unlock_holdout is not None:
            raise RuntimeError(
                "--unlock-holdout is not valid in development mode."
            )

    elif args.mode == "holdout":
        if args.season != HOLDOUT_SEASON:
            raise RuntimeError(
                "Holdout mode is reserved for season 2025."
            )
        if args.unlock_holdout != HOLDOUT_SEASON:
            raise RuntimeError(
                "2025 holdout is locked. Explicitly supply "
                "--mode holdout --unlock-holdout 2025 only after "
                "Model Engineering freezes the candidate."
            )

    elif args.mode == "forward":
        if args.season < 2026:
            raise RuntimeError(
                "Forward mode is reserved for 2026 and later."
            )
        if args.unlock_holdout is not None:
            raise RuntimeError(
                "--unlock-holdout is not valid in forward mode."
            )


def get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _optional_float(value):
    text = str(value or "").strip()
    return None if not text else float(text)


def _optional_int(value):
    text = str(value or "").strip()
    return None if not text else int(float(text))


def load_historical_games(
    path: Path,
    season: int,
    week: int,
    provider: str,
):
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        missing = GAME_FIELDS - set(reader.fieldnames or [])

        if missing:
            raise RuntimeError(
                f"Historical game/line CSV missing fields: "
                f"{sorted(missing)}"
            )

        raw_rows = list(reader)

    games = []
    seen_ids = set()

    for row in raw_rows:
        try:
            row_season = int(row["season"])
            row_week = int(row["week"])
        except ValueError as error:
            raise RuntimeError(
                f"Invalid season/week row: {row}"
            ) from error

        if (
            row_season != season
            or row_week != week
            or row["provider"].strip() != provider
        ):
            continue

        event_id = row["event_id"].strip()

        if not event_id:
            raise RuntimeError("Historical game row has blank event_id.")

        if event_id in seen_ids:
            raise RuntimeError(
                f"Duplicate event_id/provider row: {event_id}"
            )

        seen_ids.add(event_id)

        kickoff = parse_timestamp(
            row["kickoff"],
            f"kickoff for {event_id}",
        )

        home_team = row["home_team"].strip()
        away_team = row["away_team"].strip()

        if not home_team or not away_team:
            raise RuntimeError(
                f"Missing team identity for {event_id}"
            )

        games.append(
            {
                "event_id": event_id,
                "season": row_season,
                "week": row_week,
                "kickoff": kickoff,
                "kickoff_text": row["kickoff"].strip(),
                "home_team": home_team,
                "away_team": away_team,
                "provider": row["provider"].strip(),
                "home_spread": float(row["home_spread"]),
                "home_spread_price": _optional_int(
                    row["home_spread_price"]
                ),
                "away_spread_price": _optional_int(
                    row["away_spread_price"]
                ),
                "opening_home_spread": _optional_float(
                    row["opening_home_spread"]
                ),
                "home_score": _optional_int(row["home_score"]),
                "away_score": _optional_int(row["away_score"]),
                "line_source": row["line_source"].strip(),
            }
        )

    games.sort(
        key=lambda game: (
            game["kickoff"],
            game["event_id"],
        )
    )

    if not games:
        raise RuntimeError(
            f"No historical rows found for season={season}, "
            f"week={week}, provider={provider}."
        )

    return games


def load_season_eligibility(path: Path, season: int):
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        missing = ELIGIBILITY_FIELDS - set(
            reader.fieldnames or []
        )

        if missing:
            raise RuntimeError(
                f"Eligibility CSV missing fields: {sorted(missing)}"
            )

        rows = list(reader)

    mapping = {}
    fcs_names = set()

    for row in rows:
        if int(row["season"]) != season:
            continue

        display_team = row["display_team"].strip()
        model_team = row["model_team"].strip()
        classification = (
            row["classification"].strip().lower()
        )

        if not display_team or not model_team:
            raise RuntimeError(
                "Eligibility rows require display_team and model_team."
            )

        if classification not in {"fbs", "fcs"}:
            raise RuntimeError(
                f"Eligibility classification for {display_team} "
                f"must be fbs or fcs, got {classification!r}."
            )

        if display_team in mapping:
            raise RuntimeError(
                f"Duplicate eligibility row for {season} {display_team}"
            )

        mapping[display_team] = {
            "cfbd_team": model_team,
            "classification": classification,
            "_source": row["source"].strip(),
            "_source_url": row["source_url"].strip(),
            "_notes": row["notes"].strip(),
        }

        if classification == "fcs":
            fcs_names.add(display_team)
            fcs_names.add(model_team)

    if not mapping:
        raise RuntimeError(
            f"No season-aware eligibility rows for {season}."
        )

    return mapping, fcs_names


def validate_game_eligibility(game, mapping, ratings):
    reasons = []

    for side in ("home", "away"):
        display = game[f"{side}_team"]
        info = mapping.get(display)

        if info is None:
            reasons.append(
                f"missing_{side}_season_eligibility"
            )
            continue

        if info["classification"] != "fbs":
            reasons.append(
                f"{side}_classified_{info['classification']}"
            )
            continue

        model_team = info["cfbd_team"]

        if model_team not in ratings:
            reasons.append(
                f"missing_{side}_rating"
            )

    return reasons


def event_rows_for_production(game):
    home_price = (
        game["home_spread_price"]
        if game["home_spread_price"] is not None
        else -110
    )
    away_price = (
        game["away_spread_price"]
        if game["away_spread_price"] is not None
        else -110
    )

    common = {
        "external_id": game["event_id"],
        "away_team": game["away_team"],
        "home_team": game["home_team"],
        "commence_time": game["kickoff_text"],
        "sportsbook": game["provider"],
    }

    return [
        {
            **common,
            "selection": game["home_team"],
            "line": game["home_spread"],
            "price": home_price,
        },
        {
            **common,
            "selection": game["away_team"],
            "line": -game["home_spread"],
            "price": away_price,
        },
    ]


@contextmanager
def frozen_production_context(
    replay_as_of: datetime,
    season_fcs_names: set[str],
):
    original_datetime = production.datetime
    sentinel = object()
    original_fcs = getattr(
        production,
        "FCS_TEAMS",
        sentinel,
    )

    class ReplayDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return replay_as_of.replace(tzinfo=None)
            return replay_as_of.astimezone(tz)

    production.datetime = ReplayDateTime

    if original_fcs is not sentinel:
        production.FCS_TEAMS = set(season_fcs_names)

    try:
        yield
    finally:
        production.datetime = original_datetime

        if original_fcs is not sentinel:
            production.FCS_TEAMS = original_fcs


def derive_actionability(edge: dict) -> str:
    units = float(edge["recommended_units"] or 0.0)

    if units > 0:
        return "Model Play"

    signal = str(edge.get("signal_source", "")).lower()

    hard_guards = (
        "extreme edge no-bet guard",
        "fcs no-bet guard",
        "future game review",
    )

    if any(term in signal for term in hard_guards):
        return "Guarded"

    if edge["recommendation"] in {"Value", "Lean", "Watch"}:
        return "Review Only"

    return "No Play"


def result_metrics(
    selected_side: str,
    model_line: float,
    market_line: float,
    home_score,
    away_score,
):
    if home_score is None or away_score is None:
        return {
            "actual_selected_side_margin": "",
            "signed_forecast_error": "",
            "absolute_forecast_error": "",
            "market_absolute_error": "",
            "ats_result": "",
        }

    if selected_side == "home":
        actual_margin = home_score - away_score
    else:
        actual_margin = away_score - home_score

    projected_margin = -float(model_line)
    market_implied_margin = -float(market_line)

    signed_error = actual_margin - projected_margin
    absolute_error = abs(signed_error)
    market_absolute_error = abs(
        actual_margin - market_implied_margin
    )

    cover_margin = actual_margin + float(market_line)

    if cover_margin > 0:
        ats_result = "win"
    elif cover_margin < 0:
        ats_result = "loss"
    else:
        ats_result = "push"

    return {
        "actual_selected_side_margin": round(actual_margin, 1),
        "signed_forecast_error": round(signed_error, 1),
        "absolute_forecast_error": round(absolute_error, 1),
        "market_absolute_error": round(
            market_absolute_error,
            1,
        ),
        "ats_result": ats_result,
    }


def selected_market_metadata(game, selected_side):
    if selected_side == "home":
        price = game["home_spread_price"]
        opening = game["opening_home_spread"]
    else:
        price = game["away_spread_price"]
        opening = (
            -game["opening_home_spread"]
            if game["opening_home_spread"] is not None
            else None
        )

    return price, opening


def write_csv(path: Path, rows: list[dict], fields):
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    enforce_holdout_policy(args)

    replay_as_of = parse_timestamp(
        args.replay_as_of,
        "replay_as_of",
    )

    snapshot = load_ratings_snapshot(args.ratings)

    if snapshot.season != args.season:
        raise RuntimeError(
            f"Ratings season {snapshot.season} does not match "
            f"replay season {args.season}."
        )

    if snapshot.target_week != args.week:
        raise RuntimeError(
            f"Ratings target week {snapshot.target_week} does not "
            f"match replay week {args.week}."
        )

    if replay_as_of < snapshot.safe_after:
        raise RuntimeError(
            "Replay as-of precedes ratings safe_after. "
            "This replay would leak unavailable ratings."
        )

    approved_books = set(
        getattr(production, "APPROVED_BOOKS", set())
    )

    if (
        approved_books
        and args.provider not in approved_books
    ):
        raise RuntimeError(
            f"Provider {args.provider!r} is not approved by frozen "
            f"v0.6 production logic: {sorted(approved_books)}"
        )

    games = load_historical_games(
        args.games_lines,
        args.season,
        args.week,
        args.provider,
    )
    team_mapping, season_fcs_names = load_season_eligibility(
        args.eligibility,
        args.season,
    )

    production_script_path = (
        PROJECT_ROOT
        / "scripts"
        / "project_ncaaf_from_apex.py"
    )
    production_code_sha256 = sha256_file(
        production_script_path
    )

    modeled_rows = []
    exclusions = []

    for game in games:
        reasons = []

        if game["kickoff"] <= snapshot.safe_after:
            reasons.append(
                "kickoff_not_after_ratings_safe_after"
            )

        if game["kickoff"] <= replay_as_of:
            reasons.append(
                "kickoff_not_after_replay_as_of"
            )

        reasons.extend(
            validate_game_eligibility(
                game,
                team_mapping,
                snapshot.ratings,
            )
        )

        if reasons:
            exclusions.append(
                {
                    "event_id": game["event_id"],
                    "season": game["season"],
                    "week": game["week"],
                    "kickoff": game["kickoff_text"],
                    "away_team": game["away_team"],
                    "home_team": game["home_team"],
                    "provider": game["provider"],
                    "reason": ";".join(reasons),
                }
            )
            continue

        with frozen_production_context(
            replay_as_of,
            season_fcs_names,
        ):
            edge = production.build_model_row_for_event(
                event_rows=event_rows_for_production(game),
                ratings=snapshot.ratings,
                team_mapping=team_mapping,
            )

        if edge is None:
            exclusions.append(
                {
                    "event_id": game["event_id"],
                    "season": game["season"],
                    "week": game["week"],
                    "kickoff": game["kickoff_text"],
                    "away_team": game["away_team"],
                    "home_team": game["home_team"],
                    "provider": game["provider"],
                    "reason": "frozen_production_builder_excluded",
                }
            )
            continue

        if edge["selection"] == game["home_team"]:
            selected_side = "home"
        elif edge["selection"] == game["away_team"]:
            selected_side = "away"
        else:
            raise RuntimeError(
                f"Frozen v0.6 returned unrecognized selection "
                f"for {game['event_id']}: {edge['selection']}"
            )

        market_price, opening_market_line = (
            selected_market_metadata(
                game,
                selected_side,
            )
        )

        metrics = result_metrics(
            selected_side=selected_side,
            model_line=float(edge["model_line"]),
            market_line=float(edge["market_line"]),
            home_score=game["home_score"],
            away_score=game["away_score"],
        )

        modeled_rows.append(
            {
                "event_id": game["event_id"],
                "season": args.season,
                "week": args.week,
                "kickoff": game["kickoff_text"],
                "home_team": game["home_team"],
                "away_team": game["away_team"],
                "selected_team": edge["selection"],
                "selected_side": selected_side,
                "provider": args.provider,
                "line_source": game["line_source"],
                "historical_market_line": edge["market_line"],
                "market_price": (
                    market_price
                    if market_price is not None
                    else ""
                ),
                "price_available": market_price is not None,
                "opening_market_line": (
                    opening_market_line
                    if opening_market_line is not None
                    else ""
                ),
                "model_line": edge["model_line"],
                "projected_selected_margin": round(
                    -float(edge["model_line"]),
                    1,
                ),
                "edge_points": edge["edge_points"],
                "recommendation": edge["recommendation"],
                "actionability": derive_actionability(edge),
                "confidence_score": edge["confidence_score"],
                "model_suggested_units": edge["recommended_units"],
                "signal_source": edge["signal_source"],
                "home_score": (
                    game["home_score"]
                    if game["home_score"] is not None
                    else ""
                ),
                "away_score": (
                    game["away_score"]
                    if game["away_score"] is not None
                    else ""
                ),
                **metrics,
                "ratings_season": snapshot.season,
                "ratings_target_week": snapshot.target_week,
                "ratings_source": snapshot.source,
                "ratings_source_label": snapshot.source_label,
                "ratings_source_url": snapshot.source_url,
                "ratings_published_at": (
                    snapshot.published_at.isoformat()
                ),
                "ratings_safe_after": (
                    snapshot.safe_after.isoformat()
                ),
                "ratings_sha256": snapshot.ratings_sha256,
                "replay_as_of": replay_as_of.isoformat(),
                "model_version": MODEL_VERSION,
                "production_code_sha256": (
                    production_code_sha256
                ),
            }
        )

    if args.validate_only:
        print("VALIDATION ONLY - no replay artifacts written.")
        print(f"Games considered: {len(games)}")
        print(f"Would model: {len(modeled_rows)}")
        print(f"Would exclude: {len(exclusions)}")
        if exclusions:
            counts = Counter(
                reason
                for row in exclusions
                for reason in row["reason"].split(";")
            )
            print(f"Exclusions: {dict(counts)}")
        return

    if args.output_dir.exists():
        raise RuntimeError(
            f"Refusing to overwrite immutable replay directory: "
            f"{args.output_dir}"
        )

    args.output_dir.mkdir(parents=True)
    inputs_dir = args.output_dir / "inputs"
    inputs_dir.mkdir()

    copied_inputs = {}

    for label, source in (
        ("ratings", args.ratings),
        ("games_lines", args.games_lines),
        ("eligibility", args.eligibility),
    ):
        destination = inputs_dir / source.name
        shutil.copy2(source, destination)
        copied_inputs[label] = {
            "original_path": str(source.resolve()),
            "copied_path": str(
                destination.relative_to(args.output_dir)
            ),
            "sha256": sha256_file(destination),
        }

    rows_path = args.output_dir / "rows.csv"
    exclusions_path = args.output_dir / "exclusions.csv"

    write_csv(
        rows_path,
        modeled_rows,
        OUTPUT_FIELDS,
    )

    exclusion_fields = [
        "event_id",
        "season",
        "week",
        "kickoff",
        "away_team",
        "home_team",
        "provider",
        "reason",
    ]
    write_csv(
        exclusions_path,
        exclusions,
        exclusion_fields,
    )

    manifest = {
        "schema_version": 1,
        "artifact_type": "isolated_ncaaf_v0_6_historical_replay",
        "mode": args.mode,
        "season": args.season,
        "week": args.week,
        "provider": args.provider,
        "replay_as_of": replay_as_of.isoformat(),
        "model_version": MODEL_VERSION,
        "production_model_version_string": getattr(
            production,
            "MODEL_VERSION",
            "unknown",
        ),
        "production_script": (
            "scripts/project_ncaaf_from_apex.py"
        ),
        "production_code_sha256": production_code_sha256,
        "apexmodel_git_commit": get_git_commit(),
        "ratings": {
            "season": snapshot.season,
            "target_week": snapshot.target_week,
            "source": snapshot.source,
            "source_label": snapshot.source_label,
            "source_url": snapshot.source_url,
            "published_at": snapshot.published_at.isoformat(),
            "safe_after": snapshot.safe_after.isoformat(),
            "ratings_sha256": snapshot.ratings_sha256,
            "team_count": snapshot.row_count,
        },
        "line_source": sorted(
            {
                game["line_source"]
                for game in games
                if game["line_source"]
            }
        ),
        "games_considered": len(games),
        "games_modeled": len(modeled_rows),
        "games_excluded": len(exclusions),
        "exclusion_counts": dict(
            Counter(
                reason
                for row in exclusions
                for reason in row["reason"].split(";")
            )
        ),
        "inputs": copied_inputs,
        "outputs": {
            "rows_csv": "rows.csv",
            "rows_sha256": sha256_file(rows_path),
            "exclusions_csv": "exclusions.csv",
            "exclusions_sha256": sha256_file(
                exclusions_path
            ),
        },
        "production_data_touched": False,
        "production_ratings_updater_invoked": False,
        "production_database_written": False,
        "sample_model_edges_written": False,
        "holdout_policy": {
            "development_seasons": [2022, 2023, 2024],
            "historical_holdout": 2025,
            "forward_validation": "2026+",
            "holdout_requires_explicit_unlock": True,
        },
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    manifest_path = args.output_dir / "replay_manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Replay artifact: {args.output_dir}")
    print(f"Games considered: {len(games)}")
    print(f"Games modeled: {len(modeled_rows)}")
    print(f"Games excluded: {len(exclusions)}")
    print(f"Rows SHA256: {manifest['outputs']['rows_sha256']}")


if __name__ == "__main__":
    main()

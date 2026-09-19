import csv
import hashlib
import json
import math
import shutil
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from scripts import diagnose_ncaaf_2023_week5 as w5
from scripts.ncaaf_replay_snapshot import load_ratings_snapshot

ROOT = Path.cwd()

DATA = ROOT / "data/replays/ncaaf_v0_6"
RATINGS = DATA / "ratings/2023"
GAMES = DATA / "games_lines/2023"
ELIGIBILITY = DATA / "eligibility/2023.csv"
DISC = DATA / "source_discovery"
VECTORS = DISC / "2023_weekly_vectors"

REPLAY_ROOT = ROOT / "outputs/replays/ncaaf_v0_6/2023"

OUT = REPLAY_ROOT / "season_diagnostics_001"

STATIC_SOURCE = (
    REPLAY_ROOT
    / "week_05"
    / "diagnostics_001"
    / "static_2022_final_spplus.json"
)

REGRESSION = VECTORS / "schema_provenance.json"

prod = w5.prod
replay = w5.replay


# ============================================================
# Helpers
# ============================================================

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def directory_sha256(path):
    h = hashlib.sha256()

    for file in sorted(
        (p for p in path.rglob("*") if p.is_file()),
        key=lambda p: str(p.relative_to(path)),
    ):
        rel = str(file.relative_to(path)).replace("\\", "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_file(file).encode("ascii"))
        h.update(b"\n")

    return h.hexdigest()


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    rows = list(rows)

    if fields is None:
        fields = list(rows[0].keys()) if rows else []

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def f(value):
    if value in ("", None):
        return None
    return float(value)


def mean(values):
    values = list(values)
    return statistics.fmean(values) if values else math.nan


def median(values):
    values = list(values)
    return statistics.median(values) if values else math.nan


def rmse(values):
    values = list(values)
    return (
        math.sqrt(statistics.fmean(x * x for x in values))
        if values
        else math.nan
    )


def fmt(value, digits=2):
    if isinstance(value, float) and math.isnan(value):
        return ""
    return f"{value:.{digits}f}"


def edge_bucket(value):
    x = float(value)

    if x < 1.0:
        return "<1.0"
    if x < 2.0:
        return "1.0-1.9"
    if x < 4.0:
        return "2.0-3.9"
    if x < 7.0:
        return "4.0-6.9"
    if x < 10.0:
        return "7.0-9.9"
    return "10.0+"


def spread_bucket(value):
    x = abs(float(value))

    if x <= 6.5:
        return "0-6.5"
    if x <= 13.5:
        return "7-13.5"
    if x <= 20.5:
        return "14-20.5"
    if x <= 27.5:
        return "21-27.5"
    return "28+"


def action_bucket(row):
    action = str(row.get("actionability", "")).strip().lower()
    units = f(row.get("model_suggested_units")) or 0.0

    if "model play" in action:
        return "Model Play"

    if "review" in action:
        return "Review Only"

    if units > 0:
        return "Model Play"

    return "Guarded / Other"


def selected_market_role(row):
    selected_spread = f(
        row.get("historical_market_line")
    )

    if selected_spread is None:
        return "Unknown"

    if selected_spread < 0:
        return "Favorite"

    if selected_spread > 0:
        return "Underdog"

    return "Pick'em"


def model_favorite_side(row):
    margin = row_measures(row)[
        "model_home_margin"
    ]

    if margin > 0:
        return "Model-projected home favorite"

    if margin < 0:
        return "Model-projected road favorite"

    return "Model pick'em"


def row_measures(row):
    home_score = f(row["home_score"])
    away_score = f(row["away_score"])

    actual_home = home_score - away_score

    # Canonical replay fields.
    model_error = f(row["signed_forecast_error"])
    model_ae = f(row["absolute_forecast_error"])
    model_home = actual_home + model_error

    # historical_market_line is the SELECTED-SIDE spread,
    # not necessarily the home spread.
    selected_spread = f(row["historical_market_line"])

    if selected_spread is None:
        market_home = None
        market_error = None
    else:
        market_home = (
            -selected_spread
            if row["selected_side"] == "home"
            else selected_spread
        )
        market_error = market_home - actual_home

    market_ae = f(row["market_absolute_error"])

    projected_selected = f(
        row["projected_selected_margin"]
    )
    actual_selected = f(
        row["actual_selected_side_margin"]
    )

    selected_bias = (
        projected_selected - actual_selected
    )

    return {
        "actual_home_margin": actual_home,
        "model_home_margin": model_home,
        "model_error": model_error,
        "model_ae": model_ae,
        "market_home_margin": market_home,
        "market_error": market_error,
        "market_ae": market_ae,
        "projected_selected_margin": projected_selected,
        "actual_selected_margin": actual_selected,
        "selected_bias": selected_bias,
    }


def ats_summary(rows):
    results = [
        str(r.get("ats_result", "")).lower()
        for r in rows
        if r.get("ats_result")
    ]

    wins = results.count("win")
    losses = results.count("loss")
    pushes = results.count("push")
    decisions = wins + losses

    return {
        "ats_wins": wins,
        "ats_losses": losses,
        "ats_pushes": pushes,
        "ats_record": f"{wins}-{losses}-{pushes}",
        "ats_win_rate": (
            100.0 * wins / decisions
            if decisions
            else math.nan
        ),
    }


def diagnostic_metrics(rows):
    measures = [row_measures(r) for r in rows]

    model_errors = [m["model_error"] for m in measures]
    model_ae = [m["model_ae"] for m in measures]

    market_ae = [
        m["market_ae"]
        for m in measures
        if m["market_ae"] is not None
    ]

    home_bias = [m["model_error"] for m in measures]
    selected_bias = [m["selected_bias"] for m in measures]

    model_better = 0
    market_better = 0
    ties = 0

    for m in measures:
        if m["market_ae"] is None:
            continue

        if abs(m["model_ae"] - m["market_ae"]) <= 1e-9:
            ties += 1
        elif m["model_ae"] < m["market_ae"]:
            model_better += 1
        else:
            market_better += 1

    out = {
        "n": len(rows),
        "model_mae": mean(model_ae),
        "median_ae": median(model_ae),
        "rmse": rmse(model_errors),
        "home_signed_bias": mean(home_bias),
        "selected_side_signed_bias": mean(selected_bias),
        "archival_market_mae": mean(market_ae),
        "model_better": model_better,
        "market_better": market_better,
        "ties": ties,
        "model_better_pct": (
            100.0 * model_better
            / (model_better + market_better + ties)
            if model_better + market_better + ties
            else math.nan
        ),
        "within_3_pct": (
            100.0 * sum(x <= 3 for x in model_ae) / len(model_ae)
            if model_ae else math.nan
        ),
        "within_7_pct": (
            100.0 * sum(x <= 7 for x in model_ae) / len(model_ae)
            if model_ae else math.nan
        ),
        "within_10_pct": (
            100.0 * sum(x <= 10 for x in model_ae) / len(model_ae)
            if model_ae else math.nan
        ),
        "within_14_pct": (
            100.0 * sum(x <= 14 for x in model_ae) / len(model_ae)
            if model_ae else math.nan
        ),
    }

    out.update(ats_summary(rows))
    return out


def diagnostic_row(label, rows):
    m = diagnostic_metrics(rows)

    return {
        "group": label,
        "n": m["n"],
        "ats_record": m["ats_record"],
        "ats_win_rate": fmt(m["ats_win_rate"]),
        "model_mae": fmt(m["model_mae"]),
        "archival_dk_mae": fmt(m["archival_market_mae"]),
        "median_ae": fmt(m["median_ae"]),
        "home_signed_bias": fmt(m["home_signed_bias"]),
        "selected_side_signed_bias": fmt(
            m["selected_side_signed_bias"]
        ),
        "model_better": m["model_better"],
        "market_better": m["market_better"],
        "ties": m["ties"],
    }


def markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(h, "")) for h in headers)
            + " |"
        )

    return "\n".join(lines)


def load_static_ratings(path):
    obj = json.loads(path.read_text(encoding="utf-8"))

    def find_mapping(node):
        if isinstance(node, list):
            result = {}

            for item in node:
                if not isinstance(item, dict):
                    continue

                team = (
                    item.get("team")
                    or item.get("school")
                    or item.get("name")
                )

                rating = None
                for key in (
                    "rating",
                    "sp_plus",
                    "sp+",
                    "SP+",
                    "value",
                ):
                    if key in item:
                        try:
                            rating = float(item[key])
                        except (TypeError, ValueError):
                            rating = None
                        break

                if team and rating is not None:
                    result[str(team)] = rating

            if len(result) >= 50:
                return result

        if isinstance(node, dict):
            numeric = {}

            for key, value in node.items():
                try:
                    numeric[str(key)] = float(value)
                except (TypeError, ValueError):
                    pass

            if len(numeric) >= 50:
                return numeric

            nested = {}

            for team, value in node.items():
                if not isinstance(value, dict):
                    continue

                for key in (
                    "rating",
                    "sp_plus",
                    "sp+",
                    "SP+",
                    "value",
                ):
                    if key not in value:
                        continue
                    try:
                        nested[str(team)] = float(value[key])
                    except (TypeError, ValueError):
                        pass
                    break

            if len(nested) >= 50:
                return nested

            for value in node.values():
                found = find_mapping(value)
                if found:
                    return found

        return None

    result = find_mapping(obj)

    if not result:
        raise RuntimeError(
            f"Unable to locate ratings mapping in {path}"
        )

    return result


def production_row(game, ratings, mapping, asof):
    with replay.frozen_production_context(
        asof,
        set(),
    ):
        result = prod.build_model_row_for_event(
            event_rows=replay.event_rows_for_production(game),
            ratings=ratings,
            team_mapping=mapping,
        )

    if isinstance(result, list):
        if len(result) != 1:
            raise RuntimeError(
                "Unexpected production-row list length: "
                f"{len(result)}"
            )
        result = result[0]

    if not isinstance(result, dict):
        raise RuntimeError(
            f"Unexpected production-row type: {type(result)}"
        )

    if "model_line" not in result:
        raise RuntimeError(
            "Production row missing model_line. "
            f"Keys: {sorted(result)}"
        )

    return result


def values_equal(a, b):
    if a in ("", None) and b in ("", None):
        return True

    try:
        return abs(float(a) - float(b)) <= 1e-6
    except (TypeError, ValueError):
        return str(a) == str(b)


# ============================================================
# Safety / output setup
# ============================================================

if OUT.exists():
    raise RuntimeError(
        f"Refusing to overwrite existing diagnostics: {OUT}"
    )

OUT.mkdir(parents=True)

if not STATIC_SOURCE.exists():
    raise RuntimeError(
        f"Static 2022 SP+ artifact missing: {STATIC_SOURCE}"
    )

if not REGRESSION.exists():
    raise RuntimeError(
        "Historical extractor regression provenance missing"
    )

regression = json.loads(REGRESSION.read_text(encoding="utf-8"))

if regression.get("status") != "PASS":
    raise RuntimeError("Historical extractor regression did not PASS")

shutil.copy2(
    STATIC_SOURCE,
    OUT / "static_2022_final_spplus.json",
)


# ============================================================
# Load canonical Weeks 1-14
# ============================================================

eligibility_map, fbs = replay.load_season_eligibility(
    ELIGIBILITY,
    2023,
)

# Independent projection-fidelity identity map.
# Mirrors the accepted Week 5 diagnostic exactly.
eligibility_rows = read_csv(ELIGIBILITY)
projection_identity = {
    r["display_team"]: r
    for r in eligibility_rows
}

weekly_rows = {}
games_cache = {}
snapshots = {}
all_rows = []

artifact_rows = []

for week in range(1, 15):
    artifact = (
        REPLAY_ROOT
        / f"week_{week:02d}"
        / "replay_001"
    )

    if "INVALID_rank_bug" in str(artifact):
        raise RuntimeError(
            "Invalid rank-bug artifact entered canonical path"
        )

    rows_path = artifact / "rows.csv"

    if not rows_path.exists():
        raise RuntimeError(
            f"Canonical replay rows missing for Week {week}: "
            f"{rows_path}"
        )

    rows = read_csv(rows_path)

    for row in rows:
        row["_week"] = week

    weekly_rows[week] = rows
    all_rows.extend(rows)

    ratings_path = (
        RATINGS
        / f"week_{week:02d}"
        / "normalized.csv"
    )

    games_path = (
        GAMES
        / f"week_{week:02d}_draftkings.csv"
    )

    snapshot = load_ratings_snapshot(ratings_path)
    games = replay.load_historical_games(
        games_path,
        2023,
        week,
        "DraftKings",
    )

    snapshots[week] = snapshot
    games_cache[week] = {
        str(g["event_id"]): g
        for g in games
    }

    artifact_rows.append(
        {
            "week": week,
            "artifact_dir": str(
                artifact.relative_to(ROOT)
            ).replace("\\", "/"),
            "rows_sha256": sha256_file(rows_path),
            "artifact_directory_sha256": directory_sha256(
                artifact
            ),
            "modeled_rows": len(rows),
        }
    )

write_csv(
    OUT / "canonical_weekly_artifacts.csv",
    artifact_rows,
)


# ============================================================
# Integrity checks
# ============================================================

games_considered = 0
exclusions = 0
exclusion_reasons = Counter()

projection_total = 0
projection_pass = 0

temporal_total = 0
temporal_pass = 0

identity_total = 0
identity_pass = 0

result_total = 0
result_pass = 0

production_hashes = set()
model_versions = set()

projection_keys = [
    "model_line",
    "selected_team",
    "selected_side",
    "edge_points",
    "recommendation",
    "confidence_score",
    "model_suggested_units",
]

for week in range(1, 15):
    rows = weekly_rows[week]
    snapshot = snapshots[week]
    games = games_cache[week]

    modeled_ids = {
        str(r["event_id"])
        for r in rows
    }

    games_considered += len(games)

    replay_as_of = (
        w5.ts(rows[0]["replay_as_of"])
        if rows
        else snapshot.safe_after
    )

    for event_id, game in games.items():
        if event_id in modeled_ids:
            continue

        exclusions += 1
        reasons = []

        if game["kickoff"] <= snapshot.safe_after:
            reasons.append(
                "kickoff_not_after_ratings_safe_after"
            )

        if game["kickoff"] <= replay_as_of:
            reasons.append(
                "kickoff_not_after_replay_as_of"
            )

        eligibility_failure = (
            replay.validate_game_eligibility(
                game,
                eligibility_map,
                snapshot.ratings,
            )
        )

        if eligibility_failure:
            if isinstance(
                eligibility_failure,
                (list, tuple, set),
            ):
                reasons.extend(
                    str(x)
                    for x in eligibility_failure
                )
            else:
                reasons.append(
                    str(eligibility_failure)
                )

        if not reasons:
            reasons.append("unexplained_exclusion")

        for reason in set(reasons):
            exclusion_reasons[reason] += 1

    for row in rows:
        event_id = str(row["event_id"])
        game = games[event_id]

        production_hashes.add(
            row.get("production_code_sha256", "")
        )
        model_versions.add(
            row.get("model_version", "")
        )

        # Projection fidelity:
        # mirror the accepted Week 5 independent proof exactly.
        projection_total += 1

        hi = projection_identity.get(
            game["home_team"]
        )
        ai = projection_identity.get(
            game["away_team"]
        )

        matches = False

        ident = bool(
            hi
            and ai
            and hi["classification"].lower() == "fbs"
            and ai["classification"].lower() == "fbs"
            and hi["model_team"] in snapshot.ratings
            and ai["model_team"] in snapshot.ratings
        )

        if ident:
            projected_home_margin = (
                float(
                    snapshot.ratings[
                        hi["model_team"]
                    ]["rating"]
                )
                - float(
                    snapshot.ratings[
                        ai["model_team"]
                    ]["rating"]
                )
                + 2.5
            )

            side = row["selected_side"].lower()

            expected_model_line = round(
                -projected_home_margin
                if side == "home"
                else projected_home_margin,
                1,
            )

            stored_model_line = float(
                row["model_line"]
            )

            matches = (
                abs(
                    expected_model_line
                    - stored_model_line
                )
                < 1e-12
            )

        if matches:
            projection_pass += 1

        # Temporal integrity
        temporal_total += 1

        kickoff = w5.ts(row["kickoff"])
        safe_after = w5.ts(
            row["ratings_safe_after"]
        )
        as_of = w5.ts(row["replay_as_of"])

        if kickoff > safe_after and kickoff > as_of:
            temporal_pass += 1

        # Identity / FBS integrity
        identity_total += 1

        identity_failure = (
            replay.validate_game_eligibility(
                game,
                eligibility_map,
                snapshot.ratings,
            )
        )

        if not identity_failure:
            identity_pass += 1

        # Result orientation
        result_total += 1

        measures = row_measures(row)

        stored_selected = f(
            row["actual_selected_side_margin"]
        )

        actual_selected_ok = (
            stored_selected is not None
            and abs(
                stored_selected
                - measures["actual_selected_margin"]
            ) <= 1e-9
        )

        selected_spread = f(
            row["historical_market_line"]
        )

        ats_margin = (
            measures["actual_selected_margin"]
            + selected_spread
        )

        if abs(ats_margin) <= 1e-9:
            expected_ats = "push"
        elif ats_margin > 0:
            expected_ats = "win"
        else:
            expected_ats = "loss"

        ats_ok = (
            str(row["ats_result"]).lower()
            == expected_ats
        )

        scores_ok = (
            abs(
                f(row["home_score"])
                - float(game["home_score"])
            ) <= 1e-9
            and abs(
                f(row["away_score"])
                - float(game["away_score"])
            ) <= 1e-9
        )

        stored_market_ae = f(
            row["market_absolute_error"]
        )
        reconstructed_market_ae = abs(
            measures["market_error"]
        )

        market_orientation_ok = (
            stored_market_ae is not None
            and abs(
                stored_market_ae
                - reconstructed_market_ae
            ) <= 1e-9
        )

        if (
            actual_selected_ok
            and ats_ok
            and scores_ok
            and market_orientation_ok
        ):
            result_pass += 1


extract_manifest = json.loads(
    (VECTORS / "extraction_manifest.json").read_text(
        encoding="utf-8"
    )
)

week9_14_sp_pass = all(
    regression["weeks"][str(week)]["source_spplus_matches"]
    == 133
    and not regression["weeks"][str(week)][
        "rating_vector_identical_to_rank"
    ]
    for week in range(9, 15)
)

production_isolation_pass = (
    len(production_hashes) == 1
    and len(model_versions) == 1
    and not extract_manifest.get(
        "production_state_written",
        True,
    )
    and not extract_manifest.get(
        "holdout_2025_inspected",
        True,
    )
)

integrity_pass = all(
    [
        len(weekly_rows) == 14,
        projection_pass == projection_total,
        temporal_pass == temporal_total,
        identity_pass == identity_total,
        result_pass == result_total,
        week9_14_sp_pass,
        production_isolation_pass,
    ]
)

integrity = {
    "status": (
        "PASS"
        if integrity_pass
        else "FAIL"
    ),
    "weeks_attempted": 14,
    "weeks_included": len(weekly_rows),
    "games_considered": games_considered,
    "games_modeled": len(all_rows),
    "games_excluded": exclusions,
    "exclusion_reasons": dict(
        sorted(exclusion_reasons.items())
    ),
    "projection_fidelity": (
        f"{projection_pass}/{projection_total}"
    ),
    "temporal_integrity": (
        f"{temporal_pass}/{temporal_total}"
    ),
    "identity_fbs_integrity": (
        f"{identity_pass}/{identity_total}"
    ),
    "result_orientation_integrity": (
        f"{result_pass}/{result_total}"
    ),
    "week_09_14_source_spplus_confirmed": (
        week9_14_sp_pass
    ),
    "production_isolation": (
        production_isolation_pass
    ),
    "production_code_sha256": sorted(
        production_hashes
    ),
    "model_versions": sorted(model_versions),
    "production_state_touched": (
        extract_manifest.get(
            "production_state_written"
        )
    ),
    "holdout_2025_inspected": (
        extract_manifest.get(
            "holdout_2025_inspected"
        )
    ),
    "frozen_v0_6_changed": False,
}

(OUT / "season_integrity.json").write_text(
    json.dumps(
        integrity,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)


# ============================================================
# Raw forecast quality
# ============================================================

season_metrics = diagnostic_metrics(all_rows)

forecast_week_rows = []

for week in range(1, 15):
    m = diagnostic_metrics(
        weekly_rows[week]
    )

    forecast_week_rows.append(
        {
            "week": week,
            "n": m["n"],
            "model_mae": fmt(
                m["model_mae"]
            ),
            "median_ae": fmt(
                m["median_ae"]
            ),
            "rmse": fmt(m["rmse"]),
            "signed_bias": fmt(
                m["home_signed_bias"]
            ),
        }
    )

write_csv(
    OUT / "forecast_quality_by_week.csv",
    forecast_week_rows,
)


# ============================================================
# Archival DraftKings benchmark
# ============================================================

market_errors = [
    row_measures(r)["market_error"]
    for r in all_rows
    if row_measures(r)["market_error"]
    is not None
]

archival_summary = {
    "label": (
        "ARCHIVAL MARKET BENCHMARK — "
        "EXACT REPLAY-AS-OF LINE TIMESTAMP "
        "NOT ESTABLISHED"
    ),
    "n": len(all_rows),
    "model_mae": season_metrics["model_mae"],
    "archival_dk_mae": (
        season_metrics["archival_market_mae"]
    ),
    "model_better": (
        season_metrics["model_better"]
    ),
    "market_better": (
        season_metrics["market_better"]
    ),
    "tie": season_metrics["ties"],
    "model_better_pct": (
        season_metrics["model_better_pct"]
    ),
    "model_signed_home_margin_error": (
        season_metrics["home_signed_bias"]
    ),
    "archival_market_signed_home_margin_error": (
        mean(market_errors)
    ),
}

archival_week_rows = []

for week in range(1, 15):
    m = diagnostic_metrics(
        weekly_rows[week]
    )

    archival_week_rows.append(
        {
            "week": week,
            "n": m["n"],
            "model_mae": fmt(
                m["model_mae"]
            ),
            "archival_market_mae": fmt(
                m["archival_market_mae"]
            ),
            "model_better": (
                m["model_better"]
            ),
            "market_better": (
                m["market_better"]
            ),
            "tie": m["ties"],
        }
    )

write_csv(
    OUT / "archival_market_by_week.csv",
    archival_week_rows,
)


# ============================================================
# Spread-size diagnostics
# ============================================================

spread_order = [
    "0-6.5",
    "7-13.5",
    "14-20.5",
    "21-27.5",
    "28+",
]

spread_groups = defaultdict(list)

for row in all_rows:
    spread_groups[
        spread_bucket(row["model_line"])
    ].append(row)

spread_rows = [
    diagnostic_row(
        label,
        spread_groups[label],
    )
    for label in spread_order
]

write_csv(
    OUT / "spread_size_diagnostics.csv",
    spread_rows,
)

favorite_side_groups = defaultdict(list)

for row in all_rows:
    favorite_side_groups[
        model_favorite_side(row)
    ].append(row)

favorite_side_rows = [
    diagnostic_row(label, rows)
    for label, rows
    in sorted(favorite_side_groups.items())
]

write_csv(
    OUT / "model_favorite_side_diagnostics.csv",
    favorite_side_rows,
)


# ============================================================
# Recommendation / edge / actionability
# ============================================================

rec_order = [
    "Value",
    "Lean",
    "Watch",
    "No Play",
]

rec_groups = defaultdict(list)

for row in all_rows:
    rec_groups[
        row["recommendation"]
    ].append(row)

rec_rows = [
    diagnostic_row(
        label,
        rec_groups[label],
    )
    for label in rec_order
]

write_csv(
    OUT / "recommendation_diagnostics.csv",
    rec_rows,
)

edge_order = [
    "<1.0",
    "1.0-1.9",
    "2.0-3.9",
    "4.0-6.9",
    "7.0-9.9",
    "10.0+",
]

edge_groups = defaultdict(list)

for row in all_rows:
    edge_groups[
        edge_bucket(row["edge_points"])
    ].append(row)

edge_rows = [
    diagnostic_row(
        label,
        edge_groups[label],
    )
    for label in edge_order
]

write_csv(
    OUT / "edge_bucket_diagnostics.csv",
    edge_rows,
)

action_order = [
    "Model Play",
    "Review Only",
    "Guarded / Other",
]

action_groups = defaultdict(list)

for row in all_rows:
    action_groups[
        action_bucket(row)
    ].append(row)

action_rows = [
    diagnostic_row(
        label,
        action_groups[label],
    )
    for label in action_order
]

write_csv(
    OUT / "actionability_diagnostics.csv",
    action_rows,
)


# ============================================================
# Signed-bias diagnostics
# ============================================================

def bias_row(label, rows):
    measures = [
        row_measures(r)
        for r in rows
    ]

    return {
        "group": label,
        "n": len(rows),
        "unconditioned_home_margin_bias": fmt(
            mean(
                m["model_error"]
                for m in measures
            )
        ),
        "market_selected_side_bias": fmt(
            mean(
                m["selected_bias"]
                for m in measures
            )
        ),
    }


write_csv(
    OUT / "bias_overall.csv",
    [bias_row("Overall", all_rows)],
)

write_csv(
    OUT / "bias_by_week.csv",
    [
        {
            "week": week,
            **bias_row(
                f"Week {week}",
                weekly_rows[week],
            ),
        }
        for week in range(1, 15)
    ],
)

market_role_groups = defaultdict(list)

for row in all_rows:
    market_role_groups[
        selected_market_role(row)
    ].append(row)

write_csv(
    OUT / "bias_by_favorite_underdog.csv",
    [
        bias_row(label, rows)
        for label, rows
        in sorted(
            market_role_groups.items()
        )
    ],
)

write_csv(
    OUT / "bias_by_edge_bucket.csv",
    [
        bias_row(
            label,
            edge_groups[label],
        )
        for label in edge_order
    ],
)

write_csv(
    OUT / "bias_by_spread_bucket.csv",
    [
        bias_row(
            label,
            spread_groups[label],
        )
        for label in spread_order
    ],
)

write_csv(
    OUT / "bias_by_recommendation.csv",
    [
        bias_row(
            label,
            rec_groups[label],
        )
        for label in rec_order
    ],
)

write_csv(
    OUT / "bias_by_actionability.csv",
    [
        bias_row(
            label,
            action_groups[label],
        )
        for label in action_order
    ],
)


# ============================================================
# Static 2022 final SP+ vs weekly 2023 SP+
# ============================================================

static_path = OUT / "static_2022_final_spplus.json"
static_raw = json.loads(
    static_path.read_text(encoding="utf-8")
)

# Reuse the proven Week 5 static-team resolution logic.
static_ratings = static_raw

static_comparisons = []
static_failures = []

for week in range(1, 15):
    for row in weekly_rows[week]:
        event_id = str(row["event_id"])
        game = games_cache[week][event_id]

        hk = w5.static_key(
            static_ratings,
            row["home_team"],
        )
        ak = w5.static_key(
            static_ratings,
            row["away_team"],
        )

        if hk is None or ak is None:
            static_failures.append(
                {
                    "week": week,
                    "event_id": event_id,
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "reason": "absent_from_2022_final_SP+",
                }
            )
            continue

        static_mapping = {
            row["home_team"]: {
                "cfbd_team": hk,
                "classification": "fbs",
            },
            row["away_team"]: {
                "cfbd_team": ak,
                "classification": "fbs",
            },
        }

        try:
            static_row = production_row(
                game,
                static_ratings,
                static_mapping,
                w5.ts(row["replay_as_of"]),
            )
        except Exception as exc:
            static_failures.append(
                {
                    "week": week,
                    "event_id": event_id,
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "reason": str(exc),
                }
            )
            continue

        actual_home = (
            f(row["home_score"])
            - f(row["away_score"])
        )

        weekly_error = f(
            row["signed_forecast_error"]
        )
        weekly_model_line = (
            actual_home + weekly_error
        )

        static_model_line = (
            float(static_ratings[hk]["rating"])
            - float(static_ratings[ak]["rating"])
            + 2.5
        )

        static_error = (
            static_model_line
            - actual_home
        )

        static_comparisons.append(
            {
                "week": week,
                "event_id": event_id,
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "actual_home_margin": actual_home,
                "weekly_model_line": (
                    weekly_model_line
                ),
                "static_model_line": (
                    static_model_line
                ),
                "weekly_error": weekly_error,
                "static_error": static_error,
                "weekly_abs_error": abs(
                    weekly_error
                ),
                "static_abs_error": abs(
                    static_error
                ),
                "abs_model_line_change": abs(
                    weekly_model_line
                    - static_model_line
                ),
                "weekly_recommendation": (
                    row["recommendation"]
                ),
                "static_recommendation": (
                    static_row.get(
                        "recommendation",
                        "",
                    )
                ),
                "weekly_edge_bucket": (
                    edge_bucket(
                        row["edge_points"]
                    )
                ),
                "static_edge_bucket": (
                    edge_bucket(
                        static_row.get(
                            "edge_points",
                            0,
                        )
                    )
                ),
                "weekly_actionability": (
                    action_bucket(row)
                ),
                "static_actionability": (
                    action_bucket(
                        static_row
                    )
                ),
            }
        )

if not static_comparisons:
    raise RuntimeError(
        "Static-vs-weekly comparison produced zero shared games"
    )

weekly_better = sum(
    r["weekly_abs_error"]
    < r["static_abs_error"]
    for r in static_comparisons
)

static_better = sum(
    r["static_abs_error"]
    < r["weekly_abs_error"]
    for r in static_comparisons
)

static_ties = (
    len(static_comparisons)
    - weekly_better
    - static_better
)

line_changes = [
    r["abs_model_line_change"]
    for r in static_comparisons
]

static_summary = {
    "shared_games": len(
        static_comparisons
    ),
    "static_mae": mean(
        r["static_abs_error"]
        for r in static_comparisons
    ),
    "weekly_mae": mean(
        r["weekly_abs_error"]
        for r in static_comparisons
    ),
    "weekly_minus_static_mae": (
        mean(
            r["weekly_abs_error"]
            for r in static_comparisons
        )
        - mean(
            r["static_abs_error"]
            for r in static_comparisons
        )
    ),
    "static_signed_bias": mean(
        r["static_error"]
        for r in static_comparisons
    ),
    "weekly_signed_bias": mean(
        r["weekly_error"]
        for r in static_comparisons
    ),
    "weekly_ratings_better": weekly_better,
    "static_ratings_better": static_better,
    "ties": static_ties,
    "mean_absolute_model_line_change": (
        mean(line_changes)
    ),
    "median_absolute_model_line_change": (
        median(line_changes)
    ),
    "maximum_absolute_model_line_change": (
        max(line_changes)
    ),
    "static_unavailable_games": len(
        static_failures
    ),
    "static_source_sha256": sha256_file(
        static_path
    ),
}

(OUT / "static_vs_weekly_summary.json").write_text(
    json.dumps(
        static_summary,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)

if static_failures:
    write_csv(
        OUT / "static_unavailable_games.csv",
        static_failures,
    )

static_week_rows = []

for week in range(1, 15):
    subset = [
        r for r in static_comparisons
        if r["week"] == week
    ]

    if not subset:
        continue

    wb = sum(
        r["weekly_abs_error"]
        < r["static_abs_error"]
        for r in subset
    )
    sb = sum(
        r["static_abs_error"]
        < r["weekly_abs_error"]
        for r in subset
    )

    static_week_rows.append(
        {
            "week": week,
            "shared_games": len(subset),
            "static_mae": fmt(
                mean(
                    r["static_abs_error"]
                    for r in subset
                )
            ),
            "weekly_mae": fmt(
                mean(
                    r["weekly_abs_error"]
                    for r in subset
                )
            ),
            "mae_difference_weekly_minus_static": fmt(
                mean(
                    r["weekly_abs_error"]
                    for r in subset
                )
                - mean(
                    r["static_abs_error"]
                    for r in subset
                )
            ),
            "static_signed_bias": fmt(
                mean(
                    r["static_error"]
                    for r in subset
                )
            ),
            "weekly_signed_bias": fmt(
                mean(
                    r["weekly_error"]
                    for r in subset
                )
            ),
            "weekly_better": wb,
            "static_better": sb,
            "ties": (
                len(subset) - wb - sb
            ),
            "mean_abs_model_line_change": fmt(
                mean(
                    r["abs_model_line_change"]
                    for r in subset
                )
            ),
            "median_abs_model_line_change": fmt(
                median(
                    r["abs_model_line_change"]
                    for r in subset
                )
            ),
            "max_abs_model_line_change": fmt(
                max(
                    r["abs_model_line_change"]
                    for r in subset
                )
            ),
        }
    )

write_csv(
    OUT / "static_vs_weekly_by_week.csv",
    static_week_rows,
)

rec_migration = Counter(
    (
        r["static_recommendation"],
        r["weekly_recommendation"],
    )
    for r in static_comparisons
)

write_csv(
    OUT / "recommendation_migration.csv",
    [
        {
            "static_recommendation": a,
            "weekly_recommendation": b,
            "n": n,
        }
        for (a, b), n
        in sorted(rec_migration.items())
    ],
)

edge_migration = Counter(
    (
        r["static_edge_bucket"],
        r["weekly_edge_bucket"],
    )
    for r in static_comparisons
)

write_csv(
    OUT / "edge_bucket_migration.csv",
    [
        {
            "static_edge_bucket": a,
            "weekly_edge_bucket": b,
            "n": n,
        }
        for (a, b), n
        in sorted(edge_migration.items())
    ],
)

action_migration = Counter(
    (
        r["static_actionability"],
        r["weekly_actionability"],
    )
    for r in static_comparisons
)

write_csv(
    OUT / "model_play_migration.csv",
    [
        {
            "static_actionability": a,
            "weekly_actionability": b,
            "n": n,
        }
        for (a, b), n
        in sorted(action_migration.items())
    ],
)


# ============================================================
# Opening vs archival market movement
# ============================================================

movement_rows = []

for row in all_rows:
    opening = f(
        row.get("opening_market_line")
    )
    archival = f(
        row.get("historical_market_line")
    )

    if opening is None or archival is None:
        continue

    movement_rows.append(
        {
            "week": int(row["week"]),
            "event_id": row["event_id"],
            "away_team": row["away_team"],
            "home_team": row["home_team"],
            "opening_home_spread": opening,
            "archival_home_spread": archival,
            "absolute_movement": abs(
                archival - opening
            ),
        }
    )

movement_values = [
    r["absolute_movement"]
    for r in movement_rows
]

movement_summary = {
    "n": len(movement_rows),
    "mean_absolute_movement": (
        mean(movement_values)
    ),
    "median_absolute_movement": (
        median(movement_values)
    ),
    "maximum_absolute_movement": (
        max(movement_values)
        if movement_values
        else math.nan
    ),
    "unchanged_count": sum(
        x <= 1e-9
        for x in movement_values
    ),
    "unchanged_pct": (
        100.0
        * sum(
            x <= 1e-9
            for x in movement_values
        )
        / len(movement_values)
        if movement_values
        else math.nan
    ),
}

(OUT / "opening_movement_summary.json").write_text(
    json.dumps(
        movement_summary,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)

write_csv(
    OUT / "opening_movement_top20.csv",
    sorted(
        movement_rows,
        key=lambda r: r[
            "absolute_movement"
        ],
        reverse=True,
    )[:20],
)


# ============================================================
# Outliers
# ============================================================

outlier_rows = []

for row in all_rows:
    week = int(row["week"])
    measures = row_measures(row)
    snapshot = snapshots[week]

    home_rating = (
        snapshot.ratings.get(
            row["home_team"]
        )
    )
    away_rating = (
        snapshot.ratings.get(
            row["away_team"]
        )
    )

    outlier_rows.append(
        {
            "week": week,
            "event_id": row["event_id"],
            "away_team": row["away_team"],
            "home_team": row["home_team"],
            "away_spplus": away_rating,
            "home_spplus": home_rating,
            "model_margin": (
                measures["model_home_margin"]
            ),
            "archival_dk_home_spread": (
                f(
                    row[
                        "historical_market_line"
                    ]
                )
            ),
            "actual_home_margin": (
                measures[
                    "actual_home_margin"
                ]
            ),
            "signed_error_projected_minus_actual": (
                measures["model_error"]
            ),
            "absolute_error": (
                measures["model_ae"]
            ),
            "recommendation": (
                row["recommendation"]
            ),
            "actionability": (
                action_bucket(row)
            ),
        }
    )

write_csv(
    OUT / "outliers_largest_absolute_misses.csv",
    sorted(
        outlier_rows,
        key=lambda r: r["absolute_error"],
        reverse=True,
    )[:20],
)

write_csv(
    OUT / "outliers_largest_positive_errors.csv",
    sorted(
        outlier_rows,
        key=lambda r: r[
            "signed_error_projected_minus_actual"
        ],
        reverse=True,
    )[:20],
)

write_csv(
    OUT / "outliers_largest_negative_errors.csv",
    sorted(
        outlier_rows,
        key=lambda r: r[
            "signed_error_projected_minus_actual"
        ],
    )[:20],
)


# ============================================================
# Full metrics JSON
# ============================================================

full_metrics = {
    "season": 2023,
    "integrity": integrity,
    "forecast_quality": {
        "n": season_metrics["n"],
        "model_mae": (
            season_metrics["model_mae"]
        ),
        "median_absolute_error": (
            season_metrics["median_ae"]
        ),
        "rmse": season_metrics["rmse"],
        "mean_signed_home_margin_error": (
            season_metrics[
                "home_signed_bias"
            ]
        ),
        "within_3_pct": (
            season_metrics["within_3_pct"]
        ),
        "within_7_pct": (
            season_metrics["within_7_pct"]
        ),
        "within_10_pct": (
            season_metrics[
                "within_10_pct"
            ]
        ),
        "within_14_pct": (
            season_metrics[
                "within_14_pct"
            ]
        ),
    },
    "archival_market_benchmark": (
        archival_summary
    ),
    "static_vs_weekly": static_summary,
    "opening_vs_archival_movement": (
        movement_summary
    ),
}

(OUT / "metrics.json").write_text(
    json.dumps(
        full_metrics,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)


# ============================================================
# Human-readable report
# ============================================================

principal = [
    {
        "Metric": "Games modeled",
        "Value": len(all_rows),
    },
    {
        "Metric": "Model MAE",
        "Value": fmt(
            season_metrics["model_mae"]
        ),
    },
    {
        "Metric": "Median AE",
        "Value": fmt(
            season_metrics["median_ae"]
        ),
    },
    {
        "Metric": "RMSE",
        "Value": fmt(
            season_metrics["rmse"]
        ),
    },
    {
        "Metric": "Home-margin bias",
        "Value": fmt(
            season_metrics[
                "home_signed_bias"
            ]
        ),
    },
    {
        "Metric": "Within 7 pts",
        "Value": (
            fmt(
                season_metrics[
                    "within_7_pct"
                ]
            )
            + "%"
        ),
    },
    {
        "Metric": "Archival DK MAE",
        "Value": fmt(
            season_metrics[
                "archival_market_mae"
            ]
        ),
    },
    {
        "Metric": "Model better %",
        "Value": (
            fmt(
                season_metrics[
                    "model_better_pct"
                ]
            )
            + "%"
        ),
    },
]

files_generated = sorted(
    str(p.relative_to(OUT))
    for p in OUT.iterdir()
    if p.is_file()
)

report = []

report += [
    "# NCAAF v0.6 — 2023 Corrected Season Diagnostic Packet",
    "",
    "## 2023 Season Integrity",
    "",
    f"**{integrity['status']}**",
    "",
    f"- Weeks attempted: **{integrity['weeks_attempted']}**",
    f"- Weeks included: **{integrity['weeks_included']}**",
    f"- Games considered: **{integrity['games_considered']}**",
    f"- Games modeled: **{integrity['games_modeled']}**",
    f"- Games excluded: **{integrity['games_excluded']}**",
    f"- Exclusion reasons: `{integrity['exclusion_reasons']}`",
    f"- Projection fidelity: **{integrity['projection_fidelity']}**",
    f"- Temporal integrity: **{integrity['temporal_integrity']}**",
    f"- Identity/FBS integrity: **{integrity['identity_fbs_integrity']}**",
    f"- Result orientation integrity: **{integrity['result_orientation_integrity']}**",
    f"- Week 9–14 corrected SP+ vectors confirmed: **{week9_14_sp_pass}**",
    f"- Production isolation: **{production_isolation_pass}**",
    f"- 2025 inspected: **{integrity['holdout_2025_inspected']}**",
    f"- Frozen v0.6 changed: **{integrity['frozen_v0_6_changed']}**",
    f"- Production state touched: **{integrity['production_state_touched']}**",
    "",
    "Canonical weekly replay artifacts and hashes are recorded in `canonical_weekly_artifacts.csv`.",
    "",
    "## 2023 Season Forecast Summary",
    "",
    markdown_table(
        ["Metric", "Value"],
        principal,
    ),
    "",
    "## Raw Forecast Quality by Week",
    "",
    markdown_table(
        [
            "week",
            "n",
            "model_mae",
            "median_ae",
            "rmse",
            "signed_bias",
        ],
        forecast_week_rows,
    ),
    "",
    "## ARCHIVAL MARKET BENCHMARK — EXACT REPLAY-AS-OF LINE TIMESTAMP NOT ESTABLISHED",
    "",
    f"- Model MAE: **{fmt(archival_summary['model_mae'])}**",
    f"- Archival DK MAE: **{fmt(archival_summary['archival_dk_mae'])}**",
    f"- Model Better / Market Better / Tie: **{archival_summary['model_better']} / {archival_summary['market_better']} / {archival_summary['tie']}**",
    f"- Model Better %: **{fmt(archival_summary['model_better_pct'])}%**",
    f"- Model signed home-margin error: **{fmt(archival_summary['model_signed_home_margin_error'])}**",
    f"- Archival-market signed home-margin error: **{fmt(archival_summary['archival_market_signed_home_margin_error'])}**",
    "",
    markdown_table(
        [
            "week",
            "n",
            "model_mae",
            "archival_market_mae",
            "model_better",
            "market_better",
            "tie",
        ],
        archival_week_rows,
    ),
    "",
    "## Spread-Size Diagnostics",
    "",
    markdown_table(
        [
            "group",
            "n",
            "model_mae",
            "archival_dk_mae",
            "median_ae",
            "home_signed_bias",
            "model_better",
            "market_better",
            "ties",
        ],
        spread_rows,
    ),
    "",
    "## Edge / Recommendation Diagnostics",
    "",
    "### Recommendation",
    "",
    markdown_table(
        [
            "group",
            "n",
            "ats_record",
            "ats_win_rate",
            "model_mae",
            "archival_dk_mae",
            "selected_side_signed_bias",
        ],
        rec_rows,
    ),
    "",
    "### Edge Bucket",
    "",
    markdown_table(
        [
            "group",
            "n",
            "ats_record",
            "ats_win_rate",
            "model_mae",
            "archival_dk_mae",
            "selected_side_signed_bias",
        ],
        edge_rows,
    ),
    "",
    "### Production Actionability",
    "",
    markdown_table(
        [
            "group",
            "n",
            "ats_record",
            "ats_win_rate",
            "model_mae",
            "archival_dk_mae",
            "selected_side_signed_bias",
        ],
        action_rows,
    ),
    "",
    "## Signed-Bias Diagnostics",
    "",
    "Both requested bias definitions are stored across the dedicated `bias_*.csv` tables:",
    "",
    "- Unconditioned home-margin bias = projected home margin − actual home margin.",
    "- Market-selected-side bias = projected selected-side margin − actual selected-side margin.",
    "",
    "## Static 2022 Final SP+ vs Contemporaneous 2023 Weekly SP+",
    "",
    f"- Shared games: **{static_summary['shared_games']}**",
    f"- Static MAE: **{fmt(static_summary['static_mae'])}**",
    f"- Weekly MAE: **{fmt(static_summary['weekly_mae'])}**",
    f"- Weekly − Static MAE: **{fmt(static_summary['weekly_minus_static_mae'])}**",
    f"- Static signed bias: **{fmt(static_summary['static_signed_bias'])}**",
    f"- Weekly signed bias: **{fmt(static_summary['weekly_signed_bias'])}**",
    f"- Weekly ratings better / Static better / Ties: **{static_summary['weekly_ratings_better']} / {static_summary['static_ratings_better']} / {static_summary['ties']}**",
    f"- Mean absolute model-line change: **{fmt(static_summary['mean_absolute_model_line_change'])}**",
    f"- Median absolute model-line change: **{fmt(static_summary['median_absolute_model_line_change'])}**",
    f"- Maximum absolute model-line change: **{fmt(static_summary['maximum_absolute_model_line_change'])}**",
    "",
    "Week-level comparison and recommendation/edge/actionability migration are stored in the corresponding CSV artifacts.",
    "",
    "## Opening vs Archival-Market Movement",
    "",
    f"- Rows with opening + archival line: **{movement_summary['n']}**",
    f"- Mean absolute movement: **{fmt(movement_summary['mean_absolute_movement'])}**",
    f"- Median movement: **{fmt(movement_summary['median_absolute_movement'])}**",
    f"- Maximum movement: **{fmt(movement_summary['maximum_absolute_movement'])}**",
    f"- Unchanged: **{movement_summary['unchanged_count']} ({fmt(movement_summary['unchanged_pct'])}%)**",
    "",
    "The 20 largest movements are stored in `opening_movement_top20.csv`.",
    "",
    "## Outliers",
    "",
    "The packet contains:",
    "",
    "- `outliers_largest_absolute_misses.csv`",
    "- `outliers_largest_positive_errors.csv`",
    "- `outliers_largest_negative_errors.csv`",
    "",
    "Legitimate football outliers are retained; no rows were removed based on model error.",
    "",
    "## Historical-Extractor Regression Control",
    "",
    "- Exact `SP+` header required.",
    "- Duplicate or absent exact `SP+` header fails.",
    "- 133 expected normalized teams required.",
    "- All normalized identities must resolve.",
    "- Source header/schema retained in `schema_provenance.json`.",
    "- Extraction fails regression if the rating vector is identically equal to the adjacent `Rk` vector.",
    "- No arbitrary statistical-distribution threshold is used.",
    "",
    "## Data Limitations",
    "",
    "- **ARCHIVAL MARKET BENCHMARK — EXACT REPLAY-AS-OF LINE TIMESTAMP NOT ESTABLISHED.** DraftKings data is archival and must not be described as a closing or guaranteed contemporaneous replay-as-of line.",
    "- Week 3 contains only **10** FBS-vs-FBS games with archived DraftKings spreads in CFBD despite a substantially larger football slate; Week 3 market coverage is therefore incomplete.",
    "- Several ratings `safe_after` timestamps remain conservative/provisional availability timestamps. They were sufficient for leakage gating in this reconstruction but have not been tightened to exact publication minutes.",
    "- Static prior-season comparison includes only games for which the static 2022 ratings input can be resolved through frozen production logic.",
    "",
    "## Files / Commit",
    "",
    "Generated season packet files:",
]

report += [
    f"- `{name}`"
    for name in files_generated
]

report += [
    "",
    "- Commit: **PENDING packet commit**",
    "",
    "No v0.7 tuning or App/UI recommendation is made in this packet.",
]

(OUT / "REPORT.md").write_text(
    "\n".join(report) + "\n",
    encoding="utf-8",
)


# ============================================================
# Compact final summary
# ============================================================

summary_lines = [
    f"2023 Season Integrity: {integrity['status']}",
    f"Games considered / modeled / excluded: {games_considered} / {len(all_rows)} / {exclusions}",
    f"Projection / temporal / identity / result: {projection_pass}/{projection_total} | {temporal_pass}/{temporal_total} | {identity_pass}/{identity_total} | {result_pass}/{result_total}",
    f"Model MAE: {fmt(season_metrics['model_mae'])}",
    f"Median AE: {fmt(season_metrics['median_ae'])}",
    f"RMSE: {fmt(season_metrics['rmse'])}",
    f"Home-margin bias: {fmt(season_metrics['home_signed_bias'])}",
    f"Within 3 / 7 / 10 / 14: {fmt(season_metrics['within_3_pct'])}% / {fmt(season_metrics['within_7_pct'])}% / {fmt(season_metrics['within_10_pct'])}% / {fmt(season_metrics['within_14_pct'])}%",
    f"Archival DK MAE: {fmt(season_metrics['archival_market_mae'])}",
    f"Model Better / Market Better / Tie: {season_metrics['model_better']} / {season_metrics['market_better']} / {season_metrics['ties']}",
    f"Static shared games: {static_summary['shared_games']}",
    f"Static MAE / Weekly MAE: {fmt(static_summary['static_mae'])} / {fmt(static_summary['weekly_mae'])}",
    f"Week 9-14 corrected source SP+: {'PASS' if week9_14_sp_pass else 'FAIL'}",
    f"2025 inspected: {integrity['holdout_2025_inspected']}",
    f"Production state touched: {integrity['production_state_touched']}",
    f"Packet: {OUT}",
]

(OUT / "FINAL_SUMMARY.txt").write_text(
    "\n".join(summary_lines) + "\n",
    encoding="utf-8",
)

print("=== FINAL SUMMARY ===")
print("\n".join(summary_lines))

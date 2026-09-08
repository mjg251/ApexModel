import argparse
import csv
import hashlib
import json
import math
import os
from datetime import date, datetime
from pathlib import Path

import nflreadpy as nfl
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = PROJECT_ROOT / "models" / "nfl_power_ratings.csv"
BACKUP_PATH = PROJECT_ROOT / "models" / "nfl_power_ratings_previous.csv"
META_PATH = PROJECT_ROOT / "models" / "nfl_power_ratings_meta.json"

TARGET_SEASON = 2026
PRIOR_SEASON = TARGET_SEASON - 1

CURRENT_SEASON_WEIGHT = 1.00
PRIOR_SEASON_WEIGHT = 0.35

EPA_TO_POINTS_MULTIPLIER = 25.0
MODEL_VERSION = "v0.4"

ABBR_TO_FULL_NAME = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs",
    "LA": "Los Angeles Rams",
    "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE": "New England Patriots",
    "NO": "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
}


def to_pandas(frame):
    if hasattr(frame, "to_pandas"):
        return frame.to_pandas()

    return frame


def load_schedules(seasons: list[int]) -> pd.DataFrame:
    schedules = to_pandas(
        nfl.load_schedules(seasons)
    )

    return schedules.copy()


def resolve_target_week(
    schedules: pd.DataFrame,
    explicit_week: int | None = None,
) -> int:
    regular = schedules[
        (schedules["season"] == TARGET_SEASON)
        & (schedules["game_type"] == "REG")
    ].copy()

    if regular.empty:
        raise RuntimeError(
            f"No {TARGET_SEASON} NFL regular-season schedule rows found."
        )

    available_weeks = sorted(
        int(value)
        for value in regular["week"].dropna().unique()
    )

    if explicit_week is not None:
        if explicit_week not in available_weeks:
            raise RuntimeError(
                f"Invalid target week {explicit_week}. "
                f"Available weeks: {available_weeks}"
            )

        return explicit_week

    regular["game_date"] = pd.to_datetime(
        regular["gameday"],
        errors="coerce",
    ).dt.date

    today = date.today()

    upcoming = regular[
        regular["game_date"] >= today
    ].copy()

    if upcoming.empty:
        raise RuntimeError(
            "Unable to determine an active/upcoming NFL target week."
        )

    return int(upcoming["week"].min())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def validate_existing_rating_file(path: Path) -> None:
    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        rows = list(csv.DictReader(file))

    if len(rows) != 32:
        raise RuntimeError(
            f"Expected 32 NFL ratings in {path.name}, "
            f"found {len(rows)}."
        )

    teams = [
        row.get("team", "").strip()
        for row in rows
    ]

    if len(set(teams)) != 32:
        raise RuntimeError(
            f"Duplicate or missing NFL teams in {path.name}."
        )

    for row in rows:
        try:
            rating = float(row["rating"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"Invalid rating row in {path.name}: {row}"
            ) from error

        if not math.isfinite(rating):
            raise RuntimeError(
                f"Non-finite rating in {path.name}: {row}"
            )


def existing_snapshot_is_current(
    target_week: int,
) -> bool:
    if not OUTPUT_PATH.exists() or not META_PATH.exists():
        return False

    try:
        metadata = json.loads(
            META_PATH.read_text(
                encoding="utf-8",
            )
        )

        validate_existing_rating_file(
            OUTPUT_PATH
        )

        expected_hash = metadata.get(
            "ratings_sha256"
        )

        actual_hash = sha256_file(
            OUTPUT_PATH
        )

        return (
            metadata.get("sport") == "NFL"
            and metadata.get("model_version") == MODEL_VERSION
            and metadata.get("season") == TARGET_SEASON
            and metadata.get("target_week") == target_week
            and metadata.get("ratings_through_week")
            == target_week - 1
            and metadata.get("prior_season")
            == PRIOR_SEASON
            and metadata.get("current_season_weight")
            == CURRENT_SEASON_WEIGHT
            and metadata.get("prior_season_weight")
            == PRIOR_SEASON_WEIGHT
            and expected_hash == actual_hash
        )

    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return False


def filter_supported_teams(
    stats: pd.DataFrame,
) -> pd.DataFrame:
    return stats[
        stats["team"].isin(
            ABBR_TO_FULL_NAME.keys()
        )
        & stats["opponent_team"].isin(
            ABBR_TO_FULL_NAME.keys()
        )
    ].copy()


def validate_complete_game_rows(
    stats: pd.DataFrame,
    expected_game_ids: set[str],
    label: str,
) -> None:
    observed_game_ids = set(
        stats["game_id"].dropna().astype(str)
    )

    missing = sorted(
        expected_game_ids - observed_game_ids
    )

    if missing:
        raise RuntimeError(
            f"{label} source data is incomplete. "
            f"Missing {len(missing)} game(s): {missing}"
        )

    if not expected_game_ids:
        return

    counts = (
        stats[
            stats["game_id"]
            .astype(str)
            .isin(expected_game_ids)
        ]
        .groupby("game_id")
        .size()
    )

    invalid = {
        str(game_id): int(count)
        for game_id, count in counts.items()
        if int(count) != 2
    }

    if invalid:
        raise RuntimeError(
            f"{label} expected exactly two team-stat rows "
            f"per game. Invalid counts: {invalid}"
        )


def expected_regular_games(
    schedules: pd.DataFrame,
    season: int,
    before_week: int | None = None,
) -> pd.DataFrame:
    rows = schedules[
        (schedules["season"] == season)
        & (schedules["game_type"] == "REG")
    ].copy()

    if before_week is not None:
        rows = rows[
            rows["week"] < before_week
        ].copy()

    return rows


def load_rating_inputs(
    schedules: pd.DataFrame,
    target_week: int,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    int,
    int,
]:
    prior_stats = to_pandas(
        nfl.load_team_stats(
            [PRIOR_SEASON]
        )
    ).copy()

    prior_stats = filter_supported_teams(
        prior_stats
    )

    prior_stats = prior_stats[
        (prior_stats["season"] == PRIOR_SEASON)
        & (prior_stats["season_type"] == "REG")
    ].copy()

    prior_schedule = expected_regular_games(
        schedules=schedules,
        season=PRIOR_SEASON,
    )

    prior_expected_ids = set(
        prior_schedule["game_id"]
        .dropna()
        .astype(str)
    )

    validate_complete_game_rows(
        stats=prior_stats,
        expected_game_ids=prior_expected_ids,
        label=f"{PRIOR_SEASON} REG",
    )

    if target_week == 1:
        current_stats = prior_stats.iloc[0:0].copy()
        current_expected_ids: set[str] = set()

    else:
        current_schedule = expected_regular_games(
            schedules=schedules,
            season=TARGET_SEASON,
            before_week=target_week,
        )

        if (
            current_schedule["home_score"].isna().any()
            or current_schedule["away_score"].isna().any()
        ):
            incomplete = current_schedule[
                current_schedule["home_score"].isna()
                | current_schedule["away_score"].isna()
            ]

            game_ids = (
                incomplete["game_id"]
                .dropna()
                .astype(str)
                .tolist()
            )

            raise RuntimeError(
                f"Cannot build NFL Week {target_week} ratings. "
                f"Prior-week schedule is not fully final. "
                f"Incomplete game IDs: {game_ids}"
            )

        current_expected_ids = set(
            current_schedule["game_id"]
            .dropna()
            .astype(str)
        )

        try:
            current_stats = to_pandas(
                nfl.load_team_stats(
                    [TARGET_SEASON]
                )
            ).copy()

        except Exception as error:
            raise RuntimeError(
                f"Cannot build NFL Week {target_week} ratings. "
                f"Required {TARGET_SEASON} team-stat data "
                f"is unavailable."
            ) from error

        current_stats = filter_supported_teams(
            current_stats
        )

        current_stats = current_stats[
            (current_stats["season"] == TARGET_SEASON)
            & (current_stats["week"] < target_week)
            & (current_stats["season_type"] == "REG")
        ].copy()

        validate_complete_game_rows(
            stats=current_stats,
            expected_game_ids=current_expected_ids,
            label=(
                f"{TARGET_SEASON} through "
                f"Week {target_week - 1}"
            ),
        )

    return (
        prior_stats,
        current_stats,
        len(prior_expected_ids),
        len(current_expected_ids),
    )


def calculate_game_level_efficiency(
    stats: pd.DataFrame,
) -> pd.DataFrame:
    stats = stats.copy()

    stats["dropbacks"] = (
        stats["attempts"].fillna(0)
        + stats["sacks_suffered"].fillna(0)
    )

    stats["rushes"] = (
        stats["carries"].fillna(0)
    )

    stats["offensive_plays"] = (
        stats["dropbacks"]
        + stats["rushes"]
    )

    stats["offensive_epa"] = (
        stats["passing_epa"].fillna(0)
        + stats["rushing_epa"].fillna(0)
    )

    stats = stats[
        stats["offensive_plays"] > 0
    ].copy()

    stats["offensive_epa_per_play"] = (
        stats["offensive_epa"]
        / stats["offensive_plays"]
    )

    return stats


def calculate_team_ratings(
    prior_stats: pd.DataFrame,
    current_stats: pd.DataFrame,
) -> list[dict]:
    prior = calculate_game_level_efficiency(
        prior_stats
    )

    current = calculate_game_level_efficiency(
        current_stats
    )

    prior["weight"] = PRIOR_SEASON_WEIGHT
    current["weight"] = CURRENT_SEASON_WEIGHT

    available = pd.concat(
        [current, prior],
        ignore_index=True,
    )

    if available.empty:
        raise RuntimeError(
            "No NFL team-stat rows available for ratings."
        )

    offense = (
        available
        .groupby("team")
        .apply(
            lambda group: pd.Series(
                {
                    "offensive_epa_per_play": (
                        (
                            group[
                                "offensive_epa_per_play"
                            ]
                            * group["weight"]
                        ).sum()
                        / group["weight"].sum()
                    ),
                    "games": (
                        group["game_id"]
                        .nunique()
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    defense_allowed = (
        available
        .groupby("opponent_team")
        .apply(
            lambda group: pd.Series(
                {
                    "defensive_epa_per_play_allowed": (
                        (
                            group[
                                "offensive_epa_per_play"
                            ]
                            * group["weight"]
                        ).sum()
                        / group["weight"].sum()
                    )
                }
            ),
            include_groups=False,
        )
        .reset_index()
        .rename(
            columns={
                "opponent_team": "team"
            }
        )
    )

    ratings = offense.merge(
        defense_allowed,
        on="team",
        how="inner",
    )

    ratings["net_epa_per_play"] = (
        ratings[
            "offensive_epa_per_play"
        ]
        - ratings[
            "defensive_epa_per_play_allowed"
        ]
    )

    league_average_net = (
        ratings[
            "net_epa_per_play"
        ].mean()
    )

    ratings["rating"] = (
        (
            ratings[
                "net_epa_per_play"
            ]
            - league_average_net
        )
        * EPA_TO_POINTS_MULTIPLIER
    )

    ratings["rating"] = (
        ratings["rating"]
        .clip(
            lower=-7.0,
            upper=7.0,
        )
    )

    output_rows = []

    for _, row in ratings.iterrows():
        team_abbr = row["team"]

        if team_abbr not in ABBR_TO_FULL_NAME:
            continue

        output_rows.append(
            {
                "team": (
                    ABBR_TO_FULL_NAME[
                        team_abbr
                    ]
                ),
                "rating": round(
                    float(row["rating"]),
                    1,
                ),
                "offensive_epa_per_play": round(
                    float(
                        row[
                            "offensive_epa_per_play"
                        ]
                    ),
                    4,
                ),
                "defensive_epa_per_play_allowed": round(
                    float(
                        row[
                            "defensive_epa_per_play_allowed"
                        ]
                    ),
                    4,
                ),
                "net_epa_per_play": round(
                    float(
                        row[
                            "net_epa_per_play"
                        ]
                    ),
                    4,
                ),
                "games": int(
                    row["games"]
                ),
            }
        )

    if len(output_rows) != 32:
        found = sorted(
            row["team"]
            for row in output_rows
        )

        raise RuntimeError(
            f"Expected 32 NFL teams, found "
            f"{len(output_rows)}. Found: {found}"
        )

    return sorted(
        output_rows,
        key=lambda item: item["rating"],
        reverse=True,
    )


def write_candidate_ratings(
    ratings: list[dict],
    target_week: int,
) -> Path:
    candidate_path = OUTPUT_PATH.with_suffix(
        ".csv.tmp"
    )

    generated_at = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    with candidate_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        fieldnames = [
            "team",
            "rating",
            "source",
            "tier",
            "notes",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for row in ratings:
            writer.writerow(
                {
                    "team": row["team"],
                    "rating": row["rating"],
                    "source": (
                        "nflverse EPA-derived "
                        "team rating"
                    ),
                    "tier": "Model",
                    "notes": (
                        f"NFL v0.4 canonical weekly ratings; "
                        f"Target season: {TARGET_SEASON}; "
                        f"Target week: {target_week}; "
                        f"Ratings through week: "
                        f"{target_week - 1}; "
                        f"Current-season weight: "
                        f"{CURRENT_SEASON_WEIGHT}; "
                        f"Prior season: {PRIOR_SEASON}; "
                        f"Prior-season weight: "
                        f"{PRIOR_SEASON_WEIGHT}; "
                        f"Formula: offense EPA/play - "
                        f"defense EPA/play allowed, "
                        f"centered to league average, "
                        f"multiplied by "
                        f"{EPA_TO_POINTS_MULTIPLIER}; "
                        f"Off EPA/play: "
                        f"{row['offensive_epa_per_play']}; "
                        f"Def EPA/play allowed: "
                        f"{row['defensive_epa_per_play_allowed']}; "
                        f"Net EPA/play: "
                        f"{row['net_epa_per_play']}; "
                        f"Games: {row['games']}; "
                        f"Generated: {generated_at}"
                    ),
                }
            )

    validate_existing_rating_file(
        candidate_path
    )

    return candidate_path


def promote_snapshot(
    candidate_path: Path,
    target_week: int,
    prior_game_count: int,
    current_game_count: int,
) -> None:
    if OUTPUT_PATH.exists():
        BACKUP_PATH.write_text(
            OUTPUT_PATH.read_text(
                encoding="utf-8",
            ),
            encoding="utf-8",
        )

    candidate_hash = sha256_file(
        candidate_path
    )

    metadata = {
        "sport": "NFL",
        "model_version": MODEL_VERSION,
        "season": TARGET_SEASON,
        "target_week": target_week,
        "ratings_through_week": target_week - 1,
        "source": "nflverse weekly team stats",
        "prior_season": PRIOR_SEASON,
        "prior_season_weight": PRIOR_SEASON_WEIGHT,
        "current_season_weight": CURRENT_SEASON_WEIGHT,
        "prior_regular_season_games": prior_game_count,
        "current_regular_season_games": current_game_count,
        "generated_at": (
            datetime.now()
            .astimezone()
            .isoformat(
                timespec="seconds"
            )
        ),
        "ratings_sha256": candidate_hash,
    }

    meta_candidate = META_PATH.with_suffix(
        ".json.tmp"
    )

    meta_candidate.write_text(
        json.dumps(
            metadata,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        candidate_path,
        OUTPUT_PATH,
    )

    os.replace(
        meta_candidate,
        META_PATH,
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--target-week",
        type=int,
        default=None,
        help=(
            "Override automatic target-week detection. "
            "Primarily intended for validation/testing."
        ),
    )

    args = parser.parse_args()

    schedules = load_schedules(
        [PRIOR_SEASON, TARGET_SEASON]
    )

    target_week = resolve_target_week(
        schedules=schedules,
        explicit_week=args.target_week,
    )

    print(
        f"NFL v0.4 target week: "
        f"{TARGET_SEASON} Week {target_week}"
    )

    print(
        f"Required ratings cutoff: "
        f"through Week {target_week - 1}"
    )

    if existing_snapshot_is_current(
        target_week
    ):
        print(
            "NFL ratings snapshot is already "
            "current and validated."
        )
        print(
            f"Reusing: {OUTPUT_PATH}"
        )
        print(
            f"Metadata: {META_PATH}"
        )
        return

    (
        prior_stats,
        current_stats,
        prior_game_count,
        current_game_count,
    ) = load_rating_inputs(
        schedules=schedules,
        target_week=target_week,
    )

    ratings = calculate_team_ratings(
        prior_stats=prior_stats,
        current_stats=current_stats,
    )

    candidate_path = write_candidate_ratings(
        ratings=ratings,
        target_week=target_week,
    )

    promote_snapshot(
        candidate_path=candidate_path,
        target_week=target_week,
        prior_game_count=prior_game_count,
        current_game_count=current_game_count,
    )

    print()
    print(
        f"Wrote canonical NFL v0.4 "
        f"Week {target_week} ratings:"
    )
    print(OUTPUT_PATH)
    print()
    print(
        f"Ratings through Week: "
        f"{target_week - 1}"
    )
    print(
        f"Prior-season REG games: "
        f"{prior_game_count}"
    )
    print(
        f"Current-season REG games: "
        f"{current_game_count}"
    )
    print(
        f"Metadata: {META_PATH}"
    )

    print()
    print("Top 10:")

    for row in ratings[:10]:
        print(
            f"{row['team']}: "
            f"{row['rating']} "
            f"(net EPA/play "
            f"{row['net_epa_per_play']})"
        )

    print()
    print("Bottom 10:")

    for row in ratings[-10:]:
        print(
            f"{row['team']}: "
            f"{row['rating']} "
            f"(net EPA/play "
            f"{row['net_epa_per_play']})"
        )


if __name__ == "__main__":
    main()
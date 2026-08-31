import csv
from datetime import datetime
from pathlib import Path

import nflreadpy as nfl
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = PROJECT_ROOT / "models" / "nfl_power_ratings.csv"
BACKUP_PATH = PROJECT_ROOT / "models" / "nfl_power_ratings_previous.csv"

SEASONS = [2024, 2025]

EPA_TO_POINTS_MULTIPLIER = 25.0

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


def load_team_stats() -> pd.DataFrame:
    stats = nfl.load_team_stats(SEASONS)

    if hasattr(stats, "to_pandas"):
        stats = stats.to_pandas()

    stats = stats.copy()

    stats = stats[
        stats["team"].isin(ABBR_TO_FULL_NAME.keys())
        & stats["opponent_team"].isin(ABBR_TO_FULL_NAME.keys())
    ]

    stats = stats[
        stats["season_type"].isin(["REG", "POST"])
    ]

    return stats


def calculate_game_level_efficiency(stats: pd.DataFrame) -> pd.DataFrame:
    stats = stats.copy()

    stats["dropbacks"] = (
        stats["attempts"].fillna(0)
        + stats["sacks_suffered"].fillna(0)
    )

    stats["rushes"] = stats["carries"].fillna(0)

    stats["offensive_plays"] = stats["dropbacks"] + stats["rushes"]

    stats["offensive_epa"] = (
        stats["passing_epa"].fillna(0)
        + stats["rushing_epa"].fillna(0)
    )

    stats = stats[stats["offensive_plays"] > 0]

    stats["offensive_epa_per_play"] = (
        stats["offensive_epa"] / stats["offensive_plays"]
    )

    return stats


def calculate_team_ratings(stats: pd.DataFrame) -> list[dict]:
    game_efficiency = calculate_game_level_efficiency(stats)

    offense = (
        game_efficiency
        .groupby("team", as_index=False)
        .agg(
            offensive_epa_per_play=("offensive_epa_per_play", "mean"),
            games=("game_id", "nunique"),
        )
    )

    defense_allowed = (
        game_efficiency
        .groupby("opponent_team", as_index=False)
        .agg(
            defensive_epa_per_play_allowed=("offensive_epa_per_play", "mean"),
        )
        .rename(columns={"opponent_team": "team"})
    )

    ratings = offense.merge(
        defense_allowed,
        on="team",
        how="inner",
    )

    ratings["net_epa_per_play"] = (
        ratings["offensive_epa_per_play"]
        - ratings["defensive_epa_per_play_allowed"]
    )

    league_average_net = ratings["net_epa_per_play"].mean()

    ratings["centered_net_epa_per_play"] = (
        ratings["net_epa_per_play"] - league_average_net
    )

    ratings["rating"] = (
        ratings["centered_net_epa_per_play"] * EPA_TO_POINTS_MULTIPLIER
    )

    ratings["rating"] = ratings["rating"].clip(lower=-7.0, upper=7.0)

    output_rows = []

    for _, row in ratings.iterrows():
        team_abbr = row["team"]
        full_name = ABBR_TO_FULL_NAME[team_abbr]

        output_rows.append(
            {
                "team": full_name,
                "rating": round(float(row["rating"]), 1),
                "offensive_epa_per_play": round(
                    float(row["offensive_epa_per_play"]),
                    4,
                ),
                "defensive_epa_per_play_allowed": round(
                    float(row["defensive_epa_per_play_allowed"]),
                    4,
                ),
                "net_epa_per_play": round(
                    float(row["net_epa_per_play"]),
                    4,
                ),
                "games": int(row["games"]),
            }
        )

    if len(output_rows) != 32:
        found = sorted(row["team"] for row in output_rows)
        raise ValueError(
            f"Expected 32 NFL teams, found {len(output_rows)}. Found: {found}"
        )

    return sorted(output_rows, key=lambda item: item["rating"], reverse=True)


def write_ratings(ratings: list[dict]) -> None:
    if OUTPUT_PATH.exists():
        BACKUP_PATH.write_text(
            OUTPUT_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    fetched_at = datetime.now().strftime("%Y-%m-%d %I:%M %p")

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        fieldnames = [
            "team",
            "rating",
            "source",
            "tier",
            "notes",
        ]

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for row in ratings:
            writer.writerow(
                {
                    "team": row["team"],
                    "rating": row["rating"],
                    "source": "nflverse EPA-derived team rating",
                    "tier": "Model",
                    "notes": (
                        f"Seasons: {SEASONS}; "
                        f"Formula: offense EPA/play - defense EPA/play allowed, "
                        f"centered to league average, multiplied by "
                        f"{EPA_TO_POINTS_MULTIPLIER}; "
                        f"Off EPA/play: {row['offensive_epa_per_play']}; "
                        f"Def EPA/play allowed: "
                        f"{row['defensive_epa_per_play_allowed']}; "
                        f"Net EPA/play: {row['net_epa_per_play']}; "
                        f"Games: {row['games']}; "
                        f"Generated: {fetched_at}"
                    ),
                }
            )


def main() -> None:
    stats = load_team_stats()
    ratings = calculate_team_ratings(stats)
    write_ratings(ratings)

    print(f"Wrote {len(ratings)} NFL ratings to:")
    print(OUTPUT_PATH)
    print()
    print("Top 10:")
    for row in ratings[:10]:
        print(
            f"{row['team']}: {row['rating']} "
            f"(net EPA/play {row['net_epa_per_play']})"
        )
    print()
    print("Bottom 10:")
    for row in ratings[-10:]:
        print(
            f"{row['team']}: {row['rating']} "
            f"(net EPA/play {row['net_epa_per_play']})"
        )


if __name__ == "__main__":
    main()
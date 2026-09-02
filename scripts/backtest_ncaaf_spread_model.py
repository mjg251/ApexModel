import csv
import os
import sys
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.project_ncaaf_from_apex import (  # noqa: E402
    ACTIONABLE_EDGE_THRESHOLD,
    EXTREME_EDGE_NO_BET_THRESHOLD,
    HOME_FIELD_ADVANTAGE,
    VALUE_EDGE_THRESHOLD,
    classify_recommendation,
    load_team_mapping,
    normalize_team_name,
    team_should_be_excluded,
)


OUTPUT_DIR = PROJECT_ROOT / "outputs" / "backtests"
OUTPUT_PATH = OUTPUT_DIR / "ncaaf_spread_backtest_v0_6_edge_window.csv"

BACKTEST_SEASONS = [2022, 2023, 2024, 2025]
RATINGS_SEASONS = [season - 1 for season in BACKTEST_SEASONS]

CFBD_BASE_URL = "https://api.collegefootballdata.com"

PROVIDER = "DraftKings"
FLAT_SPREAD_PRICE = -110


def get_api_key() -> str:
    api_key = os.getenv("CFBD_API_KEY")

    if not api_key:
        raise RuntimeError("Missing CFBD_API_KEY environment variable.")

    return api_key


def cfbd_get(path: str, params: dict) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
    }

    response = requests.get(
        f"{CFBD_BASE_URL}{path}",
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def first_present_value(row: dict, keys: list[str]):
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]

    return None


def fetch_sp_ratings(year: int) -> dict[str, dict]:
    data = cfbd_get(
        "/ratings/sp",
        {
            "year": year,
        },
    )

    ratings = {}

    for row in data:
        team = row.get("team", "").strip()

        if not team:
            continue

        rating = first_present_value(
            row,
            [
                "rating",
                "overall",
                "overallRating",
                "sp",
                "spRating",
            ],
        )

        if rating is None and isinstance(row.get("ratings"), dict):
            rating = first_present_value(
                row["ratings"],
                [
                    "rating",
                    "overall",
                    "overallRating",
                    "sp",
                    "spRating",
                ],
            )

        if rating is None:
            continue

        try:
            rating_value = float(rating)
        except ValueError:
            continue

        ratings[team] = {
            "rating": rating_value,
            "source": f"CFBD SP+ {year}",
            "tier": "Historical",
            "notes": "Prior-year rating used for no-lookahead backtest approximation.",
        }

    return ratings


def fetch_lines_for_year(year: int) -> list[dict]:
    return cfbd_get(
        "/lines",
        {
            "year": year,
            "seasonType": "regular",
        },
    )


def select_provider_line(game: dict) -> dict | None:
    for line in game.get("lines", []):
        if line.get("provider") == PROVIDER and line.get("spread") is not None:
            return line

    return None


def project_home_margin(
    home_team: str,
    away_team: str,
    ratings: dict[str, dict],
) -> float:
    return (
        ratings[home_team]["rating"]
        - ratings[away_team]["rating"]
        + HOME_FIELD_ADVANTAGE
    )


def american_profit_for_one_unit(result: str) -> float:
    if result == "push":
        return 0.0

    if result == "loss":
        return -1.0

    # Use flat -110 spread pricing for the first NCAAF backtest.
    return round(100 / abs(FLAT_SPREAD_PRICE), 4)


def grade_spread_bet(
    selected_side: str,
    market_line: float,
    home_score: int,
    away_score: int,
) -> tuple[str, float]:
    if selected_side == "home":
        cover_margin = (home_score - away_score) + market_line
    else:
        cover_margin = (away_score - home_score) + market_line

    if cover_margin > 0:
        return "win", round(float(cover_margin), 1)

    if cover_margin < 0:
        return "loss", round(float(cover_margin), 1)

    return "push", 0.0


def recommend_units(edge_points: float) -> float:
    if edge_points >= EXTREME_EDGE_NO_BET_THRESHOLD:
        return 0.0

    if edge_points >= ACTIONABLE_EDGE_THRESHOLD:
        return 0.25

    return 0.0


def build_backtest_rows() -> list[dict]:
    team_mapping = load_team_mapping()

    ratings_by_backtest_season = {
        backtest_season: fetch_sp_ratings(backtest_season - 1)
        for backtest_season in BACKTEST_SEASONS
    }

    rows = []

    for season in BACKTEST_SEASONS:
        print(f"Fetching CFBD lines for {season}...")
        games = fetch_lines_for_year(season)
        ratings = ratings_by_backtest_season[season]

        for game in games:
            line = select_provider_line(game)

            if not line:
                continue

            if game.get("homeScore") is None or game.get("awayScore") is None:
                continue

            home_display = game.get("homeTeam", "").strip()
            away_display = game.get("awayTeam", "").strip()

            if not home_display or not away_display:
                continue

            home_team = normalize_team_name(
                team_name=home_display,
                team_mapping=team_mapping,
            )
            away_team = normalize_team_name(
                team_name=away_display,
                team_mapping=team_mapping,
            )

            home_excluded = team_should_be_excluded(
                display_team=home_display,
                mapped_team=home_team,
                team_mapping=team_mapping,
                ratings=ratings,
            )
            away_excluded = team_should_be_excluded(
                display_team=away_display,
                mapped_team=away_team,
                team_mapping=team_mapping,
                ratings=ratings,
            )

            if home_excluded or away_excluded:
                continue

            spread = float(line["spread"])

            # CFBD spread convention:
            # negative spread = home team favored
            # positive spread = home team underdog
            home_market_line = spread
            away_market_line = -spread

            projected_home_margin = project_home_margin(
                home_team=home_team,
                away_team=away_team,
                ratings=ratings,
            )

            home_model_line = -projected_home_margin
            away_model_line = projected_home_margin

            home_edge = home_market_line - home_model_line
            away_edge = away_market_line - away_model_line

            if home_edge >= away_edge:
                selected_side = "home"
                selected_team = home_team
                opponent_team = away_team
                market_line = home_market_line
                model_line = home_model_line
                edge_points = home_edge
            else:
                selected_side = "away"
                selected_team = away_team
                opponent_team = home_team
                market_line = away_market_line
                model_line = away_model_line
                edge_points = away_edge

            edge_points = round(max(0.0, float(edge_points)), 1)
            recommendation = classify_recommendation(edge_points)
            recommended_units = recommend_units(edge_points)

            home_score = int(game["homeScore"])
            away_score = int(game["awayScore"])

            ats_result, cover_margin = grade_spread_bet(
                selected_side=selected_side,
                market_line=market_line,
                home_score=home_score,
                away_score=away_score,
            )

            flat_profit_units = american_profit_for_one_unit(ats_result)

            recommended_profit_units = round(
                flat_profit_units * recommended_units,
                4,
            )

            rows.append(
                {
                    "season": season,
                    "rating_year": season - 1,
                    "week": game.get("week"),
                    "game_id": game.get("gameId"),
                    "away_team": away_team,
                    "home_team": home_team,
                    "selected_team": selected_team,
                    "opponent_team": opponent_team,
                    "selected_side": selected_side,
                    "provider": PROVIDER,
                    "market_line": round(float(market_line), 1),
                    "model_line": round(float(model_line), 1),
                    "edge_points": edge_points,
                    "recommendation": recommendation,
                    "recommended_units": recommended_units,
                    "home_rating": round(float(ratings[home_team]["rating"]), 2),
                    "away_rating": round(float(ratings[away_team]["rating"]), 2),
                    "projected_home_margin": round(float(projected_home_margin), 1),
                    "actual_home_margin": home_score - away_score,
                    "home_score": home_score,
                    "away_score": away_score,
                    "ats_result": ats_result,
                    "cover_margin": cover_margin,
                    "flat_profit_units": flat_profit_units,
                    "recommended_profit_units": recommended_profit_units,
                }
            )

    return rows


def write_output(rows: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict], label: str) -> None:
    if not rows:
        print()
        print(f"{label}: no rows")
        return

    wins = sum(1 for row in rows if row["ats_result"] == "win")
    losses = sum(1 for row in rows if row["ats_result"] == "loss")
    pushes = sum(1 for row in rows if row["ats_result"] == "push")

    decisions = wins + losses
    win_rate = wins / decisions if decisions else 0

    flat_profit = sum(float(row["flat_profit_units"]) for row in rows)
    flat_roi = flat_profit / len(rows) if rows else 0

    recommended_profit = sum(float(row["recommended_profit_units"]) for row in rows)
    recommended_risk = sum(float(row["recommended_units"]) for row in rows)
    recommended_roi = (
        recommended_profit / recommended_risk
        if recommended_risk
        else 0
    )

    average_edge = sum(float(row["edge_points"]) for row in rows) / len(rows)
    average_cover = sum(float(row["cover_margin"]) for row in rows) / len(rows)

    print()
    print(label)
    print("-" * len(label))
    print(f"Rows: {len(rows)}")
    print(f"ATS: {wins}-{losses}-{pushes}")
    print(f"Win Rate: {win_rate:.1%}")
    print(f"Avg Edge: {average_edge:.2f}")
    print(f"Avg Cover Margin: {average_cover:+.2f}")
    print(f"Flat Profit: {flat_profit:+.2f} units")
    print(f"Flat ROI: {flat_roi:+.1%}")
    print(f"Recommended Profit: {recommended_profit:+.2f} units")
    print(f"Recommended ROI: {recommended_roi:+.1%}")


def print_summaries(rows: list[dict]) -> None:
    recommended_rows = [
        row for row in rows
        if float(row["recommended_units"]) > 0
    ]

    print()
    print(f"Total modeled rows: {len(rows)}")
    print(f"Recommended v0.6 unit rows: {len(recommended_rows)}")

    summarize(recommended_rows, "All Recommended v0.6 Plays")

    for season in BACKTEST_SEASONS:
        season_rows = [
            row for row in recommended_rows
            if int(row["season"]) == season
        ]
        summarize(season_rows, f"Season {season}")

    buckets = [
        (
            "Edge 2.0 to 3.9",
            [
                row for row in rows
                if 2.0 <= float(row["edge_points"]) < 4.0
            ],
        ),
        (
            "Edge 4.0 to 4.9",
            [
                row for row in rows
                if 4.0 <= float(row["edge_points"]) < 5.0
            ],
        ),
        (
            "Edge 5.0 to 6.9",
            [
                row for row in rows
                if 5.0 <= float(row["edge_points"]) < 7.0
            ],
        ),
        (
            "Edge 7.0 to 9.9",
            [
                row for row in rows
                if 7.0 <= float(row["edge_points"]) < 10.0
            ],
        ),
        (
            "Edge 10.0+",
            [
                row for row in rows
                if float(row["edge_points"]) >= 10.0
            ],
        ),
    ]

    for label, bucket_rows in buckets:
        summarize(bucket_rows, label)

    favorites = [
        row for row in recommended_rows
        if float(row["market_line"]) < 0
    ]
    underdogs = [
        row for row in recommended_rows
        if float(row["market_line"]) > 0
    ]

    summarize(favorites, "Recommended Favorites")
    summarize(underdogs, "Recommended Underdogs")

    big_spread_rows = [
        row for row in recommended_rows
        if abs(float(row["market_line"])) >= 21.0
    ]

    summarize(big_spread_rows, "Recommended Spread 21+")


def main() -> None:
    rows = build_backtest_rows()
    write_output(rows)

    print()
    print(f"Backtest output: {OUTPUT_PATH}")

    print_summaries(rows)


if __name__ == "__main__":
    main()
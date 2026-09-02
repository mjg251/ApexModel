import csv
from pathlib import Path

import nflreadpy as nfl
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "backtests"
OUTPUT_PATH = OUTPUT_DIR / "nfl_spread_backtest_v0_1.csv"

BACKTEST_SEASONS = [2024, 2025]
DATA_SEASONS = [2023, 2024, 2025]

HOME_FIELD_ADVANTAGE = 1.5
EPA_TO_POINTS_MULTIPLIER = 25.0

VALUE_EDGE_THRESHOLD = 5.0
LEAN_EDGE_THRESHOLD = 3.0
WATCH_EDGE_THRESHOLD = 2.0


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    schedules = nfl.load_schedules(DATA_SEASONS)
    team_stats = nfl.load_team_stats(DATA_SEASONS)

    if hasattr(schedules, "to_pandas"):
        schedules = schedules.to_pandas()

    if hasattr(team_stats, "to_pandas"):
        team_stats = team_stats.to_pandas()

    schedules = schedules.copy()
    team_stats = team_stats.copy()

    schedules = schedules[
        (schedules["game_type"] == "REG")
        & schedules["season"].isin(BACKTEST_SEASONS)
        & schedules["home_score"].notna()
        & schedules["away_score"].notna()
        & schedules["spread_line"].notna()
        & schedules["home_spread_odds"].notna()
        & schedules["away_spread_odds"].notna()
    ]

    team_stats = team_stats[
        team_stats["season_type"].isin(["REG", "POST"])
    ].copy()

    return schedules, team_stats


def calculate_game_efficiency(stats: pd.DataFrame) -> pd.DataFrame:
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

    stats = stats[stats["offensive_plays"] > 0].copy()

    stats["offensive_epa_per_play"] = (
        stats["offensive_epa"] / stats["offensive_plays"]
    )

    return stats


def build_ratings_for_week(
    game_efficiency: pd.DataFrame,
    season: int,
    week: int,
) -> dict[str, float]:
    current_season_stats = game_efficiency[
        (game_efficiency["season"] == season)
        & (game_efficiency["week"] < week)
        & (game_efficiency["season_type"] == "REG")
    ].copy()

    prior_season_stats = game_efficiency[
        (game_efficiency["season"] == season - 1)
        & (game_efficiency["season_type"] == "REG")
    ].copy()

    current_season_stats["weight"] = 1.00
    prior_season_stats["weight"] = 0.35

    available_stats = pd.concat(
        [current_season_stats, prior_season_stats],
        ignore_index=True,
    )

    if available_stats.empty:
        return {}

    offense = (
        available_stats
        .groupby("team")
        .apply(
            lambda group: pd.Series(
                {
                    "offensive_epa_per_play": (
                        (group["offensive_epa_per_play"] * group["weight"]).sum()
                        / group["weight"].sum()
                    ),
                    "games": group["game_id"].nunique(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    defense_allowed = (
        available_stats
        .groupby("opponent_team")
        .apply(
            lambda group: pd.Series(
                {
                    "defensive_epa_per_play_allowed": (
                        (group["offensive_epa_per_play"] * group["weight"]).sum()
                        / group["weight"].sum()
                    )
                }
            ),
            include_groups=False,
        )
        .reset_index()
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

    ratings["rating"] = (
        (ratings["net_epa_per_play"] - league_average_net)
        * EPA_TO_POINTS_MULTIPLIER
    )

    ratings["rating"] = ratings["rating"].clip(lower=-7.0, upper=7.0)

    return {
        row["team"]: round(float(row["rating"]), 1)
        for _, row in ratings.iterrows()
    }


def classify_recommendation(edge_points: float) -> str:
    if edge_points >= VALUE_EDGE_THRESHOLD:
        return "Value"

    if edge_points >= LEAN_EDGE_THRESHOLD:
        return "Lean"

    if edge_points >= WATCH_EDGE_THRESHOLD:
        return "Watch"

    return "No Play"


def recommend_units(edge_points: float) -> float:
    if edge_points >= 6.0:
        return 0.50

    if edge_points >= 5.0:
        return 0.25

    return 0.0


def american_profit_for_one_unit(odds: int, result: str) -> float:
    if result == "push":
        return 0.0

    if result == "loss":
        return -1.0

    if odds < 0:
        return round(100 / abs(odds), 4)

    return round(odds / 100, 4)


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


def build_backtest_rows(
    schedules: pd.DataFrame,
    team_stats: pd.DataFrame,
) -> list[dict]:
    game_efficiency = calculate_game_efficiency(team_stats)

    rows = []

    schedules = schedules.sort_values(
        ["season", "week", "gameday", "gametime"]
    )

    for _, game in schedules.iterrows():
        season = int(game["season"])
        week = int(game["week"])

        ratings = build_ratings_for_week(
            game_efficiency=game_efficiency,
            season=season,
            week=week,
        )

        away_team = game["away_team"]
        home_team = game["home_team"]

        if away_team not in ratings or home_team not in ratings:
            continue

        home_field = 0.0 if game["location"] == "Neutral" else HOME_FIELD_ADVANTAGE

        projected_home_margin = (
            ratings[home_team]
            - ratings[away_team]
            + home_field
        )

        # nflverse spread_line convention:
        # positive spread_line means home team favored by that many points.
        # negative spread_line means away team favored by that many points.
        spread_line = float(game["spread_line"])

        home_market_line = -spread_line
        away_market_line = spread_line

        home_model_line = -projected_home_margin
        away_model_line = projected_home_margin

        home_edge = home_market_line - home_model_line
        away_edge = away_market_line - away_model_line

        if home_edge >= away_edge:
            selected_side = "home"
            selected_team = home_team
            opponent_team = away_team
            market_line = home_market_line
            market_odds = int(game["home_spread_odds"])
            model_line = home_model_line
            edge_points = home_edge
        else:
            selected_side = "away"
            selected_team = away_team
            opponent_team = home_team
            market_line = away_market_line
            market_odds = int(game["away_spread_odds"])
            model_line = away_model_line
            edge_points = away_edge

        edge_points = round(max(0.0, float(edge_points)), 1)
        recommendation = classify_recommendation(edge_points)
        recommended_units = recommend_units(edge_points)

        ats_result, cover_margin = grade_spread_bet(
            selected_side=selected_side,
            market_line=market_line,
            home_score=int(game["home_score"]),
            away_score=int(game["away_score"]),
        )

        flat_profit_units = american_profit_for_one_unit(
            odds=market_odds,
            result=ats_result,
        )

        recommended_profit_units = round(
            flat_profit_units * recommended_units,
            4,
        )

        rows.append(
            {
                "season": season,
                "week": week,
                "game_id": game["game_id"],
                "gameday": game["gameday"],
                "away_team": away_team,
                "home_team": home_team,
                "selected_team": selected_team,
                "opponent_team": opponent_team,
                "selected_side": selected_side,
                "market_line": round(float(market_line), 1),
                "market_odds": market_odds,
                "model_line": round(float(model_line), 1),
                "edge_points": edge_points,
                "recommendation": recommendation,
                "recommended_units": recommended_units,
                "home_rating": ratings[home_team],
                "away_rating": ratings[away_team],
                "projected_home_margin": round(float(projected_home_margin), 1),
                "actual_home_margin": int(game["home_score"]) - int(game["away_score"]),
                "home_score": int(game["home_score"]),
                "away_score": int(game["away_score"]),
                "ats_result": ats_result,
                "cover_margin": cover_margin,
                "flat_profit_units": flat_profit_units,
                "recommended_profit_units": recommended_profit_units,
            }
        )

    return rows


def summarize(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        print(f"{label}: no rows")
        return

    bets = df[df["recommended_units"] > 0].copy()

    if bets.empty:
        print(f"{label}: no model plays")
        return

    wins = int((bets["ats_result"] == "win").sum())
    losses = int((bets["ats_result"] == "loss").sum())
    pushes = int((bets["ats_result"] == "push").sum())

    decisions = wins + losses
    win_rate = wins / decisions if decisions else 0

    flat_profit = float(bets["flat_profit_units"].sum())
    flat_risk = len(bets)
    flat_roi = flat_profit / flat_risk if flat_risk else 0

    recommended_profit = float(bets["recommended_profit_units"].sum())
    recommended_risk = float(bets["recommended_units"].sum())
    recommended_roi = (
        recommended_profit / recommended_risk
        if recommended_risk
        else 0
    )

    average_edge = float(bets["edge_points"].mean())
    average_cover_margin = float(bets["cover_margin"].mean())

    print()
    print(label)
    print("-" * len(label))
    print(f"Bets: {len(bets)}")
    print(f"ATS: {wins}-{losses}-{pushes}")
    print(f"Win Rate: {win_rate:.1%}")
    print(f"Avg Edge: {average_edge:.2f}")
    print(f"Avg Cover Margin: {average_cover_margin:+.2f}")
    print(f"Flat Profit: {flat_profit:+.2f} units")
    print(f"Flat ROI: {flat_roi:+.1%}")
    print(f"Recommended Profit: {recommended_profit:+.2f} units")
    print(f"Recommended ROI: {recommended_roi:+.1%}")


def print_group_summaries(df: pd.DataFrame) -> None:
    summarize(df, "All Recommended Model Plays")

    for season in sorted(df["season"].unique()):
        summarize(
            df[df["season"] == season],
            f"Season {season}",
        )

    for recommendation in ["Value", "Lean", "Watch", "No Play"]:
        group = df[df["recommendation"] == recommendation]
        summarize(group, f"Recommendation: {recommendation}")

    buckets = [
        ("Edge 5.0 to 5.9", df[(df["edge_points"] >= 5.0) & (df["edge_points"] < 6.0)]),
        ("Edge 6.0+", df[df["edge_points"] >= 6.0]),
    ]

    for label, group in buckets:
        summarize(group, label)


def write_output(rows: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    schedules, team_stats = load_data()

    print(f"Loaded completed backtest games: {len(schedules)}")
    print(f"Loaded team-stat rows: {len(team_stats)}")

    rows = build_backtest_rows(
        schedules=schedules,
        team_stats=team_stats,
    )

    write_output(rows)

    df = pd.DataFrame(rows)

    print(f"Backtest rows written: {len(rows)}")
    print(f"Output: {OUTPUT_PATH}")

    print_group_summaries(df)


if __name__ == "__main__":
    main()
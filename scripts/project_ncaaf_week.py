import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RATINGS_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings.csv"
GAMES_PATH = PROJECT_ROOT / "data" / "ncaaf_upcoming_games.csv"

# Output directly into Apex so Apex can import it.
APEX_OUTPUT_PATH = Path("C:/Projects/Apex/sample_model_edges.csv")

HOME_FIELD_ADVANTAGE = 2.5
MIN_EDGE_FOR_PLAY = 2.0


def load_ratings() -> dict[str, float]:
    ratings = {}

    with RATINGS_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            team = row["team"].strip()
            rating = float(row["rating"])

            ratings[team] = rating

    return ratings


def load_games() -> list[dict]:
    games = []

    with GAMES_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            games.append(row)

    return games


def project_home_margin(
    home_team: str,
    away_team: str,
    ratings: dict[str, float],
) -> float:
    home_rating = ratings.get(home_team)
    away_rating = ratings.get(away_team)

    if home_rating is None:
        raise ValueError(f"Missing rating for home team: {home_team}")

    if away_rating is None:
        raise ValueError(f"Missing rating for away team: {away_team}")

    return home_rating - away_rating + HOME_FIELD_ADVANTAGE


def recommend_units(edge_points: float) -> float:
    if edge_points >= 7.0:
        return 0.75

    if edge_points >= 4.0:
        return 0.50

    return 0.25


def build_edge(row: dict, ratings: dict[str, float]) -> dict | None:
    sport = row["sport"].strip()
    event_date = row["event_date"].strip()
    event_time = row["event_time"].strip()
    away_team = row["away_team"].strip()
    home_team = row["home_team"].strip()
    book = row["book"].strip()

    market_home_spread = float(row["market_line"])
    market_odds = int(row["market_odds"])

    projected_home_margin = project_home_margin(
        home_team=home_team,
        away_team=away_team,
        ratings=ratings,
    )

    # Convert the home-team spread into expected home margin.
    # Example:
    # Missouri -37.5 means market expects Missouri by 37.5.
    # market_home_spread = -37.5
    # market_home_margin = 37.5
    market_home_margin = -market_home_spread

    edge_to_home = projected_home_margin - market_home_margin

    if abs(edge_to_home) < MIN_EDGE_FOR_PLAY:
        return None

    if edge_to_home > 0:
        selection = home_team
        model_line = -projected_home_margin
        edge_points = edge_to_home
        selection_market_line = market_home_spread
    else:
        selection = away_team
        model_line = projected_home_margin
        edge_points = abs(edge_to_home)

        # If home is -37.5, away side is +37.5.
        selection_market_line = -market_home_spread

    recommended_units = recommend_units(edge_points)

    event = f"{away_team} at {home_team}"

    return {
        "sport": sport,
        "event_date": event_date,
        "event_time": event_time,
        "event": event,
        "market": "Spread",
        "selection": selection,
        "book": book,
        "market_line": round(selection_market_line, 1),
        "market_odds": market_odds,
        "model_line": round(model_line, 1),
        "edge_points": round(edge_points, 1),
        "signal_source": "NCAAF Spread Model v0",
        "recommended_units": recommended_units,
    }


def write_edges(edges: list[dict]) -> None:
    APEX_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "sport",
        "event_date",
        "event_time",
        "event",
        "market",
        "selection",
        "book",
        "market_line",
        "market_odds",
        "model_line",
        "edge_points",
        "signal_source",
        "recommended_units",
    ]

    with APEX_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(edges)


def main() -> None:
    ratings = load_ratings()
    games = load_games()

    edges = []

    for game in games:
        edge = build_edge(game, ratings)

        if edge is not None:
            edges.append(edge)

    write_edges(edges)

    print(f"Wrote {len(edges)} model edges to:")
    print(APEX_OUTPUT_PATH)


if __name__ == "__main__":
    main()
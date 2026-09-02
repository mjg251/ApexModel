import csv
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RATINGS_PATH = PROJECT_ROOT / "models" / "nfl_power_ratings.csv"
APEX_DB_PATH = Path("C:/Projects/Apex/database/apex.db")
APEX_OUTPUT_PATH = Path("C:/Projects/Apex/sample_model_edges.csv")

MODEL_VERSION = "NFL Spread Model v0.4 Apex Slate - nflverse EPA Ratings"

HOME_FIELD_ADVANTAGE = 1.5

VALUE_EDGE_THRESHOLD = 5.0
LEAN_EDGE_THRESHOLD = 3.0
WATCH_EDGE_THRESHOLD = 2.00

LARGE_SPREAD_THRESHOLD = 7.0
VERY_LARGE_SPREAD_THRESHOLD = 10.0

APPROVED_BOOKS = {
    "Caesars",
    "DraftKings",
    "FanDuel",
    "BetMGM",
    "BetRivers",
    "Fanatics",
}


TEAM_ALIASES = {
    "Arizona Cardinals": "Arizona Cardinals",
    "Atlanta Falcons": "Atlanta Falcons",
    "Baltimore Ravens": "Baltimore Ravens",
    "Buffalo Bills": "Buffalo Bills",
    "Carolina Panthers": "Carolina Panthers",
    "Chicago Bears": "Chicago Bears",
    "Cincinnati Bengals": "Cincinnati Bengals",
    "Cleveland Browns": "Cleveland Browns",
    "Dallas Cowboys": "Dallas Cowboys",
    "Denver Broncos": "Denver Broncos",
    "Detroit Lions": "Detroit Lions",
    "Green Bay Packers": "Green Bay Packers",
    "Houston Texans": "Houston Texans",
    "Indianapolis Colts": "Indianapolis Colts",
    "Jacksonville Jaguars": "Jacksonville Jaguars",
    "Kansas City Chiefs": "Kansas City Chiefs",
    "Las Vegas Raiders": "Las Vegas Raiders",
    "Los Angeles Chargers": "Los Angeles Chargers",
    "Los Angeles Rams": "Los Angeles Rams",
    "Miami Dolphins": "Miami Dolphins",
    "Minnesota Vikings": "Minnesota Vikings",
    "New England Patriots": "New England Patriots",
    "New Orleans Saints": "New Orleans Saints",
    "New York Giants": "New York Giants",
    "New York Jets": "New York Jets",
    "Philadelphia Eagles": "Philadelphia Eagles",
    "Pittsburgh Steelers": "Pittsburgh Steelers",
    "San Francisco 49ers": "San Francisco 49ers",
    "Seattle Seahawks": "Seattle Seahawks",
    "Tampa Bay Buccaneers": "Tampa Bay Buccaneers",
    "Tennessee Titans": "Tennessee Titans",
    "Washington Commanders": "Washington Commanders",
}


def normalize_team_name(team_name: str) -> str:
    clean_name = team_name.strip()
    return TEAM_ALIASES.get(clean_name, clean_name)


def load_ratings() -> dict[str, dict]:
    ratings = {}

    with RATINGS_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            team = row["team"].strip()

            ratings[team] = {
                "rating": float(row["rating"]),
                "source": row.get("source", "Manual NFL power rating").strip(),
                "tier": row.get("tier", "").strip(),
                "notes": row.get("notes", "").strip(),
            }

    return ratings


def fetch_apex_nfl_spreads() -> list[dict]:
    connection = sqlite3.connect(APEX_DB_PATH)
    connection.row_factory = sqlite3.Row

    rows = connection.execute(
        """
        SELECT
            e.external_id,
            e.away_team,
            e.home_team,
            e.commence_time,
            o.sportsbook,
            o.selection,
            o.line,
            o.price
        FROM events e
        JOIN odds o
            ON o.event_external_id = e.external_id
        WHERE e.sport_key = 'americanfootball_nfl'
        AND o.market = 'spreads'
        ORDER BY
            e.commence_time,
            e.away_team,
            e.home_team,
            o.sportsbook,
            o.selection
        """
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def group_rows_by_event(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = {}

    for row in rows:
        grouped.setdefault(row["external_id"], []).append(row)

    return grouped


def parse_event_datetime(commence_time: str) -> tuple[str, str]:
    game_time = datetime.fromisoformat(
        commence_time.replace("Z", "+00:00")
    ).astimezone()

    event_date = game_time.strftime("%Y-%m-%d")
    event_time = game_time.strftime("%I:%M %p MT").lstrip("0")

    return event_date, event_time


def project_home_margin(
    home_team: str,
    away_team: str,
    ratings: dict[str, dict],
) -> float:
    home_rating_data = ratings.get(home_team)
    away_rating_data = ratings.get(away_team)

    if home_rating_data is None:
        raise ValueError(f"Missing rating for home team: {home_team}")

    if away_rating_data is None:
        raise ValueError(f"Missing rating for away team: {away_team}")

    home_rating = home_rating_data["rating"]
    away_rating = away_rating_data["rating"]

    return home_rating - away_rating + HOME_FIELD_ADVANTAGE


def classify_recommendation(edge_points: float) -> str:
    if edge_points >= VALUE_EDGE_THRESHOLD:
        return "Value"

    if edge_points >= LEAN_EDGE_THRESHOLD:
        return "Lean"

    if edge_points >= WATCH_EDGE_THRESHOLD:
        return "Watch"

    return "No Play"


def calculate_confidence_score(edge_points: float, market_line: float) -> int:
    score = 50

    score += min(int(edge_points * 6), 25)

    absolute_spread = abs(market_line)

    if absolute_spread >= VERY_LARGE_SPREAD_THRESHOLD:
        score -= 10
    elif absolute_spread >= LARGE_SPREAD_THRESHOLD:
        score -= 5

    return max(1, min(score, 100))


def recommend_units(edge_points: float) -> float:
    if edge_points >= 7.0:
        return 0.0

    if edge_points >= 6.0:
        return 0.25

    return 0.0


def apply_risk_guards(
    recommended_units: float,
    market_line: float,
    confidence_score: int,
) -> tuple[float, list[str]]:
    guard_notes = []
    adjusted_units = recommended_units
    absolute_spread = abs(market_line)

    if absolute_spread >= VERY_LARGE_SPREAD_THRESHOLD:
        adjusted_units = min(adjusted_units, 0.25)
        guard_notes.append("very large spread cap")

    elif absolute_spread >= LARGE_SPREAD_THRESHOLD:
        adjusted_units = min(adjusted_units, 0.50)
        guard_notes.append("large spread cap")

    if confidence_score < 55:
        adjusted_units = min(adjusted_units, 0.25)
        guard_notes.append("low confidence cap")

    return adjusted_units, guard_notes


def build_model_row_for_event(
    event_rows: list[dict],
    ratings: dict[str, dict],
) -> dict | None:
    first_row = event_rows[0]

    away_display = first_row["away_team"]
    home_display = first_row["home_team"]

    away_team = normalize_team_name(away_display)
    home_team = normalize_team_name(home_display)

    if away_team not in ratings or home_team not in ratings:
        print(
            "Skipping missing NFL rating:",
            f"{away_display} -> {away_team}",
            "|",
            f"{home_display} -> {home_team}",
        )
        return None

    projected_home_margin = project_home_margin(
        home_team=home_team,
        away_team=away_team,
        ratings=ratings,
    )

    candidate_rows = []

    for row in event_rows:
        sportsbook = row["sportsbook"]

        if sportsbook not in APPROVED_BOOKS:
            continue

        selection_display = row["selection"]
        selection_team = normalize_team_name(selection_display)

        if selection_team == home_team:
            model_line = -projected_home_margin
        elif selection_team == away_team:
            model_line = projected_home_margin
        else:
            continue

        market_line = float(row["line"])
        edge_points = market_line - model_line

        candidate_rows.append(
            {
                "row": row,
                "selection_display": selection_display,
                "market_line": market_line,
                "market_odds": int(row["price"]),
                "model_line": model_line,
                "edge_points": edge_points,
            }
        )

    if not candidate_rows:
        print("Skipping no approved book spread:", away_display, "at", home_display)
        return None

    best_candidate = max(
        candidate_rows,
        key=lambda item: (
            item["edge_points"],
            item["market_line"],
            item["market_odds"],
        ),
    )

    edge_points = max(0.0, best_candidate["edge_points"])
    recommendation = classify_recommendation(edge_points)

    confidence_score = calculate_confidence_score(
        edge_points=edge_points,
        market_line=best_candidate["market_line"],
    )

    raw_units = recommend_units(edge_points)

    recommended_units, guard_notes = apply_risk_guards(
        recommended_units=raw_units,
        market_line=best_candidate["market_line"],
        confidence_score=confidence_score,
    )

    if recommendation == "No Play":
        recommended_units = 0.0

    if edge_points >= 7.0:
        guard_notes.append("extreme edge no-bet guard")

    home_rating_data = ratings[home_team]
    away_rating_data = ratings[away_team]

    rating_context = (
        f"Home Rating: {home_rating_data['rating']}; "
        f"Away Rating: {away_rating_data['rating']}; "
        f"Home Source: {home_rating_data['source']}; "
        f"Away Source: {away_rating_data['source']}"
    )

    guard_context = ""

    if guard_notes:
        guard_context = " | Guards: " + ", ".join(guard_notes)

    event_date, event_time = parse_event_datetime(first_row["commence_time"])

    event = f"{away_display} at {home_display}"

    signal_source = (
        f"{MODEL_VERSION} | Recommendation: {recommendation} | "
        f"Confidence: {confidence_score} | "
        f"{rating_context}"
        f"{guard_context}"
    )

    return {
        "sport": "NFL",
        "event_date": event_date,
        "event_time": event_time,
        "event": event,
        "market": "Spread",
        "selection": best_candidate["selection_display"],
        "book": best_candidate["row"]["sportsbook"],
        "market_line": round(best_candidate["market_line"], 1),
        "market_odds": best_candidate["market_odds"],
        "model_line": round(best_candidate["model_line"], 1),
        "edge_points": round(edge_points, 1),
        "recommendation": recommendation,
        "confidence_score": confidence_score,
        "signal_source": signal_source,
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
        "recommendation",
        "confidence_score",
        "signal_source",
        "recommended_units",
    ]

    with APEX_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(edges)


def main() -> None:
    ratings = load_ratings()
    rows = fetch_apex_nfl_spreads()

    grouped_events = group_rows_by_event(rows)

    edges = []

    for event_rows in grouped_events.values():
        edge = build_model_row_for_event(
            event_rows=event_rows,
            ratings=ratings,
        )

        if edge is not None:
            edges.append(edge)

    edges.sort(
        key=lambda edge: (
            edge["event_date"],
            -edge["edge_points"],
            edge["event"],
        )
    )

    write_edges(edges)

    print(f"Wrote {len(edges)} NFL Apex-slate model rows to:")
    print(APEX_OUTPUT_PATH)


if __name__ == "__main__":
    main()
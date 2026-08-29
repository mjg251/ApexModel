import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RATINGS_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings.csv"
TEAM_MAPPING_PATH = PROJECT_ROOT / "models" / "ncaaf_team_mapping.csv"

APEX_DB_PATH = Path("C:/Projects/Apex/database/apex.db")
APEX_OUTPUT_PATH = Path("C:/Projects/Apex/sample_model_edges.csv")

MODEL_VERSION = "NCAAF Spread Model v0.4 Apex Slate"

HOME_FIELD_ADVANTAGE = 2.5

VALUE_EDGE_THRESHOLD = 4.0
LEAN_EDGE_THRESHOLD = 2.0
WATCH_EDGE_THRESHOLD = 1.0

LARGE_SPREAD_THRESHOLD = 28.0
VERY_LARGE_SPREAD_THRESHOLD = 35.0
FCS_MAX_UNITS = 0.25
LOW_CONFIDENCE_MAX_UNITS = 0.25

APPROVED_BOOKS = {
    "Caesars",
    "DraftKings",
    "FanDuel",
    "BetMGM",
    "BetRivers",
    "Fanatics",
}

TEAM_ALIASES = {
    "USC Trojans": "USC",
    "San Jose State Spartans": "San Jose State",

    "Missouri Tigers": "Missouri",
    "Arkansas-Pine Bluff Golden Lions": "Arkansas-Pine Bluff",

    "Utah Utes": "Utah",
    "Idaho Vandals": "Idaho",

    "Colorado State Rams": "Colorado State",
    "Colorado Buffaloes": "Colorado",

    "Penn State Nittany Lions": "Penn State",
    "Ohio State Buckeyes": "Ohio State",
    "Michigan Wolverines": "Michigan",
    "Oregon Ducks": "Oregon",
    "Oklahoma State Cowboys": "Oklahoma State",
    "Iowa State Cyclones": "Iowa State",
    "Iowa Hawkeyes": "Iowa",
    "Texas Longhorns": "Texas",
    "Oklahoma Sooners": "Oklahoma",

    "Georgia Bulldogs": "Georgia",
    "Arkansas Razorbacks": "Arkansas",
    "Alabama Crimson Tide": "Alabama",
    "LSU Tigers": "LSU",
    "Ole Miss Rebels": "Ole Miss",

    "Miami Hurricanes": "Miami",
    "Notre Dame Fighting Irish": "Notre Dame",

    "Clemson Tigers": "Clemson",
    "NC State Wolfpack": "NC State",
    "Indiana Hoosiers": "Indiana",
}

FCS_TEAMS = {
    "Arkansas-Pine Bluff",
    "Idaho",
}

MASCOT_SUFFIXES = [
    "Tar Heels",
    "Horned Frogs",
    "Wolfpack",
    "Cavaliers",
    "Gamecocks",
    "Bison",
    "Hornets",
    "Eagles",
    "Rainbow Warriors",
    "Cardinal",
    "Aggies",
    "Seminoles",
    "Tigers",
    "Rebels",
    "Minutemen",
    "Scarlet Knights",
    "Zips",
    "Demon Deacons",
    "Bulls",
    "Wildcats",
    "Knights",
    "Warriors",
    "Blue Hens",
    "Wolves",
    "Owls",
    "Yellow Jackets",
    "Golden Gophers",
    "Blazers",
    "Fighting Illini",
    "Sycamores",
    "Boilermakers",
    "Jayhawks",
    "Rockets",
    "Spartans",
    "Miners",
    "Sooners",
    "Bulldogs",
    "Pirates",
    "Crimson Tide",
    "Leopards",
    "Huskies",
    "Flames",
    "Dukes",
    "RedHawks",
    "Panthers",
    "Orange",
    "Mean Green",
    "Hoosiers",
    "Bobcats",
    "Cornhuskers",
    "Beavers",
    "Cougars",
    "Texans",
    "Falcons",
    "Golden Flashes",
    "Redhawks",
    "Penguins",
    "Rams",
    "Volunteers",
    "Mountaineers",
    "Midshipmen",
    "Green Wave",
    "Roadrunners",
    "Golden Hurricane",
    "Braves",
    "Monarchs",
    "Cowboys",
    "Governors",
    "Buccaneers",
    "Colonels",
    "Bearkats",
    "Jaguars",
    "Demons",
    "Warhawks",
    "Keydets",
    "Hokies",
    "Ragin Cajuns",
    "Jackrabbits",
    "Trailblazers",
    "Lakers",
    "Lumberjacks",
    "Aztecs",
    "Chippewas",
    "Lobos",
    "Delta Devils",
    "Sun Devils",
    "Bruins",
    "Hilltoppers",
    "Wolf Pack",
    "Nittany Lions",
    "Longhorns",
    "Razorbacks",
    "Bearcats",
    "49ers",
    "Paladins",
    "Thundering Herd",
    "Vaqueros",
    "Red Raiders",
    "Commodores",
    "Blue Raiders",
    "Utes",
    "Vandals",
    "Trojans",
    "Buckeyes",
    "Wolverines",
    "Hurricanes",
    "Fighting Irish",
]


def normalize_team_name(
    team_name: str,
    team_mapping: dict[str, dict],
) -> str:
    clean_name = team_name.strip()

    mapped_team = team_mapping.get(clean_name)

    if mapped_team and mapped_team["cfbd_team"]:
        return mapped_team["cfbd_team"]

    if clean_name in TEAM_ALIASES:
        return TEAM_ALIASES[clean_name]

    for suffix in MASCOT_SUFFIXES:
        suffix_text = f" {suffix}"

        if clean_name.endswith(suffix_text):
            stripped_name = clean_name[: -len(suffix_text)].strip()

            if stripped_name:
                return TEAM_ALIASES.get(stripped_name, stripped_name)

    return clean_name

def load_team_mapping() -> dict[str, dict]:
    if not TEAM_MAPPING_PATH.exists():
        return {}

    mapping = {}

    with TEAM_MAPPING_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            apex_team = row.get("apex_team", "").strip()
            cfbd_team = row.get("cfbd_team", "").strip()
            classification = row.get("classification", "").strip().lower()

            if not apex_team:
                continue

            mapping[apex_team] = {
                "cfbd_team": cfbd_team,
                "classification": classification,
            }

    return mapping


def load_ratings() -> dict[str, dict]:
    ratings = {}

    with RATINGS_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            team = row["team"].strip()

            ratings[team] = {
                "rating": float(row["rating"]),
                "source": row.get("source", "").strip(),
                "tier": row.get("tier", "").strip(),
                "notes": row.get("notes", "").strip(),
            }

    return ratings


def fetch_apex_ncaaf_spreads() -> list[dict]:
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
        WHERE e.sport_key = 'americanfootball_ncaaf'
        AND o.market = 'spreads'
        ORDER BY
            e.commence_time,
            e.away_team,
            e.home_team,
            o.sportsbook,
            o.selection
        """
    ).fetchall()

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


def calculate_confidence_score(
    edge_points: float,
    fcs_away: bool,
    fcs_home: bool,
) -> int:
    score = 50

    score += min(int(edge_points * 4), 25)

    if fcs_away or fcs_home:
        score -= 20

    if edge_points >= 10:
        score -= 5

    return max(1, min(score, 100))


def classify_recommendation(edge_points: float) -> str:
    if edge_points >= VALUE_EDGE_THRESHOLD:
        return "Value"

    if edge_points >= LEAN_EDGE_THRESHOLD:
        return "Lean"

    if edge_points >= WATCH_EDGE_THRESHOLD:
        return "Watch"

    return "No Play"


def recommend_units(edge_points: float) -> float:
    if edge_points >= 7.0:
        return 0.75

    if edge_points >= 4.0:
        return 0.50

    if edge_points >= 2.0:
        return 0.25

    return 0.0


def apply_risk_guards(
    recommended_units: float,
    market_line: float,
    confidence_score: int,
    fcs_away: bool,
    fcs_home: bool,
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

    if fcs_away or fcs_home:
        adjusted_units = min(adjusted_units, FCS_MAX_UNITS)
        guard_notes.append("FCS cap")

    if confidence_score < 50:
        adjusted_units = min(adjusted_units, LOW_CONFIDENCE_MAX_UNITS)
        guard_notes.append("low confidence cap")

    return adjusted_units, guard_notes


def american_odds_value(price: int) -> int:
    # Higher American odds are better for the bettor.
    # Example: -105 is better than -110, +110 is better than +100.
    return price


def build_model_row_for_event(
    event_rows: list[dict],
    ratings: dict[str, dict],
    team_mapping: dict[str, dict],
) -> dict | None:
    first_row = event_rows[0]

    away_display = first_row["away_team"]
    home_display = first_row["home_team"]

    away_team = normalize_team_name(
        team_name=away_display,
        team_mapping=team_mapping,
    )

    home_team = normalize_team_name(
        team_name=home_display,
        team_mapping=team_mapping,
    )

    away_classification = team_mapping.get(away_display, {}).get("classification", "")
    home_classification = team_mapping.get(home_display, {}).get("classification", "")

    away_is_fcs = away_classification == "fcs"
    home_is_fcs = home_classification == "fcs"

    if away_team not in ratings:
        ratings[away_team] = {
            "rating": -28.0 if away_is_fcs else -18.0,
            "source": "Fallback estimate",
            "tier": "Unrated FCS" if away_is_fcs else "Unrated Team",
            "notes": "No CFBD SP+ rating found",
        }

        print(f"Using fallback rating: {away_display} -> {away_team}")

    if home_team not in ratings:
        ratings[home_team] = {
            "rating": -28.0 if home_is_fcs else -18.0,
            "source": "Fallback estimate",
            "tier": "Unrated FCS" if home_is_fcs else "Unrated Team",
            "notes": "No CFBD SP+ rating found",
        }

        print(f"Using fallback rating: {home_display} -> {home_team}")

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
        selection_team = normalize_team_name(
            team_name=selection_display,
            team_mapping=team_mapping,
        )

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
                "selection_team": selection_team,
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

    # Pick the side/book with the highest modeled edge.
    # This still exports every game we can model, but picks the side the model prefers.
    best_candidate = max(
        candidate_rows,
        key=lambda item: (
            item["edge_points"],
            item["market_line"],
            american_odds_value(item["market_odds"]),
        ),
    )

    edge_points = max(0.0, best_candidate["edge_points"])
    recommendation = classify_recommendation(edge_points)

    fcs_away = away_team in FCS_TEAMS
    fcs_home = home_team in FCS_TEAMS

    confidence_score = calculate_confidence_score(
        edge_points=edge_points,
        fcs_away=fcs_away,
        fcs_home=fcs_home,
    )

    raw_units = recommend_units(edge_points)

    recommended_units, guard_notes = apply_risk_guards(
        recommended_units=raw_units,
        market_line=best_candidate["market_line"],
        confidence_score=confidence_score,
        fcs_away=fcs_away,
        fcs_home=fcs_home,
    )

    if recommendation == "No Play":
        recommended_units = 0.0

    home_rating_data = ratings[home_team]
    away_rating_data = ratings[away_team]

    rating_context = (
        f"Home Tier: {home_rating_data['tier']}; "
        f"Away Tier: {away_rating_data['tier']}; "
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
        "sport": "NCAAF",
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
    team_mapping = load_team_mapping()
    rows = fetch_apex_ncaaf_spreads()

    grouped_events = group_rows_by_event(rows)

    edges = []

    for event_rows in grouped_events.values():
        edge = build_model_row_for_event(
            event_rows=event_rows,
            ratings=ratings,
            team_mapping=team_mapping,
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

    print(f"Wrote {len(edges)} NCAAF Apex-slate model rows to:")
    print(APEX_OUTPUT_PATH)


if __name__ == "__main__":
    main()
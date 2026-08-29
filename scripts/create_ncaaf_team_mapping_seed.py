import csv
import sqlite3
from difflib import get_close_matches
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

APEX_DB_PATH = Path("C:/Projects/Apex/database/apex.db")
RATINGS_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings.csv"
OUTPUT_PATH = PROJECT_ROOT / "models" / "ncaaf_team_mapping.csv"


def load_rating_teams() -> list[str]:
    with RATINGS_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        return sorted(row["team"].strip() for row in reader)


def load_apex_teams() -> list[str]:
    connection = sqlite3.connect(APEX_DB_PATH)

    rows = connection.execute(
        """
        SELECT DISTINCT away_team AS team
        FROM events
        WHERE sport_key = 'americanfootball_ncaaf'

        UNION

        SELECT DISTINCT home_team AS team
        FROM events
        WHERE sport_key = 'americanfootball_ncaaf'

        ORDER BY team
        """
    ).fetchall()

    return [row[0].strip() for row in rows]


def simple_strip_name(team_name: str) -> str:
    suffixes = [
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
        "Bears",
        "Broncos",
        "Cardinals",
        "Badgers",
        "Mustangs",
        "Gators",
        "Golden Bears",
        "Black Bears",
        "Blue Devils",
        "Golden Eagles",
        "Red Wolves",
        "Bengals",
    ]

    clean = team_name.strip()

    for suffix in suffixes:
        suffix_text = f" {suffix}"

        if clean.endswith(suffix_text):
            return clean[: -len(suffix_text)].strip()

    return clean


def best_guess(apex_team: str, rating_teams: list[str]) -> str:
    stripped = simple_strip_name(apex_team)

    if stripped in rating_teams:
        return stripped

    close_matches = get_close_matches(
        stripped,
        rating_teams,
        n=1,
        cutoff=0.84,
    )

    if close_matches:
        return close_matches[0]

    return ""


def main() -> None:
    rating_teams = load_rating_teams()
    apex_teams = load_apex_teams()

    rows = []

    for apex_team in apex_teams:
        guess = best_guess(apex_team, rating_teams)

        rows.append(
            {
                "apex_team": apex_team,
                "cfbd_team": guess,
                "classification": "",
                "notes": "auto guess" if guess else "needs manual mapping",
            }
        )

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "apex_team",
                "cfbd_team",
                "classification",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    mapped_count = sum(1 for row in rows if row["cfbd_team"])
    unmapped_count = len(rows) - mapped_count

    print(f"Wrote {len(rows)} team mappings to:")
    print(OUTPUT_PATH)
    print(f"Mapped: {mapped_count}")
    print(f"Unmapped: {unmapped_count}")


if __name__ == "__main__":
    main()
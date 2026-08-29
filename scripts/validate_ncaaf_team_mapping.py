import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RATINGS_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings.csv"
MAPPING_PATH = PROJECT_ROOT / "models" / "ncaaf_team_mapping.csv"


def load_rating_teams() -> set[str]:
    with RATINGS_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        return {row["team"].strip() for row in reader}


def main() -> None:
    rating_teams = load_rating_teams()

    blank_mappings = []
    invalid_mappings = []
    valid_mappings = []

    with MAPPING_PATH.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            apex_team = row["apex_team"].strip()
            cfbd_team = row["cfbd_team"].strip()

            if not cfbd_team:
                blank_mappings.append(apex_team)
            elif cfbd_team not in rating_teams:
                invalid_mappings.append((apex_team, cfbd_team))
            else:
                valid_mappings.append((apex_team, cfbd_team))

    print(f"Valid mappings: {len(valid_mappings)}")
    print(f"Blank mappings: {len(blank_mappings)}")
    print(f"Invalid mappings: {len(invalid_mappings)}")
    print()

    if blank_mappings:
        print("BLANK MAPPINGS")
        print("-" * 60)
        for team in blank_mappings:
            print(team)
        print()

    if invalid_mappings:
        print("INVALID MAPPINGS")
        print("-" * 60)
        for apex_team, cfbd_team in invalid_mappings:
            print(f"{apex_team} -> {cfbd_team}")


if __name__ == "__main__":
    main()
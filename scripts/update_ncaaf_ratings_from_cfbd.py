import csv
import os
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings.csv"

CFBD_RATINGS_URL = "https://api.collegefootballdata.com/ratings/sp"

SEASON = 2026


def get_api_key() -> str:
    api_key = os.getenv("CFBD_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing CFBD_API_KEY environment variable. "
            "Set it with: setx CFBD_API_KEY \"YOUR_KEY_HERE\" "
            "then restart VS Code."
        )

    return api_key


def fetch_sp_ratings() -> list[dict]:
    api_key = get_api_key()

    response = requests.get(
        CFBD_RATINGS_URL,
        params={"year": SEASON},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected CFBD response: {data}")

    return data


def first_present_value(row: dict, keys: list[str]):
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]

    return None


def extract_team_rating(row: dict) -> tuple[str, float]:
    team = row.get("team")

    if not team:
        raise ValueError(f"Rating row missing team: {row}")

    rating = first_present_value(
        row,
        ["rating", "overall", "sp", "SP"],
    )

    if isinstance(rating, dict):
        rating = first_present_value(
            rating,
            ["rating", "overall", "value"],
        )

    if rating is None:
        raise ValueError(f"Rating row missing rating value: {row}")

    return str(team).strip(), float(rating)


def classify_tier(rating: float) -> str:
    if rating >= 18:
        return "Elite FBS"

    if rating >= 10:
        return "Ranked FBS"

    if rating >= 3:
        return "Solid FBS"

    if rating >= -3:
        return "Average FBS"

    if rating >= -10:
        return "Weak FBS"

    return "Low FBS"


def write_ratings(rows: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    output_rows = []

    for row in rows:
        try:
            team, rating = extract_team_rating(row)
        except ValueError as error:
            print("Skipping row:", error)
            continue

        output_rows.append(
            {
                "team": team,
                "rating": round(rating, 2),
                "source": f"CFBD SP+ {SEASON}",
                "tier": classify_tier(rating),
                "notes": "Pulled from CollegeFootballData ratings/sp",
            }
        )

    output_rows.sort(key=lambda item: item["rating"], reverse=True)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["team", "rating", "source", "tier", "notes"],
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {len(output_rows)} NCAAF ratings to:")
    print(OUTPUT_PATH)


def main() -> None:
    rows = fetch_sp_ratings()
    write_ratings(rows)


if __name__ == "__main__":
    main()
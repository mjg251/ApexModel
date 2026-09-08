import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings.csv"
BACKUP_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings_backup.csv"
META_PATH = PROJECT_ROOT / "models" / "ncaaf_power_ratings_meta.json"

CFBD_BASE_URL = "https://api.collegefootballdata.com"

SEASON = 2026
MODEL_VERSION = "v0.6"
EXPECTED_TEAM_COUNT = 139


def get_api_key() -> str:
    api_key = os.getenv("CFBD_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing CFBD_API_KEY environment variable."
        )

    return api_key


def cfbd_get(
    path: str,
    params: dict,
    max_attempts: int = 3,
) -> list[dict]:
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(
                f"{CFBD_BASE_URL}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {get_api_key()}",
                },
                timeout=30,
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                raise RuntimeError(
                    f"Unexpected CFBD response from "
                    f"{path}: {data}"
                )

            return data

        except (
            requests.Timeout,
            requests.ConnectionError,
        ) as error:
            last_error = error

            if attempt == max_attempts:
                break

            wait_seconds = attempt * 2

            print(
                f"CFBD request failed "
                f"(attempt {attempt}/{max_attempts}): "
                f"{type(error).__name__}. "
                f"Retrying in {wait_seconds}s..."
            )

            time.sleep(wait_seconds)

    raise RuntimeError(
        f"CFBD request failed after "
        f"{max_attempts} attempts: {path}"
    ) from last_error


def parse_cfbd_datetime(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def fetch_calendar() -> list[dict]:
    return cfbd_get(
        "/calendar",
        {"year": SEASON},
    )


def regular_calendar_rows(
    calendar: list[dict],
) -> list[dict]:
    rows = [
        row
        for row in calendar
        if row.get("season") == SEASON
        and row.get("seasonType") == "regular"
    ]

    if not rows:
        raise RuntimeError(
            f"No {SEASON} regular-season CFBD calendar rows found."
        )

    for row in rows:
        if (
            row.get("week") is None
            or not row.get("startDate")
            or not row.get("endDate")
        ):
            raise RuntimeError(
                f"Malformed CFBD calendar row: {row}"
            )

    return sorted(
        rows,
        key=lambda row: int(row["week"]),
    )


def resolve_target_week(
    calendar: list[dict],
    explicit_week: int | None = None,
) -> dict:
    regular = regular_calendar_rows(calendar)

    by_week = {
        int(row["week"]): row
        for row in regular
    }

    if explicit_week is not None:
        if explicit_week not in by_week:
            raise RuntimeError(
                f"Invalid NCAAF target week {explicit_week}. "
                f"Available weeks: {sorted(by_week)}"
            )

        return by_week[explicit_week]

    now = datetime.now(timezone.utc)

    first_row = regular[0]
    first_start = parse_cfbd_datetime(
        first_row["startDate"]
    )

    if now < first_start:
        return first_row

    for index, row in enumerate(regular):
        start = parse_cfbd_datetime(
            row["startDate"]
        )

        if index + 1 < len(regular):
            next_start = parse_cfbd_datetime(
                regular[index + 1]["startDate"]
            )

            if start <= now < next_start:
                return row

        else:
            end = parse_cfbd_datetime(
                row["endDate"]
            )

            if start <= now <= end:
                return row

    raise RuntimeError(
        "Current date is outside the 2026 NCAAF "
        "regular-season calendar."
    )


def verify_previous_week_complete(
    target_week: int,
) -> int:
    if target_week == 1:
        return 0

    prior_week = target_week - 1

    games = cfbd_get(
        "/games",
        {
            "year": SEASON,
            "week": prior_week,
            "seasonType": "regular",
            "classification": "fbs",
        },
    )

    if not games:
        raise RuntimeError(
            f"No CFBD FBS games returned for "
            f"{SEASON} Week {prior_week}."
        )

    malformed = [
        game
        for game in games
        if game.get("id") is None
        or game.get("week") is None
        or "completed" not in game
    ]

    if malformed:
        raise RuntimeError(
            f"Malformed CFBD game rows for "
            f"Week {prior_week}: {malformed[:5]}"
        )

    incomplete = [
        game
        for game in games
        if game.get("completed") is not True
    ]

    if incomplete:
        descriptions = []

        for game in incomplete:
            descriptions.append(
                f"{game.get('id')}: "
                f"{game.get('awayTeam')} at "
                f"{game.get('homeTeam')} "
                f"({game.get('startDate')})"
            )

        raise RuntimeError(
            f"Cannot build NCAAF Week {target_week} ratings. "
            f"Week {prior_week} is not fully complete. "
            f"Incomplete games: {descriptions}"
        )

    return len(games)


def fetch_sp_ratings() -> list[dict]:
    return cfbd_get(
        "/ratings/sp",
        {"year": SEASON},
    )


def first_present_value(
    row: dict,
    keys: list[str],
):
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]

    return None


def extract_team_rating(
    row: dict,
) -> tuple[str, float]:
    if row.get("year") != SEASON:
        raise RuntimeError(
            f"Unexpected SP+ season in row: {row}"
        )

    team = str(
        row.get("team", "")
    ).strip()

    if not team:
        raise RuntimeError(
            f"SP+ row missing team: {row}"
        )

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

    if rating is None and isinstance(
        row.get("ratings"),
        dict,
    ):
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
        raise RuntimeError(
            f"SP+ row missing rating: {row}"
        )

    try:
        rating_value = float(rating)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f"Invalid SP+ rating: {row}"
        ) from error

    if not math.isfinite(rating_value):
        raise RuntimeError(
            f"Non-finite SP+ rating: {row}"
        )

    return team, rating_value


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


def build_output_rows(
    source_rows: list[dict],
    target_week: int,
) -> list[dict]:
    if len(source_rows) != EXPECTED_TEAM_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_TEAM_COUNT} CFBD SP+ rows "
            f"for {SEASON}, received {len(source_rows)}."
        )

    output_rows = []
    seen_teams = set()

    for row in source_rows:
        team, rating = extract_team_rating(row)

        if team in seen_teams:
            raise RuntimeError(
                f"Duplicate CFBD SP+ team: {team}"
            )

        seen_teams.add(team)

        output_rows.append(
            {
                "team": team,
                "rating": round(rating, 2),
                "source": f"CFBD SP+ {SEASON}",
                "tier": classify_tier(rating),
                "notes": (
                    f"NCAAF v0.6 weekly production snapshot "
                    f"for target Week {target_week}; "
                    f"pulled from CollegeFootballData "
                    f"ratings/sp"
                ),
            }
        )

    if len(seen_teams) != EXPECTED_TEAM_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_TEAM_COUNT} unique teams, "
            f"found {len(seen_teams)}."
        )

    return sorted(
        output_rows,
        key=lambda item: item["rating"],
        reverse=True,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def source_payload_sha256(
    rows: list[dict],
) -> str:
    ordered = sorted(
        rows,
        key=lambda row: str(
            row.get("team", "")
        ),
    )

    serialized = json.dumps(
        ordered,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(
        serialized
    ).hexdigest()


def validate_rating_file(
    path: Path,
) -> None:
    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    if len(rows) != EXPECTED_TEAM_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_TEAM_COUNT} ratings "
            f"in {path.name}, found {len(rows)}."
        )

    teams = []

    for row in rows:
        team = row.get(
            "team",
            "",
        ).strip()

        if not team:
            raise RuntimeError(
                f"Blank team in {path.name}: {row}"
            )

        teams.append(team)

        try:
            rating = float(
                row["rating"]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                f"Invalid rating row in "
                f"{path.name}: {row}"
            ) from error

        if not math.isfinite(rating):
            raise RuntimeError(
                f"Non-finite rating in "
                f"{path.name}: {row}"
            )

        if not row.get(
            "source",
            "",
        ).strip():
            raise RuntimeError(
                f"Missing source in "
                f"{path.name}: {row}"
            )

    if len(set(teams)) != EXPECTED_TEAM_COUNT:
        raise RuntimeError(
            f"Duplicate teams in {path.name}."
        )


def existing_snapshot_is_current(
    target_week_row: dict,
) -> bool:
    if (
        not OUTPUT_PATH.exists()
        or not META_PATH.exists()
    ):
        return False

    try:
        metadata = json.loads(
            META_PATH.read_text(
                encoding="utf-8",
            )
        )

        validate_rating_file(
            OUTPUT_PATH
        )

        actual_hash = sha256_file(
            OUTPUT_PATH
        )

        return (
            metadata.get("sport") == "NCAAF"
            and metadata.get("model_version")
            == MODEL_VERSION
            and metadata.get("season") == SEASON
            and metadata.get("target_week")
            == int(target_week_row["week"])
            and metadata.get("calendar_start")
            == target_week_row["startDate"]
            and metadata.get("calendar_end")
            == target_week_row["endDate"]
            and metadata.get("row_count")
            == EXPECTED_TEAM_COUNT
            and metadata.get("ratings_sha256")
            == actual_hash
        )

    except (
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False


def write_candidate(
    output_rows: list[dict],
) -> Path:
    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidate = OUTPUT_PATH.with_suffix(
        ".csv.tmp"
    )

    try:
        with candidate.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "team",
                    "rating",
                    "source",
                    "tier",
                    "notes",
                ],
            )

            writer.writeheader()
            writer.writerows(output_rows)

        validate_rating_file(
            candidate
        )

    except Exception:
        candidate.unlink(
            missing_ok=True
        )
        raise

    return candidate


def promote_snapshot(
    candidate: Path,
    source_rows: list[dict],
    target_week_row: dict,
    previous_week_game_count: int,
) -> None:
    if OUTPUT_PATH.exists():
        shutil.copy2(
            OUTPUT_PATH,
            BACKUP_PATH,
        )

    candidate_hash = sha256_file(
        candidate
    )

    fetched_at = (
        datetime.now(timezone.utc)
        .astimezone()
        .isoformat(
            timespec="seconds"
        )
    )

    target_week = int(
        target_week_row["week"]
    )

    metadata = {
        "sport": "NCAAF",
        "model_version": MODEL_VERSION,
        "season": SEASON,
        "source": "CFBD SP+",
        "source_endpoint": "/ratings/sp",
        "target_week": target_week,
        "snapshot_for_target_week": target_week,
        "calendar_start": target_week_row[
            "startDate"
        ],
        "calendar_end": target_week_row[
            "endDate"
        ],
        "previous_week": (
            target_week - 1
            if target_week > 1
            else None
        ),
        "previous_week_completion_verified": (
            target_week == 1
            or previous_week_game_count > 0
        ),
        "previous_week_fbs_games_checked": (
            previous_week_game_count
        ),
        "provider_fetched_at": fetched_at,
        "row_count": EXPECTED_TEAM_COUNT,
        "source_payload_sha256": (
            source_payload_sha256(
                source_rows
            )
        ),
        "ratings_sha256": candidate_hash,
        "source_semantics": (
            "Latest CFBD SP+ snapshot fetched after "
            "the prior-week completion gate. "
            "CFBD SP+ does not expose through-week "
            "metadata."
        ),
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
        candidate,
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
            "Override automatic CFBD calendar "
            "target-week detection for validation."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Fetch and validate ratings without "
            "promoting the snapshot."
        ),
    )

    args = parser.parse_args()

    calendar = fetch_calendar()

    target_week_row = resolve_target_week(
        calendar=calendar,
        explicit_week=args.target_week,
    )

    target_week = int(
        target_week_row["week"]
    )

    print(
        f"NCAAF v0.6 target week: "
        f"{SEASON} Week {target_week}"
    )

    print(
        f"Calendar window: "
        f"{target_week_row['startDate']} "
        f"through "
        f"{target_week_row['endDate']}"
    )

    if (
        not args.dry_run
        and existing_snapshot_is_current(
            target_week_row
        )
    ):
        print(
            "NCAAF ratings snapshot is already "
            "current and validated."
        )
        print(
            f"Reusing: {OUTPUT_PATH}"
        )
        print(
            f"Metadata: {META_PATH}"
        )
        return

    previous_week_game_count = (
        verify_previous_week_complete(
            target_week
        )
    )

    if target_week > 1:
        print(
            f"Verified Week {target_week - 1} "
            f"complete: "
            f"{previous_week_game_count} "
            f"FBS-linked games."
        )
    else:
        print(
            "Week 1 has no prior-week "
            "completion requirement."
        )

    source_rows = fetch_sp_ratings()

    output_rows = build_output_rows(
        source_rows=source_rows,
        target_week=target_week,
    )

    candidate = write_candidate(
        output_rows
    )

    if args.dry_run:
        print()
        print(
            f"DRY RUN PASSED: "
            f"{len(output_rows)} validated "
            f"CFBD SP+ ratings."
        )

        print(
            f"Source payload SHA-256: "
            f"{source_payload_sha256(source_rows)}"
        )

        candidate.unlink(
            missing_ok=True
        )

        return

    promote_snapshot(
        candidate=candidate,
        source_rows=source_rows,
        target_week_row=target_week_row,
        previous_week_game_count=(
            previous_week_game_count
        ),
    )

    print()
    print(
        f"Wrote NCAAF v0.6 Week "
        f"{target_week} ratings snapshot:"
    )
    print(OUTPUT_PATH)

    print(
        f"Metadata: {META_PATH}"
    )

    print(
        f"Rows: {len(output_rows)}"
    )

    print()
    print("Top 10:")

    for row in output_rows[:10]:
        print(
            f"{row['team']}: "
            f"{row['rating']}"
        )


if __name__ == "__main__":
    main()
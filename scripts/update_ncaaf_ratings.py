import argparse
import csv
import io
import json
import math
import os
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

import update_ncaaf_ratings_from_cfbd as cfbd


CONNELLY_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1vwoVl-Dxy0es87Z9I1RTvFzr72Lb1fAkREfbLxbK-eg/"
    "export?format=xlsx"
)

SOURCE_NAME = "Bill Connelly official SP+"
SOURCE_LABEL = f"Bill Connelly SP+ {cfbd.SEASON}"

TEAM_ALIASES = {
    "Appalachian State": "App State",
    "Connecticut": "UConn",
    "Hawaii": "Hawai'i",
    "Miami-FL": "Miami",
    "Miami-OH": "Miami (OH)",
    "UL-Lafayette": "Louisiana",
    "UL-Monroe": "UL Monroe",
    "USF": "South Florida",
}


def column_number(cell_ref: str) -> int:
    letters = "".join(
        char for char in cell_ref
        if char.isalpha()
    )

    result = 0

    for char in letters.upper():
        result = result * 26 + ord(char) - 64

    return result


def fetch_connelly_ratings(
    target_week: int,
) -> list[dict]:
    response = requests.get(
        CONNELLY_URL,
        timeout=45,
    )
    response.raise_for_status()

    namespace = {
        "m": (
            "http://schemas.openxmlformats.org/"
            "spreadsheetml/2006/main"
        ),
        "r": (
            "http://schemas.openxmlformats.org/"
            "officeDocument/2006/relationships"
        ),
        "p": (
            "http://schemas.openxmlformats.org/"
            "package/2006/relationships"
        ),
    }

    with zipfile.ZipFile(
        io.BytesIO(response.content)
    ) as archive:
        shared = []

        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(
                archive.read(
                    "xl/sharedStrings.xml"
                )
            )

            for item in root.findall(
                "m:si",
                namespace,
            ):
                shared.append(
                    "".join(
                        node.text or ""
                        for node in item.findall(
                            ".//m:t",
                            namespace,
                        )
                    )
                )

        workbook = ET.fromstring(
            archive.read("xl/workbook.xml")
        )

        relationships = ET.fromstring(
            archive.read(
                "xl/_rels/workbook.xml.rels"
            )
        )

        relationship_map = {
            row.attrib["Id"]: row.attrib["Target"]
            for row in relationships.findall(
                "p:Relationship",
                namespace,
            )
        }

        wanted_sheet = f"FBS Week {target_week}"
        sheet_path = None

        for sheet in workbook.findall(
            "m:sheets/m:sheet",
            namespace,
        ):
            if sheet.attrib["name"] != wanted_sheet:
                continue

            relationship_id = sheet.attrib[
                "{"
                + namespace["r"]
                + "}id"
            ]

            target = relationship_map[
                relationship_id
            ]

            sheet_path = (
                "xl/"
                + target.lstrip("/").replace(
                    "xl/",
                    "",
                    1,
                )
            )
            break

        if sheet_path is None:
            raise RuntimeError(
                f"{wanted_sheet} is not available "
                "in the official SP+ workbook."
            )

        root = ET.fromstring(
            archive.read(sheet_path)
        )

        rows = root.findall(
            ".//m:sheetData/m:row",
            namespace,
        )

        if not rows:
            raise RuntimeError(
                f"{wanted_sheet} contains no rows."
            )

        def cell_value(cell):
            cell_type = cell.attrib.get("t")
            value = cell.find(
                "m:v",
                namespace,
            )

            if (
                cell_type == "s"
                and value is not None
            ):
                return shared[int(value.text)]

            if cell_type == "inlineStr":
                return "".join(
                    node.text or ""
                    for node in cell.findall(
                        ".//m:t",
                        namespace,
                    )
                )

            if value is None:
                return ""

            return value.text or ""

        header = {}

        for cell in rows[0].findall(
            "m:c",
            namespace,
        ):
            header[
                column_number(
                    cell.attrib.get("r", "")
                )
            ] = cell_value(cell).strip()

        team_columns = [
            column
            for column, name in header.items()
            if name == "Team"
        ]

        rating_columns = [
            column
            for column, name in header.items()
            if name == "SP+"
        ]

        if len(team_columns) != 1:
            raise RuntimeError(
                "Official workbook must contain "
                "exactly one Team column."
            )

        if len(rating_columns) != 1:
            raise RuntimeError(
                "Official workbook must contain "
                "exactly one SP+ column."
            )

        team_column = team_columns[0]
        rating_column = rating_columns[0]

        source_rows = []

        for row in rows[1:]:
            values = {}

            for cell in row.findall(
                "m:c",
                namespace,
            ):
                values[
                    column_number(
                        cell.attrib.get("r", "")
                    )
                ] = cell_value(cell).strip()

            team = values.get(
                team_column,
                "",
            )

            # The workbook exports San Jose State with a literal
            # question mark. Reuse Apex's existing canonical spelling
            # directly from the validated production ratings file.
            if team == "San Jos? State":
                with cfbd.OUTPUT_PATH.open(
                    "r",
                    newline="",
                    encoding="utf-8-sig",
                ) as canonical_file:
                    canonical_matches = [
                        str(row.get("team", "")).strip()
                        for row in csv.DictReader(canonical_file)
                        if str(
                            row.get("team", "")
                        ).strip().startswith("San Jos")
                        and str(
                            row.get("team", "")
                        ).strip().endswith(" State")
                    ]

                if len(canonical_matches) != 1:
                    raise RuntimeError(
                        "Unable to resolve canonical San Jose State name."
                    )

                team = canonical_matches[0]

            team = TEAM_ALIASES.get(
                team,
                team,
            )

            # Final canonicalization after aliases.
            if team in ("San Jose State", "San Jos? State"):
                with cfbd.OUTPUT_PATH.open(
                    "r",
                    newline="",
                    encoding="utf-8-sig",
                ) as canonical_file:
                    matches = [
                        str(row.get("team", "")).strip()
                        for row in csv.DictReader(canonical_file)
                        if str(row.get("team", "")).strip().startswith("San Jos")
                        and str(row.get("team", "")).strip().endswith(" State")
                    ]

                if len(matches) != 1:
                    raise RuntimeError(
                        "Unable to resolve canonical San Jose State name."
                    )

                team = matches[0]

            rating_text = values.get(
                rating_column,
                "",
            )

            if not team and not rating_text:
                continue

            if not team or not rating_text:
                raise RuntimeError(
                    "Official SP+ row is missing "
                    "team or rating."
                )

            try:
                rating = float(rating_text)
            except ValueError as error:
                raise RuntimeError(
                    f"Invalid SP+ rating for {team}: "
                    f"{rating_text}"
                ) from error

            if not math.isfinite(rating):
                raise RuntimeError(
                    f"Non-finite SP+ rating for "
                    f"{team}."
                )

            source_rows.append(
                {
                    "year": cfbd.SEASON,
                    "team": team,
                    "rating": rating,
                }
            )

    if (
        len(source_rows)
        != cfbd.EXPECTED_TEAM_COUNT
    ):
        raise RuntimeError(
            f"Expected "
            f"{cfbd.EXPECTED_TEAM_COUNT} "
            f"FBS teams in {wanted_sheet}; "
            f"received {len(source_rows)}."
        )

    return source_rows


def validate_team_compatibility(
    source_rows: list[dict],
) -> None:
    if not cfbd.OUTPUT_PATH.exists():
        return

    with cfbd.OUTPUT_PATH.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        existing = {
            str(row.get("team", "")).strip()
            for row in csv.DictReader(file)
            if str(
                row.get("team", "")
            ).strip()
            and str(
                row.get("team", "")
            ).strip() != "nationalAverages"
        }

    incoming = {
        str(row["team"]).strip()
        for row in source_rows
    }

    if existing != incoming:
        missing = sorted(
            existing - incoming
        )
        extra = sorted(
            incoming - existing
        )

        raise RuntimeError(
            "Official SP+ team names do not "
            "match the existing production "
            "ratings universe. "
            f"Missing: {missing[:8]}; "
            f"Extra: {extra[:8]}"
        )


def build_output_rows(
    source_rows: list[dict],
    target_week: int,
) -> list[dict]:
    output_rows = []
    seen = set()

    for row in source_rows:
        team = str(row["team"]).strip()
        rating = float(row["rating"])

        if team in seen:
            raise RuntimeError(
                f"Duplicate SP+ team: {team}"
            )

        seen.add(team)

        output_rows.append(
            {
                "team": team,
                "rating": round(rating, 2),
                "source": SOURCE_LABEL,
                "tier": cfbd.classify_tier(
                    rating
                ),
                "notes": (
                    "NCAAF v0.6 weekly production "
                    f"snapshot for target Week "
                    f"{target_week}; pulled from "
                    "Bill Connelly official 2026 "
                    "SP+ workbook"
                ),
            }
        )

    return output_rows


def promote_direct_snapshot(
    candidate: Path,
    source_rows: list[dict],
    target_week_row: dict,
    previous_week_game_count: int,
) -> None:
    candidate_hash = cfbd.sha256_file(
        candidate
    )

    if (
        cfbd.OUTPUT_PATH.exists()
        and cfbd.META_PATH.exists()
    ):
        try:
            metadata = json.loads(
                cfbd.META_PATH.read_text(
                    encoding="utf-8"
                )
            )

            cfbd.validate_rating_file(
                cfbd.OUTPUT_PATH
            )

            current_hash = cfbd.sha256_file(
                cfbd.OUTPUT_PATH
            )

            if (
                metadata.get("source")
                == SOURCE_NAME
                and metadata.get(
                    "target_week"
                )
                == int(
                    target_week_row["week"]
                )
                and current_hash
                == candidate_hash
            ):
                candidate.unlink(
                    missing_ok=True
                )

                print(
                    "NCAAF ratings snapshot is "
                    "already current and validated."
                )
                print(
                    f"Reusing: "
                    f"{cfbd.OUTPUT_PATH}"
                )
                return

        except Exception:
            pass

    if cfbd.OUTPUT_PATH.exists():
        shutil.copy2(
            cfbd.OUTPUT_PATH,
            cfbd.BACKUP_PATH,
        )

    target_week = int(
        target_week_row["week"]
    )

    fetched_at = (
        datetime.now(timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds")
    )

    metadata = {
        "sport": "NCAAF",
        "model_version": cfbd.MODEL_VERSION,
        "season": cfbd.SEASON,
        "source": SOURCE_NAME,
        "source_endpoint": CONNELLY_URL,
        "source_url": CONNELLY_URL,
        "target_week": target_week,
        "snapshot_for_target_week": (
            target_week
        ),
        "calendar_start": (
            target_week_row["startDate"]
        ),
        "calendar_end": (
            target_week_row["endDate"]
        ),
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
        "row_count": (
            cfbd.EXPECTED_TEAM_COUNT
        ),
        "source_payload_sha256": (
            cfbd.source_payload_sha256(
                source_rows
            )
        ),
        "ratings_sha256": candidate_hash,
        "source_semantics": (
            "Official Bill Connelly "
            f"week-specific FBS SP+ workbook "
            f"tab FBS Week {target_week}."
        ),
    }

    meta_candidate = (
        cfbd.META_PATH.with_suffix(
            ".json.tmp"
        )
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
        cfbd.OUTPUT_PATH,
    )

    os.replace(
        meta_candidate,
        cfbd.META_PATH,
    )

    print(
        f"Promoted official SP+ Week "
        f"{target_week} snapshot."
    )
    print(
        f"Ratings: {cfbd.OUTPUT_PATH}"
    )
    print(
        f"Metadata: {cfbd.META_PATH}"
    )


def run_cfbd_fallback(
    target_week: int,
    dry_run: bool,
) -> None:
    command = [
        sys.executable,
        str(
            Path(__file__).with_name(
                "update_ncaaf_ratings_from_cfbd.py"
            )
        ),
        "--target-week",
        str(target_week),
    ]

    if dry_run:
        command.append("--dry-run")

    subprocess.run(
        command,
        cwd=str(cfbd.PROJECT_ROOT),
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--target-week",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    calendar = cfbd.fetch_calendar()

    target_week_row = (
        cfbd.resolve_target_week(
            calendar=calendar,
            explicit_week=args.target_week,
        )
    )

    target_week = int(
        target_week_row["week"]
    )

    print(
        f"NCAAF v0.6 target week: "
        f"{cfbd.SEASON} Week {target_week}"
    )

    print(
        "Primary ratings source: "
        "Bill Connelly official SP+ workbook"
    )

    previous_week_game_count = (
        cfbd.verify_previous_week_complete(
            target_week
        )
    )

    try:
        source_rows = (
            fetch_connelly_ratings(
                target_week
            )
        )

        validate_team_compatibility(
            source_rows
        )

        output_rows = build_output_rows(
            source_rows,
            target_week,
        )

        candidate = cfbd.write_candidate(
            output_rows
        )

        if args.dry_run:
            candidate.unlink(
                missing_ok=True
            )

            print(
                "DRY RUN PASSED: official "
                f"FBS Week {target_week} SP+ "
                "snapshot validated."
            )
            return

        promote_direct_snapshot(
            candidate,
            source_rows,
            target_week_row,
            previous_week_game_count,
        )

    except Exception as error:
        print(
            "Official SP+ source unavailable "
            f"or invalid: {error}"
        )
        print(
            "Falling back to CFBD SP+."
        )

        run_cfbd_fallback(
            target_week,
            args.dry_run,
        )


if __name__ == "__main__":
    main()

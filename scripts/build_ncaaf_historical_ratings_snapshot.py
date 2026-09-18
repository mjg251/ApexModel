from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from scripts.ncaaf_replay_snapshot import (
    SNAPSHOT_FIELDS,
    calculate_snapshot_sha256,
    parse_timestamp,
    sha256_file,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build an immutable normalized historical NCAAF SP+ "
            "ratings snapshot for replay."
        )
    )
    parser.add_argument(
        "--input-csv",
        required=True,
        type=Path,
        help="Extracted source ratings CSV with team,rating columns.",
    )
    parser.add_argument(
        "--season",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--target-week",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--source",
        required=True,
    )
    parser.add_argument(
        "--source-label",
        required=True,
    )
    parser.add_argument(
        "--source-url",
        default="",
    )
    parser.add_argument(
        "--published-at",
        required=True,
        help="Actual publication/availability timestamp, ISO-8601 with timezone.",
    )
    parser.add_argument(
        "--safe-after",
        required=True,
        help=(
            "Conservative earliest timestamp at which this snapshot "
            "may be used, ISO-8601 with timezone."
        ),
    )
    parser.add_argument(
        "--source-artifact",
        type=Path,
        help="Saved original HTML/PDF/text/source artifact, if available.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New immutable snapshot directory. Must not already exist.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.output_dir.exists():
        raise RuntimeError(
            f"Refusing to overwrite existing snapshot directory: "
            f"{args.output_dir}"
        )

    published_at = parse_timestamp(
        args.published_at,
        "published_at",
    )
    safe_after = parse_timestamp(
        args.safe_after,
        "safe_after",
    )

    if safe_after < published_at:
        raise RuntimeError(
            "safe_after cannot precede published_at."
        )

    if not args.input_csv.exists():
        raise FileNotFoundError(args.input_csv)

    with args.input_csv.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        required = {"team", "rating"}

        if not required.issubset(reader.fieldnames or []):
            raise RuntimeError(
                "Input ratings CSV must contain team,rating."
            )

        source_rows = list(reader)

    if not source_rows:
        raise RuntimeError("Input ratings CSV contains no rows.")

    seen = set()
    rows = []

    for source_row in source_rows:
        team = str(source_row.get("team", "")).strip()
        rating = str(source_row.get("rating", "")).strip()

        if not team:
            raise RuntimeError(
                "Input ratings CSV contains a blank team."
            )

        if not rating:
            raise RuntimeError(
                f"Missing rating for {team}; values are never inferred."
            )

        if team in seen:
            raise RuntimeError(f"Duplicate team: {team}")

        seen.add(team)

        rows.append(
            {
                "season": args.season,
                "source": args.source.strip(),
                "source_label": args.source_label.strip(),
                "source_url": args.source_url.strip(),
                "published_at": published_at.isoformat(),
                "target_week": args.target_week,
                "safe_after": safe_after.isoformat(),
                "team": team,
                "rating": rating,
            }
        )

    ratings_sha256 = calculate_snapshot_sha256(rows)

    for row in rows:
        row["ratings_sha256"] = ratings_sha256

    rows.sort(
        key=lambda row: row["team"].casefold()
    )

    args.output_dir.mkdir(parents=True)
    normalized_path = args.output_dir / "normalized.csv"

    with normalized_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=SNAPSHOT_FIELDS,
        )
        writer.writeheader()
        writer.writerows(rows)

    source_artifact_path = None
    source_artifact_sha256 = None

    if args.source_artifact:
        if not args.source_artifact.exists():
            raise FileNotFoundError(
                args.source_artifact
            )

        source_dir = args.output_dir / "source"
        source_dir.mkdir()

        source_artifact_path = (
            source_dir / args.source_artifact.name
        )
        shutil.copy2(
            args.source_artifact,
            source_artifact_path,
        )
        source_artifact_sha256 = sha256_file(
            source_artifact_path
        )

    manifest = {
        "schema_version": 1,
        "sport": "NCAAF",
        "ratings_type": "SP+",
        "season": args.season,
        "target_week": args.target_week,
        "source": args.source.strip(),
        "source_label": args.source_label.strip(),
        "source_url": args.source_url.strip(),
        "published_at": published_at.isoformat(),
        "safe_after": safe_after.isoformat(),
        "ratings_sha256": ratings_sha256,
        "normalized_csv": "normalized.csv",
        "normalized_file_sha256": sha256_file(
            normalized_path
        ),
        "team_count": len(rows),
        "source_artifact": (
            str(source_artifact_path.relative_to(args.output_dir))
            if source_artifact_path
            else None
        ),
        "source_artifact_sha256": source_artifact_sha256,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "missing_values_inferred": False,
    }

    manifest_path = args.output_dir / "snapshot.json"
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Snapshot: {normalized_path}")
    print(f"Ratings SHA256: {ratings_sha256}")
    print(f"Teams: {len(rows)}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


SNAPSHOT_FIELDS = [
    "season",
    "source",
    "source_label",
    "source_url",
    "published_at",
    "target_week",
    "safe_after",
    "team",
    "rating",
    "ratings_sha256",
]


@dataclass(frozen=True)
class RatingsSnapshot:
    path: Path
    season: int
    source: str
    source_label: str
    source_url: str
    published_at: datetime
    target_week: int
    safe_after: datetime
    ratings_sha256: str
    ratings: dict[str, dict]
    row_count: int


def parse_timestamp(value: str, label: str) -> datetime:
    text = str(value or "").strip()

    if not text:
        raise ValueError(f"{label} is required.")

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"{label} must be an ISO-8601 timestamp with timezone: {text}"
        ) from error

    if parsed.tzinfo is None:
        raise ValueError(
            f"{label} must include a timezone offset or Z: {text}"
        )

    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _canonical_decimal(value) -> str:
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Invalid SP+ rating: {value}") from error

    if not decimal_value.is_finite():
        raise ValueError(f"Non-finite SP+ rating: {value}")

    if decimal_value == 0:
        return "0"

    return format(decimal_value.normalize(), "f")


def normalized_snapshot_rows(rows: list[dict]) -> list[dict]:
    normalized = []

    for row in rows:
        normalized.append(
            {
                "season": str(int(row["season"])),
                "source": str(row["source"]).strip(),
                "source_label": str(row["source_label"]).strip(),
                "source_url": str(row.get("source_url", "")).strip(),
                "published_at": str(row["published_at"]).strip(),
                "target_week": str(int(row["target_week"])),
                "safe_after": str(row["safe_after"]).strip(),
                "team": str(row["team"]).strip(),
                "rating": _canonical_decimal(row["rating"]),
            }
        )

    return sorted(
        normalized,
        key=lambda row: row["team"].casefold(),
    )


def calculate_snapshot_sha256(rows: list[dict]) -> str:
    canonical_rows = normalized_snapshot_rows(rows)
    payload = json.dumps(
        canonical_rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def load_ratings_snapshot(path: Path) -> RatingsSnapshot:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        missing = [
            field
            for field in SNAPSHOT_FIELDS
            if field not in (reader.fieldnames or [])
        ]

        if missing:
            raise ValueError(
                f"Ratings snapshot missing fields: {missing}"
            )

        rows = list(reader)

    if not rows:
        raise ValueError("Ratings snapshot contains no teams.")

    seasons = {int(row["season"]) for row in rows}
    target_weeks = {int(row["target_week"]) for row in rows}
    sources = {row["source"].strip() for row in rows}
    source_labels = {row["source_label"].strip() for row in rows}
    source_urls = {row.get("source_url", "").strip() for row in rows}
    published_values = {row["published_at"].strip() for row in rows}
    safe_after_values = {row["safe_after"].strip() for row in rows}
    stored_hashes = {row["ratings_sha256"].strip() for row in rows}

    uniform_sets = {
        "season": seasons,
        "target_week": target_weeks,
        "source": sources,
        "source_label": source_labels,
        "source_url": source_urls,
        "published_at": published_values,
        "safe_after": safe_after_values,
        "ratings_sha256": stored_hashes,
    }

    for label, values in uniform_sets.items():
        if len(values) != 1:
            raise ValueError(
                f"Ratings snapshot has inconsistent {label}: {values}"
            )

    season = next(iter(seasons))
    target_week = next(iter(target_weeks))
    source = next(iter(sources))
    source_label = next(iter(source_labels))
    source_url = next(iter(source_urls))
    published_text = next(iter(published_values))
    safe_after_text = next(iter(safe_after_values))
    stored_hash = next(iter(stored_hashes))

    if not source:
        raise ValueError("Ratings snapshot source is required.")

    if not source_label:
        raise ValueError("Ratings snapshot source_label is required.")

    published_at = parse_timestamp(
        published_text,
        "ratings published_at",
    )
    safe_after = parse_timestamp(
        safe_after_text,
        "ratings safe_after",
    )

    if safe_after < published_at:
        raise ValueError(
            "ratings safe_after cannot precede published_at."
        )

    calculated_hash = calculate_snapshot_sha256(rows)

    if calculated_hash != stored_hash:
        raise ValueError(
            "Ratings snapshot SHA256 mismatch: "
            f"stored={stored_hash} calculated={calculated_hash}"
        )

    ratings = {}

    for row in rows:
        team = row["team"].strip()

        if not team:
            raise ValueError("Ratings snapshot contains a blank team.")

        if team in ratings:
            raise ValueError(
                f"Duplicate team in ratings snapshot: {team}"
            )

        rating = float(row["rating"])

        if not math.isfinite(rating):
            raise ValueError(
                f"Non-finite rating for {team}: {row['rating']}"
            )

        ratings[team] = {
            "rating": rating,
            "source": source_label,
            "tier": "Historical weekly SP+ snapshot",
            "notes": (
                f"Replay snapshot {stored_hash[:12]} "
                f"target week {target_week}"
            ),
        }

    return RatingsSnapshot(
        path=path,
        season=season,
        source=source,
        source_label=source_label,
        source_url=source_url,
        published_at=published_at,
        target_week=target_week,
        safe_after=safe_after,
        ratings_sha256=stored_hash,
        ratings=ratings,
        row_count=len(rows),
    )

#!/usr/bin/env python3
r"""
Extract and normalize all 2023 FBS weekly SP+ vectors from Bill Connelly's
public workbook into replay-only source-discovery artifacts.

This does NOT create official replay snapshots yet; publication/safe-after
provenance is attached in the next phase.

Run from C:\Projects\ApexModel:
    py .\scripts\extract_2023_spplus_weekly_vectors.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XLSX = (
    ROOT
    / "data"
    / "replays"
    / "ncaaf_v0_6"
    / "source_discovery"
    / "bill_connelly_2023_spplus_public.xlsx"
)
ELIG = ROOT / "data" / "replays" / "ncaaf_v0_6" / "eligibility" / "2023.csv"
APPROVED_W5 = (
    ROOT
    / "data"
    / "replays"
    / "ncaaf_v0_6"
    / "ratings"
    / "2023"
    / "week_05"
    / "normalized.csv"
)
OUT = (
    ROOT
    / "data"
    / "replays"
    / "ncaaf_v0_6"
    / "source_discovery"
    / "2023_weekly_vectors"
)

M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"

ALIASES = {
    "Miami-FL": "Miami",
    "UL-Lafayette": "Louisiana",
    "Appalachian State": "App. St.",
    "Miami-OH": "Miami-OH",
    "San Jose State": "San Jose St.",
    "USF": "USF",
    "Hawaii": "Hawaii",
    "UL-Monroe": "ULM",
    "Connecticut": "UConn",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def col_index(ref: str) -> int:
    m = re.match(r"([A-Z]+)", ref or "")
    n = 0
    for ch in (m.group(1) if m else ""):
        n = n * 26 + ord(ch) - 64
    return n - 1


def shared_strings(z: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in z.namelist():
        return []
    root = ET.fromstring(z.read(path))
    return [
        "".join((t.text or "") for t in si.iter(f"{{{M}}}t"))
        for si in root.findall(f"{{{M}}}si")
    ]


def sheet_map(z: zipfile.ZipFile) -> dict[str, str]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{P}}}Relationship")
    }
    result = {}
    for s in wb.findall(f"{{{M}}}sheets/{{{M}}}sheet"):
        target = targets[s.attrib[f"{{{R}}}id"]].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        result[s.attrib["name"]] = target
    return result


def read_sheet(z: zipfile.ZipFile, target: str, ss: list[str]) -> list[list[str]]:
    root = ET.fromstring(z.read(target))
    result = []
    for row in root.findall(f"{{{M}}}sheetData/{{{M}}}row"):
        vals = {}
        for c in row.findall(f"{{{M}}}c"):
            idx = col_index(c.attrib.get("r", ""))
            typ = c.attrib.get("t")
            v = c.find(f"{{{M}}}v")
            value = "" if v is None else (v.text or "")
            if typ == "s" and value:
                value = ss[int(value)]
            elif typ == "inlineStr":
                t = c.find(f"{{{M}}}is/{{{M}}}t")
                value = "" if t is None else (t.text or "")
            vals[idx] = value
        if vals:
            result.append([vals.get(i, "") for i in range(max(vals) + 1)])
    return result


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    for path in (XLSX, ELIG, APPROVED_W5):
        if not path.exists():
            raise SystemExit(f"Missing required input: {path}")

    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite existing extraction: {OUT}")

    eligibility = {}
    with ELIG.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            eligibility[r["display_team"].strip()] = r["model_team"].strip()

    approved_w5 = {}
    with APPROVED_W5.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            approved_w5[r["team"].strip()] = float(r["rating"])

    tmp = OUT.with_name(OUT.name + ".__tmp__")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    manifest = {
        "artifact_type": "2023_spplus_weekly_vector_extraction",
        "source_workbook": str(XLSX),
        "source_workbook_sha256": sha256_file(XLSX),
        "source_workbook_bytes": XLSX.stat().st_size,
        "season": 2023,
        "weeks": {},
        "production_state_written": False,
        "holdout_2025_inspected": False,
    }

    with zipfile.ZipFile(XLSX) as z:
        ss = shared_strings(z)
        sheets = sheet_map(z)

        for week in range(1, 15):
            tab_name = f"FBS week {week}"
            if tab_name not in sheets:
                raise RuntimeError(f"Missing worksheet: {tab_name}")

            tab = read_sheet(z, sheets[tab_name], ss)
            header = [str(value).strip() for value in tab[0]]
            sp_columns = [
                idx for idx, value in enumerate(header)
                if value == "SP+"
            ]
            if len(sp_columns) != 1:
                raise RuntimeError(
                    f"{tab_name}: expected exactly one SP+ header; "
                    f"found {len(sp_columns)}"
                )
            rating_col = sp_columns[0]

            source_rows = []
            normalized = []
            seen_model = set()
            unresolved = []

            for row in tab[1:]:
                if len(row) <= rating_col:
                    continue
                source_team = str(row[0]).strip()
                rating_raw = str(row[rating_col]).strip()
                if not source_team or not rating_raw:
                    continue
                try:
                    rating = float(rating_raw)
                except ValueError:
                    continue

                if source_team in ALIASES:
                    model_team = ALIASES[source_team]
                    resolution = "explicit_workbook_alias"
                elif source_team in eligibility:
                    model_team = eligibility[source_team]
                    resolution = "2023_eligibility"
                else:
                    unresolved.append(source_team)
                    continue

                if model_team in seen_model:
                    raise RuntimeError(
                        f"Week {week}: duplicate normalized team {model_team!r}"
                    )
                seen_model.add(model_team)

                source_rows.append(
                    {
                        "workbook_team": source_team,
                        "model_team": model_team,
                        "rating": f"{rating:.1f}",
                        "resolution": resolution,
                    }
                )
                normalized.append(
                    {
                        "team": model_team,
                        "rating": f"{rating:.1f}",
                    }
                )

            if unresolved:
                raise RuntimeError(f"Week {week}: unresolved teams: {unresolved}")
            if len(normalized) != 133:
                raise RuntimeError(
                    f"Week {week}: expected 133 normalized teams, got {len(normalized)}"
                )

            normalized.sort(key=lambda r: r["team"])
            source_rows.sort(key=lambda r: r["model_team"])

            norm_path = tmp / f"week_{week:02d}_normalized.csv"
            map_path = tmp / f"week_{week:02d}_source_map.csv"
            write_csv(norm_path, normalized, ["team", "rating"])
            write_csv(
                map_path,
                source_rows,
                ["workbook_team", "model_team", "rating", "resolution"],
            )

            if week == 5:
                generated = {r["team"]: float(r["rating"]) for r in normalized}
                if set(generated) != set(approved_w5):
                    raise RuntimeError(
                        "Week 5 generated team set differs from approved snapshot."
                    )
                mismatches = [
                    (team, generated[team], approved_w5[team])
                    for team in sorted(generated)
                    if abs(generated[team] - approved_w5[team]) > 1e-9
                ]
                if mismatches:
                    raise RuntimeError(
                        f"Week 5 differs from approved snapshot: {mismatches[:10]}"
                    )

            manifest["weeks"][str(week)] = {
                "worksheet": tab_name,
                "team_count": len(normalized),
                "unresolved_count": 0,
                "normalized_sha256": sha256_file(norm_path),
                "source_map_sha256": sha256_file(map_path),
                "week5_approved_vector_match": True if week == 5 else None,
            }

            print(
                f"Week {week:02d}: teams=133 unresolved=0 "
                + ("approved_week5_match=PASS" if week == 5 else "PASS")
            )

    (tmp / "extraction_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.rename(OUT)

    print()
    print("ALL 14 WEEKLY VECTORS EXTRACTED: True")
    print("Week 5 approved vector match: True")
    print(f"Output: {OUT}")
    print("Production state touched: False")
    print("2025 inspected: False")


if __name__ == "__main__":
    main()

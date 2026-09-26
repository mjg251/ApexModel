#!/usr/bin/env python3
r"""
Inspect Bill Connelly's public 2023 SP+ Google Sheet without touching production state.

Downloads the published workbook into a replay-only source-discovery directory,
then lists every worksheet/tab and its basic dimensions using only the Python stdlib.

Run from C:\Projects\ApexModel:
    py .\scripts\inspect_2023_spplus_public_sheet.py
"""

from __future__ import annotations

import re
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "replays" / "ncaaf_v0_6" / "source_discovery"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SHEET_ID = "2PACX-1vRh9Slymcisd5-uEIvAD4zjGkJ7aeARseChhne-HdpyQeQiTSJeZD0WfyuG40O5S7Z20wz1XLYSUDUj"
XLSX_URL = f"https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?output=xlsx"
HTML_URL = f"https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pubhtml"

XLSX_PATH = OUT_DIR / "bill_connelly_2023_spplus_public.xlsx"
HTML_PATH = OUT_DIR / "bill_connelly_2023_spplus_public.html"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ApexModel-Historical-Replay/1.0"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read()


def col_num(cell_ref: str) -> int:
    m = re.match(r"([A-Z]+)", cell_ref)
    if not m:
        return 0
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n


def list_xlsx_sheets(path: Path) -> list[tuple[str, str, int, int]]:
    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "p": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall("p:Relationship", ns)
        }

        out = []
        for sheet in wb.findall("m:sheets/m:sheet", ns):
            name = sheet.attrib["name"]
            rid = sheet.attrib[f"{{{ns['r']}}}id"]
            target = targets[rid].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            xml = ET.fromstring(z.read(target))
            dim = xml.find("m:dimension", ns)
            ref = dim.attrib.get("ref", "") if dim is not None else ""
            max_row = 0
            max_col = 0
            for row in xml.findall("m:sheetData/m:row", ns):
                max_row = max(max_row, int(row.attrib.get("r", "0")))
                for cell in row.findall("m:c", ns):
                    max_col = max(max_col, col_num(cell.attrib.get("r", "")))
            out.append((name, ref, max_row, max_col))
        return out


def main() -> None:
    print("Fetching Bill Connelly public 2023 SP+ workbook...")
    data = fetch(XLSX_URL)
    if not data.startswith(b"PK"):
        HTML_PATH.write_bytes(data)
        raise SystemExit(
            f"Published XLSX endpoint did not return an XLSX file. "
            f"Saved response to {HTML_PATH}"
        )

    XLSX_PATH.write_bytes(data)
    print(f"Saved: {XLSX_PATH}")
    print(f"Bytes: {len(data):,}")
    print()

    sheets = list_xlsx_sheets(XLSX_PATH)
    print(f"Worksheet count: {len(sheets)}")
    print()
    for idx, (name, ref, rows, cols) in enumerate(sheets, 1):
        print(f"{idx:02d}. {name!r} | range={ref or 'unknown'} | rows={rows} | cols={cols}")

    print()
    print("Production state touched: False")
    print("2025 inspected: False")


if __name__ == "__main__":
    main()

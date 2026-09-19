import csv
import json
import zipfile
from pathlib import Path

from scripts.inspect_2023_spplus_fbs_tabs import shared, smap, readtab

ROOT = Path("data/replays/ncaaf_v0_6")
DISC = ROOT / "source_discovery"
XLSX = DISC / "bill_connelly_2023_spplus_public.xlsx"
VECTORS = DISC / "2023_weekly_vectors"
OUT = VECTORS / "schema_provenance.json"

EXPECTED_TEAMS = 133

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

result = {
    "artifact_type": "2023_spplus_historical_extractor_regression",
    "season": 2023,
    "expected_team_count": EXPECTED_TEAMS,
    "status": "PASS",
    "weeks": {},
}

with zipfile.ZipFile(XLSX) as z:
    ss = shared(z)
    sheets = smap(z)

    for week in range(1, 15):
        sheet = f"FBS week {week}"
        tab = readtab(z, sheets[sheet], ss)

        header = [str(v).strip() for v in tab[0]]

        sp_cols = [i for i, v in enumerate(header) if v == "SP+"]
        if len(sp_cols) != 1:
            raise RuntimeError(
                f"{sheet}: expected exactly one SP+ header; found {len(sp_cols)}"
            )

        sp_col = sp_cols[0]

        rank_col = None
        if sp_col + 1 < len(header) and header[sp_col + 1] == "Rk":
            rank_col = sp_col + 1

        normalized_rows = read_csv(
            VECTORS / f"week_{week:02d}_normalized.csv"
        )
        source_rows = read_csv(
            VECTORS / f"week_{week:02d}_source_map.csv"
        )

        if len(normalized_rows) != EXPECTED_TEAMS:
            raise RuntimeError(
                f"Week {week}: normalized team count "
                f"{len(normalized_rows)} != {EXPECTED_TEAMS}"
            )

        if len(source_rows) != EXPECTED_TEAMS:
            raise RuntimeError(
                f"Week {week}: source-map team count "
                f"{len(source_rows)} != {EXPECTED_TEAMS}"
            )

        normalized = {
            r["team"].strip(): float(r["rating"])
            for r in normalized_rows
        }

        source_map = {
            r["model_team"].strip(): r
            for r in source_rows
        }

        if len(normalized) != EXPECTED_TEAMS:
            raise RuntimeError(f"Week {week}: duplicate normalized teams")

        if len(source_map) != EXPECTED_TEAMS:
            raise RuntimeError(f"Week {week}: duplicate source-map teams")

        unresolved = [
            r for r in source_rows
            if not r.get("resolution", "").strip()
        ]
        if unresolved:
            raise RuntimeError(
                f"Week {week}: unresolved normalized names remain"
            )

        by_workbook_team = {
            str(row[0]).strip(): row
            for row in tab[1:]
            if row and str(row[0]).strip()
        }

        sp_mismatches = []
        rank_matches = 0
        comparable_rank_rows = 0

        for model_team, src in source_map.items():
            workbook_team = src["workbook_team"].strip()

            if workbook_team not in by_workbook_team:
                raise RuntimeError(
                    f"Week {week}: workbook team missing: {workbook_team}"
                )

            row = by_workbook_team[workbook_team]
            source_sp = float(row[sp_col])
            stored = normalized[model_team]

            if abs(stored - source_sp) > 1e-9:
                sp_mismatches.append(
                    {
                        "team": model_team,
                        "stored": stored,
                        "source_sp": source_sp,
                    }
                )

            if rank_col is not None and len(row) > rank_col:
                try:
                    rank = float(row[rank_col])
                except (TypeError, ValueError):
                    rank = None

                if rank is not None:
                    comparable_rank_rows += 1
                    if abs(stored - rank) <= 1e-9:
                        rank_matches += 1

        if sp_mismatches:
            raise RuntimeError(
                f"Week {week}: {len(sp_mismatches)} ratings do not "
                "match source SP+"
            )

        identical_to_rank = (
            comparable_rank_rows == EXPECTED_TEAMS
            and rank_matches == EXPECTED_TEAMS
        )

        if identical_to_rank:
            raise RuntimeError(
                f"Week {week}: extracted SP+ vector is identically "
                "equal to Rk vector"
            )

        result["weeks"][str(week)] = {
            "worksheet": sheet,
            "header": header,
            "spplus_column_index": sp_col,
            "rank_column_index": rank_col,
            "team_count": len(normalized_rows),
            "resolved_team_count": len(source_rows),
            "source_spplus_matches": EXPECTED_TEAMS,
            "rank_comparable_rows": comparable_rank_rows,
            "rank_equal_rows": rank_matches,
            "rating_vector_identical_to_rank": identical_to_rank,
            "status": "PASS",
        }

OUT.write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

print("Historical extractor regression: PASS (Weeks 1-14)")
print(f"Provenance: {OUT}")

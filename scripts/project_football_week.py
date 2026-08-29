import csv
from pathlib import Path

from project_nfl_week import generate_edges as generate_nfl_edges
from project_ncaaf_week import generate_edges as generate_ncaaf_edges


APEX_OUTPUT_PATH = Path("C:/Projects/Apex/sample_model_edges.csv")


FIELDNAMES = [
    "sport",
    "event_date",
    "event_time",
    "event",
    "market",
    "selection",
    "book",
    "market_line",
    "market_odds",
    "model_line",
    "edge_points",
    "signal_source",
    "recommended_units",
]


def write_edges(edges: list[dict]) -> None:
    APEX_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with APEX_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(edges)


def main() -> None:
    nfl_edges = generate_nfl_edges()
    ncaaf_edges = generate_ncaaf_edges()

    combined_edges = nfl_edges + ncaaf_edges

    combined_edges.sort(
        key=lambda edge: (
            edge["event_date"],
            edge["sport"],
            -edge["edge_points"],
        )
    )

    write_edges(combined_edges)

    print(f"Wrote {len(combined_edges)} football model edges to:")
    print(APEX_OUTPUT_PATH)
    print()
    print(f"NFL edges: {len(nfl_edges)}")
    print(f"NCAAF edges: {len(ncaaf_edges)}")


if __name__ == "__main__":
    main()
# NCAAF v0.6 — 2023 Week 5 Formal Diagnostic Packet

**ARCHIVAL MARKET BENCHMARK — EXACT REPLAY-AS-OF LINE TIMESTAMP NOT ESTABLISHED**

Frozen v0.6 was not tuned or modified. No 2025 data was requested or inspected.

## A. Replay Integrity

- Ratings snapshot SHA: `0233e6ee072b577c7c41c23467b53ce847c25e731390919061f2496c180b6fb5`
- Published: `2023-09-24T09:00:00-04:00`
- `safe_after`: `2023-09-24T09:00:00-04:00`
- `safe_after < kickoff`: **56/56**
- Team/rating resolution: **56/56**
- Historical FBS eligibility: **56/56**
- Production isolation: **PASS**
- Independent frozen-line reproduction: **56/56 exact** after one-decimal frozen output rounding
- Maximum absolute discrepancy: **0.000**
- Final margin/orientation verified: **56/56**

## B. Raw Forecast Quality

| n | Model MAE | Median AE | RMSE | Mean signed | ≤3 | ≤7 | ≤10 | ≤14 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 56 | 10.46 | 9.10 | 12.70 | -0.31 | 8.9% | 41.1% | 53.6% | 73.2% |

### 10 largest absolute forecast misses

| Home | Away | Model HM | Actual HM | Abs err | Signed err |
| --- | --- | --- | --- | --- | --- |
| Georgia Tech | Bowling Green | 18.7 | -11 | 29.7 | 29.7 |
| Purdue | Illinois | -4.6 | 25 | 29.6 | -29.6 |
| Georgia State | Troy | 3.1 | -21 | 24.1 | 24.1 |
| Massachusetts | Arkansas State | -0.1 | -24 | 23.9 | 23.9 |
| Virginia Tech | Pittsburgh | -5.7 | 17 | 22.7 | -22.7 |
| Air Force | San Diego State | 16.5 | 39 | 22.5 | -22.5 |
| Toledo | Northern Illinois | 22.4 | 2 | 20.4 | 20.4 |
| Colorado | USC | -26.2 | -7 | 19.2 | -19.2 |
| TCU | West Virginia | 14.0 | -3 | 17.0 | 17.0 |
| Tulsa | Temple | 5.1 | 22 | 16.9 | -16.9 |

## C. Spread-Size Diagnostics

| Bucket | n | MAE | Median AE | Signed error |
| --- | --- | --- | --- | --- |
| 0–6.5 | 22 | 11.98 | 12.40 | -1.84 |
| 7–13.5 | 13 | 6.77 | 7.40 | -2.54 |
| 14–20.5 | 11 | 11.97 | 7.80 | 2.03 |
| 21–27.5 | 7 | 12.40 | 11.10 | 2.66 |
| 28+ | 3 | 5.20 | 4.90 | 5.07 |

| Split | n | MAE | Median AE | RMSE | Signed error |
| --- | --- | --- | --- | --- | --- |
| Home favorite | 33 | 10.56 | 9.20 | 12.57 | 0.15 |
| Road favorite | 23 | 10.31 | 7.80 | 12.87 | -0.97 |

## D. Model vs Archival DraftKings Benchmark

**ARCHIVAL MARKET BENCHMARK — EXACT REPLAY-AS-OF LINE TIMESTAMP NOT ESTABLISHED**

| Model MAE | Archival DK MAE | Model Better | Market Better | Tie | Model signed | Archival signed |
| --- | --- | --- | --- | --- | --- | --- |
| 10.46 | 10.45 | 34 | 21 | 1 | -0.31 | -0.23 |

## E. Open vs Archival Line Forensics

| Both | Mean abs move | Median abs move | Max abs move | Unchanged | Unchanged % |
| --- | --- | --- | --- | --- | --- |
| 56 | 0.96 | 0.50 | 4.50 | 21 | 37.5% |

### 10 largest moves

| Home | Away | Open | Archival | Move | Abs move |
| --- | --- | --- | --- | --- | --- |
| BYU | Cincinnati | -2.5 | 2.0 | 4.5 | 4.5 |
| Colorado | USC | 17.0 | 21.5 | 4.5 | 4.5 |
| Auburn | Georgia | 18.5 | 14.0 | -4.5 | 4.5 |
| Mississippi State | Alabama | 11.5 | 14.5 | 3.0 | 3.0 |
| Syracuse | Clemson | 9.0 | 6.5 | -2.5 | 2.5 |
| Arkansas | Texas A&M | 4.0 | 6.0 | 2.0 | 2.0 |
| Kentucky | Florida | -3.5 | -1.5 | 2.0 | 2.0 |
| James Madison | South Alabama | -1.0 | -3.0 | -2.0 | 2.0 |
| Ole Miss | LSU | 4.5 | 2.5 | -2.0 | 2.0 |
| Southern Miss | Texas State | 7.0 | 5.0 | -2.0 | 2.0 |

## F. Edge / Recommendation Diagnostics

### By recommendation

| Rec | n | ATS | Win % | Model MAE | Archival DK MAE | Selected-side signed err |
| --- | --- | --- | --- | --- | --- | --- |
| Value | 15 | 8-6-1 | 57.1% | 11.72 | 11.13 | 4.03 |
| Lean | 14 | 7-7-0 | 50.0% | 10.96 | 10.89 | -2.17 |
| Watch | 13 | 8-5-0 | 61.5% | 12.02 | 12.31 | 0.02 |
| No Play | 14 | 12-2-0 | 85.7% | 7.16 | 7.54 | -4.13 |

### By edge bucket

| Edge | n | ATS | Win % | Model MAE | Archival DK MAE | Selected-side signed err |
| --- | --- | --- | --- | --- | --- | --- |
| <1.0 | 14 | 12-2-0 | 85.7% | 7.16 | 7.54 | -4.13 |
| 1.0–1.9 | 13 | 8-5-0 | 61.5% | 12.02 | 12.31 | 0.02 |
| 2.0–3.9 | 14 | 7-7-0 | 50.0% | 10.96 | 10.89 | -2.17 |
| 4.0–6.9 | 11 | 6-4-1 | 60.0% | 12.21 | 12.27 | 2.75 |
| 7.0–9.9 | 4 | 2-2-0 | 50.0% | 10.38 | 8.00 | 7.53 |
| 10.0+ | 0 | 0-0-0 | 0.0% | NA | NA | NA |

- Actionability: Model Play **4**, Review Only **38**, Guarded / Other **14**.
- Descriptive only; exact historical market-line timing is not established.

## G. -110 Fallback Dependency Audit

Frozen v0.6 orders candidates by edge_points, then market_line, then market_odds. Price does not enter projection or edge. Recommendation/confidence/units/guards are downstream of the selected edge/line and frozen non-price conditions. In this single-provider cohort the third-level price tie-break is reachable in 0 games; therefore synthetic -110 does not materially alter classifications here.

## H. Top-10 Miss Audit

| Home | Away | Home SP+ | Away SP+ | Model HM | Actual HM | Abs err | Signed err | Archival DK | Side | Edge | Rec/action | Audit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Georgia Tech | Bowling Green | -2.3 | -18.5 | 18.7 | -11 | 29.7 | 29.7 | -22.0 | away | 3.3 | Lean / Review Only | None identified — valid model miss |
| Purdue | Illinois | -3.3 | 3.8 | -4.6 | 25 | 29.6 | -29.6 | -1.0 | away | 5.6 | Value / Review Only | None identified — valid model miss |
| Georgia State | Troy | -1.2 | -1.8 | 3.1 | -21 | 24.1 | 24.1 | -1.5 | home | 1.6 | Watch / Review Only | None identified — valid model miss |
| Massachusetts | Arkansas State | -18.3 | -15.7 | -0.1 | -24 | 23.9 | 23.9 | -1.0 | away | 1.1 | Watch / Review Only | None identified — valid model miss |
| Virginia Tech | Pittsburgh | -4.5 | 3.7 | -5.7 | 17 | 22.7 | -22.7 | 2.5 | away | 3.2 | Lean / Review Only | None identified — valid model miss |
| Air Force | San Diego State | 6.3 | -7.7 | 16.5 | 39 | 22.5 | -22.5 | -10.5 | home | 6.0 | Value / Review Only | None identified — valid model miss |
| Toledo | Northern Illinois | 2.1 | -17.8 | 22.4 | 2 | 20.4 | 20.4 | -13.0 | home | 9.4 | Value / Model Play | None identified — valid model miss |
| Colorado | USC | -4.4 | 24.3 | -26.2 | -7 | 19.2 | -19.2 | 21.5 | away | 4.7 | Value / Review Only | None identified — valid model miss |
| TCU | West Virginia | 14.0 | 2.5 | 14.0 | -3 | 17.0 | 17.0 | -12.5 | home | 1.5 | Watch / Review Only | None identified — valid model miss |
| Tulsa | Temple | -11.4 | -14.0 | 5.1 | 22 | 16.9 | -16.9 | -3.0 | home | 2.1 | Lean / Review Only | None identified — valid model miss |

## I. Static Prior-Season vs Weekly Ratings Comparison

Static baseline: 2022 final CFBD SP+. Weekly replay: archived 2023 post-Week-4 ESPN SP+. Same games, archival DK spread, frozen builder, replay clock, and -110 compatibility price otherwise held fixed.

| Shared | Mean abs line Δ | Median abs line Δ | Max abs line Δ | Static MAE | Weekly MAE | Static bias | Weekly bias | Archival DK MAE | Weekly improved | Static improved | Ties |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 55 | 6.79 | 6.00 | 17.40 | 12.58 | 10.64 | -1.55 | -0.31 | 10.63 | 33 | 22 | 0 |

- Static-unavailable games: **1** (see `static_unavailable.csv`).

### Edge-bucket migration

| Static -> Weekly | n |
| --- | --- |
| 1.0–1.9 -> 4.0–6.9 | 1 |
| 1.0–1.9 -> <1.0 | 2 |
| 10.0+ -> 1.0–1.9 | 6 |
| 10.0+ -> 2.0–3.9 | 4 |
| 10.0+ -> 4.0–6.9 | 3 |
| 10.0+ -> 7.0–9.9 | 2 |
| 10.0+ -> <1.0 | 2 |
| 2.0–3.9 -> 1.0–1.9 | 2 |
| 2.0–3.9 -> 2.0–3.9 | 4 |
| 2.0–3.9 -> 4.0–6.9 | 2 |
| 2.0–3.9 -> <1.0 | 2 |
| 4.0–6.9 -> 1.0–1.9 | 3 |
| 4.0–6.9 -> 2.0–3.9 | 4 |
| 4.0–6.9 -> 4.0–6.9 | 4 |
| 4.0–6.9 -> 7.0–9.9 | 2 |
| 4.0–6.9 -> <1.0 | 4 |
| 7.0–9.9 -> 1.0–1.9 | 2 |
| 7.0–9.9 -> 2.0–3.9 | 1 |
| 7.0–9.9 -> <1.0 | 2 |
| <1.0 -> 2.0–3.9 | 1 |
| <1.0 -> 4.0–6.9 | 1 |
| <1.0 -> <1.0 | 1 |

### Recommendation migration

| Static -> Weekly | n |
| --- | --- |
| Lean -> Lean | 4 |
| Lean -> No Play | 2 |
| Lean -> Value | 2 |
| Lean -> Watch | 2 |
| No Play -> Lean | 1 |
| No Play -> No Play | 1 |
| No Play -> Value | 1 |
| Value -> Lean | 9 |
| Value -> No Play | 8 |
| Value -> Value | 11 |
| Value -> Watch | 11 |
| Watch -> No Play | 2 |
| Watch -> Value | 1 |

### Model Play persistence / migration

| Static -> Weekly | n |
| --- | --- |
| Model Play -> Not Model Play | 5 |
| Not Model Play -> Model Play | 4 |
| Not Model Play -> Not Model Play | 46 |

## J. Final Integrity Gate

| Gate | Result |
| --- | --- |
| 1. Projection fidelity — all 56 frozen-v0.6 lines reproduced | PASS |
| 2. Temporal integrity — no ratings used before safe-after | PASS |
| 3. Identity integrity — no unresolved/misclassified teams | PASS |
| 4. Result integrity — all final margins/orientations verified | PASS |
| 5. Production isolation — no canonical state modified | PASS |

**Overall gate: PASS**

Blockers: **None identified.**

Files created: `report.md`, `metrics.json`, `game_diagnostics.csv`, `top10_misses.csv`, `open_line_moves.csv`, `static_vs_weekly.csv`, `static_unavailable.csv`, `price_dependency_source.txt`, `diagnostic_manifest.json`.

Commit hash: **NOT COMMITTED at generation time**.

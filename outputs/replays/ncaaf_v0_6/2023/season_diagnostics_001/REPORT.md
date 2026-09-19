# NCAAF v0.6 — 2023 Corrected Season Diagnostic Packet

## 2023 Season Integrity

**PASS**

- Weeks attempted: **14**
- Weeks included: **14**
- Games considered: **703**
- Games modeled: **697**
- Games excluded: **6**
- Exclusion reasons: `{'kickoff_not_after_ratings_safe_after': 6, 'kickoff_not_after_replay_as_of': 6}`
- Projection fidelity: **697/697**
- Temporal integrity: **697/697**
- Identity/FBS integrity: **697/697**
- Result orientation integrity: **697/697**
- Week 9–14 corrected SP+ vectors confirmed: **True**
- Production isolation: **True**
- 2025 inspected: **False**
- Frozen v0.6 changed: **False**
- Production state touched: **False**

Canonical weekly replay artifacts and hashes are recorded in `canonical_weekly_artifacts.csv`.

## 2023 Season Forecast Summary

| Metric | Value |
| --- | --- |
| Games modeled | 697 |
| Model MAE | 12.40 |
| Median AE | 10.40 |
| RMSE | 15.46 |
| Home-margin bias | -2.50 |
| Within 7 pts | 34.29% |
| Archival DK MAE | 12.03 |
| Model better % | 46.05% |

## Raw Forecast Quality by Week

| week | n | model_mae | median_ae | rmse | signed_bias |
| --- | --- | --- | --- | --- | --- |
| 1 | 45 | 12.14 | 9.40 | 15.84 | -6.06 |
| 2 | 47 | 11.82 | 11.30 | 14.02 | -4.71 |
| 3 | 10 | 14.19 | 13.05 | 16.09 | -8.79 |
| 4 | 63 | 10.69 | 8.90 | 12.78 | -4.13 |
| 5 | 56 | 10.46 | 9.10 | 12.70 | 0.49 |
| 6 | 49 | 12.62 | 9.80 | 15.96 | -2.16 |
| 7 | 55 | 13.48 | 11.80 | 16.51 | -1.97 |
| 8 | 54 | 13.19 | 10.75 | 16.69 | -2.75 |
| 9 | 54 | 14.35 | 14.50 | 16.85 | -5.61 |
| 10 | 62 | 12.18 | 9.50 | 15.58 | -4.66 |
| 11 | 63 | 14.80 | 12.10 | 18.25 | -1.22 |
| 12 | 64 | 11.08 | 8.35 | 14.72 | 1.70 |
| 13 | 65 | 12.09 | 10.10 | 15.07 | -0.65 |
| 14 | 10 | 10.83 | 9.20 | 12.78 | 3.49 |

## ARCHIVAL MARKET BENCHMARK — EXACT REPLAY-AS-OF LINE TIMESTAMP NOT ESTABLISHED

- Model MAE: **12.40**
- Archival DK MAE: **12.03**
- Model Better / Market Better / Tie: **321 / 369 / 7**
- Model Better %: **46.05%**
- Model signed home-margin error: **-2.50**
- Archival-market signed home-margin error: **-0.07**

| week | n | model_mae | archival_market_mae | model_better | market_better | tie |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 45 | 12.14 | 11.71 | 20 | 25 | 0 |
| 2 | 47 | 11.82 | 10.05 | 17 | 30 | 0 |
| 3 | 10 | 14.19 | 12.20 | 4 | 6 | 0 |
| 4 | 63 | 10.69 | 9.90 | 24 | 39 | 0 |
| 5 | 56 | 10.46 | 10.45 | 34 | 21 | 1 |
| 6 | 49 | 12.62 | 12.24 | 21 | 28 | 0 |
| 7 | 55 | 13.48 | 13.85 | 27 | 27 | 1 |
| 8 | 54 | 13.19 | 13.10 | 27 | 27 | 0 |
| 9 | 54 | 14.35 | 13.90 | 21 | 33 | 0 |
| 10 | 62 | 12.18 | 11.21 | 21 | 40 | 1 |
| 11 | 63 | 14.80 | 14.56 | 31 | 30 | 2 |
| 12 | 64 | 11.08 | 11.41 | 36 | 27 | 1 |
| 13 | 65 | 12.09 | 11.86 | 30 | 34 | 1 |
| 14 | 10 | 10.83 | 12.10 | 8 | 2 | 0 |

## Spread-Size Diagnostics

| group | n | model_mae | archival_dk_mae | median_ae | home_signed_bias | model_better | market_better | ties |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0-6.5 | 250 | 11.96 | 11.85 | 9.85 | -0.66 | 122 | 124 | 4 |
| 7-13.5 | 210 | 12.60 | 12.00 | 10.65 | -3.40 | 88 | 121 | 1 |
| 14-20.5 | 133 | 12.29 | 11.88 | 10.40 | -3.25 | 65 | 68 | 0 |
| 21-27.5 | 54 | 13.33 | 12.85 | 11.75 | -2.68 | 24 | 28 | 2 |
| 28+ | 50 | 13.01 | 12.58 | 11.65 | -5.77 | 22 | 28 | 0 |

## Edge / Recommendation Diagnostics

### Recommendation

| group | n | ats_record | ats_win_rate | model_mae | archival_dk_mae | selected_side_signed_bias |
| --- | --- | --- | --- | --- | --- | --- |
| Value | 234 | 118-108-8 | 52.21 | 12.65 | 11.58 | 5.21 |
| Lean | 188 | 100-84-4 | 54.35 | 12.26 | 12.32 | 0.31 |
| Watch | 131 | 64-67-0 | 48.85 | 12.52 | 12.43 | 1.89 |
| No Play | 144 | 69-71-4 | 49.29 | 12.05 | 12.02 | 1.52 |

### Edge Bucket

| group | n | ats_record | ats_win_rate | model_mae | archival_dk_mae | selected_side_signed_bias |
| --- | --- | --- | --- | --- | --- | --- |
| <1.0 | 144 | 69-71-4 | 49.29 | 12.05 | 12.02 | 1.52 |
| 1.0-1.9 | 128 | 64-64-0 | 50.00 | 12.46 | 12.41 | 1.58 |
| 2.0-3.9 | 190 | 100-86-4 | 53.76 | 12.30 | 12.35 | 0.48 |
| 4.0-6.9 | 169 | 86-79-4 | 52.12 | 12.37 | 11.68 | 4.60 |
| 7.0-9.9 | 51 | 26-21-4 | 55.32 | 12.07 | 11.19 | 5.28 |
| 10.0+ | 15 | 6-9-0 | 40.00 | 17.85 | 11.60 | 12.40 |

### Production Actionability

| group | n | ats_record | ats_win_rate | model_mae | archival_dk_mae | selected_side_signed_bias |
| --- | --- | --- | --- | --- | --- | --- |
| Model Play | 52 | 27-21-4 | 56.25 | 12.00 | 11.32 | 5.03 |
| Review Only | 487 | 250-229-8 | 52.19 | 12.36 | 12.13 | 2.20 |
| Guarded / Other | 158 | 74-80-4 | 48.05 | 12.63 | 11.94 | 2.62 |

## Signed-Bias Diagnostics

Both requested bias definitions are stored across the dedicated `bias_*.csv` tables:

- Unconditioned home-margin bias = projected home margin − actual home margin.
- Market-selected-side bias = projected selected-side margin − actual selected-side margin.

## Static 2022 Final SP+ vs Contemporaneous 2023 Weekly SP+

- Shared games: **677**
- Static MAE: **14.19**
- Weekly MAE: **12.47**
- Weekly − Static MAE: **-1.72**
- Static signed bias: **0.03**
- Weekly signed bias: **-2.44**
- Weekly ratings better / Static better / Ties: **393 / 281 / 3**
- Mean absolute model-line change: **16.39**
- Median absolute model-line change: **11.10**
- Maximum absolute model-line change: **98.90**

Week-level comparison and recommendation/edge/actionability migration are stored in the corresponding CSV artifacts.

## Opening vs Archival-Market Movement

- Rows with opening + archival line: **696**
- Mean absolute movement: **1.01**
- Median movement: **0.50**
- Maximum movement: **12.00**
- Unchanged: **304 (43.68%)**

The 20 largest movements are stored in `opening_movement_top20.csv`.

## Outliers

The packet contains:

- `outliers_largest_absolute_misses.csv`
- `outliers_largest_positive_errors.csv`
- `outliers_largest_negative_errors.csv`

Legitimate football outliers are retained; no rows were removed based on model error.

## Historical-Extractor Regression Control

- Exact `SP+` header required.
- Duplicate or absent exact `SP+` header fails.
- 133 expected normalized teams required.
- All normalized identities must resolve.
- Source header/schema retained in `schema_provenance.json`.
- Extraction fails regression if the rating vector is identically equal to the adjacent `Rk` vector.
- No arbitrary statistical-distribution threshold is used.

## Data Limitations

- **ARCHIVAL MARKET BENCHMARK — EXACT REPLAY-AS-OF LINE TIMESTAMP NOT ESTABLISHED.** DraftKings data is archival and must not be described as a closing or guaranteed contemporaneous replay-as-of line.
- Week 3 contains only **10** FBS-vs-FBS games with archived DraftKings spreads in CFBD despite a substantially larger football slate; Week 3 market coverage is therefore incomplete.
- Several ratings `safe_after` timestamps remain conservative/provisional availability timestamps. They were sufficient for leakage gating in this reconstruction but have not been tightened to exact publication minutes.
- Static prior-season comparison includes only games for which the static 2022 ratings input can be resolved through frozen production logic.

## Files / Commit

Generated season packet files:
- `actionability_diagnostics.csv`
- `archival_market_by_week.csv`
- `bias_by_actionability.csv`
- `bias_by_edge_bucket.csv`
- `bias_by_favorite_underdog.csv`
- `bias_by_recommendation.csv`
- `bias_by_spread_bucket.csv`
- `bias_by_week.csv`
- `bias_overall.csv`
- `canonical_weekly_artifacts.csv`
- `edge_bucket_diagnostics.csv`
- `edge_bucket_migration.csv`
- `forecast_quality_by_week.csv`
- `metrics.json`
- `model_favorite_side_diagnostics.csv`
- `model_play_migration.csv`
- `opening_movement_summary.json`
- `opening_movement_top20.csv`
- `outliers_largest_absolute_misses.csv`
- `outliers_largest_negative_errors.csv`
- `outliers_largest_positive_errors.csv`
- `recommendation_diagnostics.csv`
- `recommendation_migration.csv`
- `season_integrity.json`
- `spread_size_diagnostics.csv`
- `static_2022_final_spplus.json`
- `static_unavailable_games.csv`
- `static_vs_weekly_by_week.csv`
- `static_vs_weekly_summary.json`

- Commit: **PENDING packet commit**

No v0.7 tuning or App/UI recommendation is made in this packet.

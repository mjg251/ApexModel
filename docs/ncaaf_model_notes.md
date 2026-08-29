# NCAAF Spread Model Notes

## Current Version

NCAAF Spread Model v0.1

## Purpose

This model projects college football point spreads using simple team power ratings.

It is not a machine-learning model yet. It is a transparent ratings-based model designed to create Apex-compatible model edge outputs.

## Core Formula

Projected home margin:

home_team_rating - away_team_rating + home_field_advantage

Positive projected margin means the home team is expected to win by that many points.

Example:

Missouri rating: +12.0
Arkansas-Pine Bluff rating: -28.0
Home-field advantage: +2.5

Projected Missouri margin:

12.0 - (-28.0) + 2.5 = 42.5

If the market line is Missouri -37.5, the model sees:

Model line: Missouri -42.5
Market line: Missouri -37.5
Edge: Missouri +5.0 points

## Spread Sign Convention

Input file data/ncaaf_upcoming_games.csv stores market_line from the home team's perspective.

Examples:

Missouri -37.5 at home is stored as:

-37.5

Utah -24.5 at home is stored as:

-24.5

If the model prefers the away team, the script converts the market line to the away team's side.

Example:

Home line: Utah -24.5
Away side: Idaho +24.5

## Ratings Meaning

Each team rating is measured in points versus an average team on a neutral field.

Examples:

+20.0 = elite national title contender
+10.0 = strong ranked team
0.0 = roughly average FBS team
-10.0 = weak FBS team
-25.0 or worse = weak FCS / low-end opponent

These ratings are currently manual placeholders.

## Home-Field Advantage

Current NCAAF home-field advantage:

2.5 points

This is intentionally higher than NFL because college environments, travel, and roster depth gaps can matter more.

Future versions may use team-specific home-field values.

## Minimum Edge Threshold

Current minimum edge:

2.0 points

Reason:

College football spreads are noisier than NFL spreads, especially with:
- FCS opponents
- blowout risk
- rotation uncertainty
- uneven schedules
- late injury/depth-chart information
- transfer portal roster changes

## Unit Sizing Rules

Current recommended units:

Edge >= 7.0 points: 0.75 units
Edge >= 4.0 points: 0.50 units
Edge >= 2.0 points: 0.25 units

These are intentionally conservative.

## Current Weaknesses

This version does not yet account for:

- returning production
- transfer portal changes
- quarterback changes
- offensive/defensive line continuity
- injury reports
- pace
- explosiveness
- garbage-time distortion
- FCS vs FBS adjustment
- neutral-site games
- weather
- market movement
- closing line value

## Near-Term Improvement Priorities

1. Add neutral-site flag
2. Add FCS opponent flag
3. Add model confidence score
4. Add team tier classification
5. Add max spread risk guard for huge favorites
6. Add rating notes column
7. Add prior-season baseline data
8. Add closing-line tracking in Apex

## How To Run

From terminal:

cd C:\Projects\ApexModel
python scripts\project_ncaaf_week.py

This writes:

C:\Projects\Apex\sample_model_edges.csv

Then import that CSV into Apex:

Model Edge -> Import Model CSV

## Current Apex Flow

NCAAF ratings + upcoming games
-> project_ncaaf_week.py
-> sample_model_edges.csv
-> Apex Model Edge import
-> Add Selected to Card
-> Card Builder
-> Mark Placed
-> Open Bets

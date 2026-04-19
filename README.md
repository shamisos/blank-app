# Distance Runner Training Log (Terminal + SQLite)

A simple Python CLI for logging running workouts and monitoring training load.

## Features

- Log workouts with:
  - date
  - type (`easy`, `tempo`, `interval`, `long`, `race`)
  - distance (miles)
  - duration (minutes)
  - RPE (1-10)
- Automatic weekly mileage aggregation
- ACWR monitoring using a monotonic load model
  - Load per session = `duration_minutes * RPE`
  - Acute load = 7-day cumulative load
  - Chronic reference = 28-day average weekly load (`28-day total / 4`)
  - `ACWR = acute_7_day / chronic_weekly_average`
- Injury-risk flag when ACWR > 1.5
- Weekly summary:
  - total miles
  - average RPE
  - load trend vs previous week
- Local persistence with SQLite

## Quick start

```bash
python runner_log.py --help
```

### Add a workout

```bash
python runner_log.py add --date 2026-04-18 --type tempo --distance 6.2 --duration 48 --rpe 7
```

### List recent workouts

```bash
python runner_log.py list --limit 20
```

### Weekly mileage table

```bash
python runner_log.py weekly-mileage
```

### Weekly summary

```bash
python runner_log.py summary --date 2026-04-19
```

## Database

By default, the tool stores data in `training_log.db` in the current working directory.
You can set a custom DB path with `--db` on any command.

Example:

```bash
python runner_log.py --db ./data/runs.db list
```

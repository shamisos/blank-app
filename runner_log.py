#!/usr/bin/env python3
"""Terminal-based training log and load monitor for distance runners."""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

DB_PATH = "training_log.db"
WORKOUT_TYPES = ("easy", "tempo", "interval", "long", "race")
ACWR_RISK_THRESHOLD = 1.5


@dataclass
class Workout:
    workout_date: str
    workout_type: str
    distance_miles: float
    duration_minutes: int
    rpe: int

    @property
    def load(self) -> float:
        # Monotonic load model: each workout contributes linearly to total load.
        return float(self.duration_minutes * self.rpe)


class TrainingLogDB:
    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workout_date TEXT NOT NULL,
                    workout_type TEXT NOT NULL,
                    distance_miles REAL NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    rpe INTEGER NOT NULL CHECK (rpe BETWEEN 1 AND 10),
                    load REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(workout_date)"
            )

    def add_workout(self, workout: Workout) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO workouts (
                    workout_date, workout_type, distance_miles, duration_minutes, rpe, load
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workout.workout_date,
                    workout.workout_type,
                    workout.distance_miles,
                    workout.duration_minutes,
                    workout.rpe,
                    workout.load,
                ),
            )
            return int(cursor.lastrowid)

    def list_workouts(self, limit: int = 30) -> Iterable[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, workout_date, workout_type, distance_miles, duration_minutes, rpe, load
                FROM workouts
                ORDER BY workout_date DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def sum_load_between(self, start_day: date, end_day: date) -> float:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(load), 0) AS total
                FROM workouts
                WHERE workout_date BETWEEN ? AND ?
                """,
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchone()
            return float(row["total"])

    def weekly_stats(self, week_start: date) -> dict[str, float]:
        week_end = week_start + timedelta(days=6)
        with self._connect() as conn:
            current = conn.execute(
                """
                SELECT
                    COALESCE(SUM(distance_miles), 0) AS total_miles,
                    COALESCE(AVG(rpe), 0) AS avg_rpe,
                    COALESCE(SUM(load), 0) AS total_load
                FROM workouts
                WHERE workout_date BETWEEN ? AND ?
                """,
                (week_start.isoformat(), week_end.isoformat()),
            ).fetchone()

            prev_start = week_start - timedelta(days=7)
            prev_end = week_start - timedelta(days=1)
            prev = conn.execute(
                """
                SELECT COALESCE(SUM(load), 0) AS total_load
                FROM workouts
                WHERE workout_date BETWEEN ? AND ?
                """,
                (prev_start.isoformat(), prev_end.isoformat()),
            ).fetchone()

            trend = 0.0
            if float(prev["total_load"]) > 0:
                trend = ((float(current["total_load"]) - float(prev["total_load"])) / float(prev["total_load"])) * 100.0

            return {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "total_miles": float(current["total_miles"]),
                "avg_rpe": float(current["avg_rpe"]),
                "total_load": float(current["total_load"]),
                "prev_load": float(prev["total_load"]),
                "load_trend_pct": trend,
            }

    def weekly_mileage(self) -> Iterable[sqlite3.Row]:
        # SQLite week grouping: Monday-based week start.
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT
                    DATE(workout_date, '-' || ((CAST(STRFTIME('%w', workout_date) AS INTEGER) + 6) % 7) || ' days') AS week_start,
                    ROUND(SUM(distance_miles), 2) AS total_miles,
                    ROUND(AVG(rpe), 2) AS avg_rpe,
                    ROUND(SUM(load), 1) AS total_load
                FROM workouts
                GROUP BY week_start
                ORDER BY week_start DESC
                """
            ).fetchall()


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Date must be YYYY-MM-DD") from exc


def validate_workout_type(value: str) -> str:
    normalized = value.lower()
    if normalized not in WORKOUT_TYPES:
        raise argparse.ArgumentTypeError(f"Type must be one of: {', '.join(WORKOUT_TYPES)}")
    return normalized


def calculate_acwr(db: TrainingLogDB, anchor_day: date) -> tuple[float, float, float]:
    acute_start = anchor_day - timedelta(days=6)
    chronic_start = anchor_day - timedelta(days=27)

    acute_7_day = db.sum_load_between(acute_start, anchor_day)
    chronic_28_day_total = db.sum_load_between(chronic_start, anchor_day)
    chronic_weekly_avg = chronic_28_day_total / 4.0 if chronic_28_day_total > 0 else 0.0

    if chronic_weekly_avg == 0:
        acwr = 0.0
    else:
        acwr = acute_7_day / chronic_weekly_avg

    return acute_7_day, chronic_weekly_avg, acwr


def print_workouts(rows: Iterable[sqlite3.Row]) -> None:
    print("\nRecent workouts")
    print("-" * 79)
    print(f"{'ID':<4} {'Date':<12} {'Type':<10} {'Miles':>7} {'Minutes':>8} {'RPE':>5} {'Load':>8}")
    print("-" * 79)
    for row in rows:
        print(
            f"{row['id']:<4} {row['workout_date']:<12} {row['workout_type']:<10} "
            f"{row['distance_miles']:>7.2f} {row['duration_minutes']:>8d} {row['rpe']:>5d} {row['load']:>8.1f}"
        )


def print_weekly_summary(summary: dict[str, float], acwr: float) -> None:
    print("\nWeekly summary")
    print("-" * 40)
    print(f"Week: {summary['week_start']} to {summary['week_end']}")
    print(f"Total miles: {summary['total_miles']:.2f}")
    print(f"Average RPE: {summary['avg_rpe']:.2f}")
    print(f"Total load: {summary['total_load']:.1f}")
    print(f"Load trend vs previous week: {summary['load_trend_pct']:+.1f}%")
    print(f"Current ACWR: {acwr:.2f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Distance running training log + ACWR monitor")
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_cmd = subparsers.add_parser("add", help="Add a workout")
    add_cmd.add_argument("--date", required=True, type=parse_date, help="Workout date (YYYY-MM-DD)")
    add_cmd.add_argument("--type", required=True, type=validate_workout_type, help="Workout type")
    add_cmd.add_argument("--distance", required=True, type=float, help="Distance in miles")
    add_cmd.add_argument("--duration", required=True, type=int, help="Duration in minutes")
    add_cmd.add_argument("--rpe", required=True, type=int, choices=range(1, 11), help="RPE (1-10)")

    list_cmd = subparsers.add_parser("list", help="List recent workouts")
    list_cmd.add_argument("--limit", type=int, default=30, help="Number of rows to show")

    subparsers.add_parser("weekly-mileage", help="Show weekly mileage history")

    summary_cmd = subparsers.add_parser("summary", help="Show weekly summary for a date")
    summary_cmd.add_argument("--date", default=date.today().isoformat(), type=parse_date, help="Any date in week (YYYY-MM-DD)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    db = TrainingLogDB(args.db)
    db.init_db()

    if args.command == "add":
        if args.distance <= 0:
            raise SystemExit("Distance must be > 0")
        if args.duration <= 0:
            raise SystemExit("Duration must be > 0")

        workout = Workout(
            workout_date=args.date.isoformat(),
            workout_type=args.type,
            distance_miles=args.distance,
            duration_minutes=args.duration,
            rpe=args.rpe,
        )
        workout_id = db.add_workout(workout)

        _, _, acwr = calculate_acwr(db, args.date)
        print(f"Saved workout #{workout_id} with load {workout.load:.1f}.")
        print(f"ACWR after this workout: {acwr:.2f}")
        if acwr > ACWR_RISK_THRESHOLD:
            print(f"⚠️  Injury risk zone: ACWR is above {ACWR_RISK_THRESHOLD:.1f}")

    elif args.command == "list":
        rows = db.list_workouts(limit=args.limit)
        print_workouts(rows)

    elif args.command == "weekly-mileage":
        rows = db.weekly_mileage()
        print("\nWeekly mileage")
        print("-" * 58)
        print(f"{'Week start':<12} {'Miles':>10} {'Avg RPE':>10} {'Total load':>12}")
        print("-" * 58)
        for row in rows:
            print(
                f"{row['week_start']:<12} {row['total_miles']:>10.2f} {row['avg_rpe']:>10.2f} {row['total_load']:>12.1f}"
            )

    elif args.command == "summary":
        week_start = args.date - timedelta(days=args.date.weekday())
        summary = db.weekly_stats(week_start)
        _, _, acwr = calculate_acwr(db, args.date)
        print_weekly_summary(summary, acwr)
        if acwr > ACWR_RISK_THRESHOLD:
            print(f"⚠️  ACWR exceeds {ACWR_RISK_THRESHOLD:.1f}: reduce load progression.")


if __name__ == "__main__":
    main()

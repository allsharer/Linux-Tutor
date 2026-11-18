"""Student profiles, progress and academic records (SQLite).

The database lives in ``$XDG_DATA_HOME/linux-tutor/tutor.db`` - on the host, never in a
laboratory container - so resetting or deleting a lab cannot touch academic records,
and upgrading or reinstalling the application leaves it in place.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    created_at    REAL NOT NULL,
    last_active   REAL,
    current_lesson TEXT
);
CREATE TABLE IF NOT EXISTS lesson_progress (
    profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    lesson_id     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'in_progress',   -- in_progress | passed
    section_index INTEGER NOT NULL DEFAULT 0,
    started_at    REAL,
    completed_at  REAL,
    best_score    REAL,
    attempts      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (profile_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS exercise_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    lesson_id     TEXT NOT NULL,
    exercise_id   TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    hints_used    INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    feedback      TEXT
);
CREATE TABLE IF NOT EXISTS assessments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,            -- lesson | exam
    ref_id        TEXT NOT NULL,            -- lesson id or exam id
    score         REAL NOT NULL,
    passed        INTEGER NOT NULL,
    passing_score INTEGER NOT NULL,
    hints_used    INTEGER NOT NULL DEFAULT 0,
    started_at    REAL,
    finished_at   REAL NOT NULL,
    details       TEXT
);
CREATE INDEX IF NOT EXISTS idx_assess_profile ON assessments(profile_id, kind, ref_id);
CREATE INDEX IF NOT EXISTS idx_ex_profile ON exercise_results(profile_id, lesson_id);
"""


@dataclass
class Profile:
    id: int
    username: str
    display_name: str
    created_at: float
    last_active: float | None
    current_lesson: str | None


class ProgressStore:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript(SCHEMA)
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        self.db.commit()
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------------ profiles
    def create_profile(self, username: str, display_name: str = "") -> Profile:
        username = username.strip()
        if not username:
            raise ValueError("a username is required")
        now = time.time()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO profiles (username, display_name, created_at, last_active) VALUES (?,?,?,?)",
                (username, display_name.strip() or username, now, now))
        return self.profile(cur.lastrowid)

    def profiles(self) -> list[Profile]:
        rows = self.db.execute("SELECT * FROM profiles ORDER BY last_active DESC").fetchall()
        return [Profile(**dict(r)) for r in rows]

    def profile(self, pid: int) -> Profile:
        r = self.db.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
        if not r:
            raise KeyError(pid)
        return Profile(**dict(r))

    def delete_profile(self, pid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM profiles WHERE id=?", (pid,))

    def touch(self, pid: int, current_lesson: str | None = None) -> None:
        with self.db:
            if current_lesson:
                self.db.execute("UPDATE profiles SET last_active=?, current_lesson=? WHERE id=?",
                                (time.time(), current_lesson, pid))
            else:
                self.db.execute("UPDATE profiles SET last_active=? WHERE id=?", (time.time(), pid))

    # ------------------------------------------------------------------ lessons
    def lesson_state(self, pid: int, lesson_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM lesson_progress WHERE profile_id=? AND lesson_id=?",
                            (pid, lesson_id)).fetchone()
        return dict(r) if r else None

    def all_lesson_states(self, pid: int) -> dict[str, dict]:
        rows = self.db.execute("SELECT * FROM lesson_progress WHERE profile_id=?", (pid,)).fetchall()
        return {r["lesson_id"]: dict(r) for r in rows}

    def start_lesson(self, pid: int, lesson_id: str) -> None:
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO lesson_progress (profile_id, lesson_id, status, started_at) "
                            "VALUES (?,?, 'in_progress', ?)", (pid, lesson_id, time.time()))
        self.touch(pid, lesson_id)

    def set_section(self, pid: int, lesson_id: str, index: int) -> None:
        self.start_lesson(pid, lesson_id)
        with self.db:
            self.db.execute("UPDATE lesson_progress SET section_index=? WHERE profile_id=? AND lesson_id=?",
                            (index, pid, lesson_id))

    def is_passed(self, pid: int, lesson_id: str) -> bool:
        s = self.lesson_state(pid, lesson_id)
        return bool(s and s["status"] == "passed")

    # ------------------------------------------------------------------ exercises
    def record_exercise(self, pid: int, lesson_id: str, exercise_id: str, outcome: str,
                        hints_used: int, feedback: str = "") -> None:
        with self.db:
            self.db.execute("INSERT INTO exercise_results (profile_id, lesson_id, exercise_id, outcome, "
                            "hints_used, created_at, feedback) VALUES (?,?,?,?,?,?,?)",
                            (pid, lesson_id, exercise_id, outcome, hints_used, time.time(), feedback))

    def exercise_summary(self, pid: int, lesson_id: str) -> dict[str, dict]:
        rows = self.db.execute(
            "SELECT exercise_id, COUNT(*) AS attempts, MAX(hints_used) AS hints, "
            "SUM(outcome IN ('correct','correct_alternative')) AS successes "
            "FROM exercise_results WHERE profile_id=? AND lesson_id=? GROUP BY exercise_id",
            (pid, lesson_id)).fetchall()
        return {r["exercise_id"]: dict(r) for r in rows}

    # ------------------------------------------------------------------ assessments
    def record_assessment(self, pid: int, result) -> int:
        d = result.to_dict()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO assessments (profile_id, kind, ref_id, score, passed, passing_score, "
                "hints_used, started_at, finished_at, details) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pid, result.kind, result.ref_id, result.score_percent, int(result.passed),
                 result.passing_score, result.hints_used, result.started, result.finished, json.dumps(d)))
            if result.kind == "lesson":
                self.start_lesson(pid, result.ref_id)
                self.db.execute(
                    "UPDATE lesson_progress SET attempts = attempts + 1, "
                    "best_score = MAX(COALESCE(best_score, 0), ?) WHERE profile_id=? AND lesson_id=?",
                    (result.score_percent, pid, result.ref_id))
                if result.passed:
                    self.db.execute(
                        "UPDATE lesson_progress SET status='passed', "
                        "completed_at = COALESCE(completed_at, ?) WHERE profile_id=? AND lesson_id=?",
                        (time.time(), pid, result.ref_id))
        return cur.lastrowid

    def assessments(self, pid: int, kind: str | None = None, ref_id: str | None = None,
                    limit: int = 1000) -> list[dict]:
        q = "SELECT * FROM assessments WHERE profile_id=?"
        args: list = [pid]
        if kind:
            q += " AND kind=?"
            args.append(kind)
        if ref_id:
            q += " AND ref_id=?"
            args.append(ref_id)
        q += " ORDER BY finished_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.db.execute(q, args).fetchall()]

    def exam_passed(self, pid: int, exam_id: str) -> bool:
        r = self.db.execute("SELECT 1 FROM assessments WHERE profile_id=? AND kind='exam' AND ref_id=? "
                            "AND passed=1 LIMIT 1", (pid, exam_id)).fetchone()
        return r is not None

    def best_exam(self, pid: int, exam_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM assessments WHERE profile_id=? AND kind='exam' AND ref_id=? "
                            "ORDER BY score DESC LIMIT 1", (pid, exam_id)).fetchone()
        return dict(r) if r else None

    def total_hints(self, pid: int) -> int:
        a = self.db.execute("SELECT COALESCE(SUM(hints_used),0) FROM assessments WHERE profile_id=?",
                            (pid,)).fetchone()[0]
        b = self.db.execute("SELECT COALESCE(SUM(hints_used),0) FROM "
                            "(SELECT MAX(hints_used) AS hints_used FROM exercise_results WHERE profile_id=? "
                            "GROUP BY lesson_id, exercise_id)", (pid,)).fetchone()[0]
        return int(a + b)

    # ------------------------------------------------------------------ export / backup
    def export_profile(self, pid: int) -> dict:
        p = self.profile(pid)
        def rows(sql):
            return [dict(r) for r in self.db.execute(sql, (pid,)).fetchall()]
        return {
            "format": "linux-tutor-profile", "version": SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "profile": p.__dict__,
            "lesson_progress": rows("SELECT * FROM lesson_progress WHERE profile_id=?"),
            "exercise_results": rows("SELECT * FROM exercise_results WHERE profile_id=?"),
            "assessments": rows("SELECT * FROM assessments WHERE profile_id=?"),
        }

    def import_profile(self, data: dict, rename: str | None = None) -> Profile:
        if data.get("format") != "linux-tutor-profile":
            raise ValueError("not a Linux Tutor profile export")
        src = data["profile"]
        username = rename or src["username"]
        if self.db.execute("SELECT 1 FROM profiles WHERE username=?", (username,)).fetchone():
            raise ValueError(f"a profile called {username!r} already exists")
        with self.db:
            cur = self.db.execute("INSERT INTO profiles (username, display_name, created_at, last_active, "
                                  "current_lesson) VALUES (?,?,?,?,?)",
                                  (username, src["display_name"], src["created_at"], src.get("last_active"),
                                   src.get("current_lesson")))
            pid = cur.lastrowid
            for table, rows in (("lesson_progress", data.get("lesson_progress", [])),
                                ("exercise_results", data.get("exercise_results", [])),
                                ("assessments", data.get("assessments", []))):
                for row in rows:
                    row = {k: v for k, v in row.items() if k != "id"}
                    row["profile_id"] = pid
                    cols = ",".join(row)
                    self.db.execute(f"INSERT INTO {table} ({cols}) VALUES ({','.join('?' * len(row))})",
                                    list(row.values()))
        return self.profile(pid)

    def backup(self, dest: Path) -> Path:
        """Consistent copy of the whole database (all profiles), safe while in use."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        out = sqlite3.connect(str(dest))
        with out:
            self.db.backup(out)
        out.close()
        return dest

    @staticmethod
    def restore(backup_file: Path, db_path: Path) -> None:
        """Replace the database with a backup (the application must be closed)."""
        test = sqlite3.connect(str(backup_file))
        try:
            test.execute("SELECT COUNT(*) FROM profiles").fetchone()
        finally:
            test.close()
        if Path(db_path).exists():
            shutil.copy2(db_path, str(db_path) + ".before-restore")
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        shutil.copy2(backup_file, db_path)

"""Progression rules: what is locked, what is available, and how competent the student is.

* Level 1 is always open.  Level N opens when the level N-1 examination is passed.
* A lesson opens when its level is open and its prerequisites (by default the
  previous lesson in the level) have been *passed* - i.e. the end-of-lesson
  assessment reached the passing score.  Reading a lesson is not enough.
* A level examination opens when every lesson in the level has been passed.
* The final examination opens when the Advanced examination has been passed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..curriculum.loader import Curriculum
from .store import ProgressStore

LOCKED, AVAILABLE, IN_PROGRESS, PASSED = "locked", "available", "in_progress", "passed"


@dataclass
class Overview:
    percent_complete: float
    lessons_passed: int
    lessons_total: int
    current_level: str
    level_progress: dict[str, tuple[int, int]]
    exams: dict[str, dict | None]
    competency: str
    average_score: float | None
    improvement_areas: list[str] = field(default_factory=list)
    recent: list[dict] = field(default_factory=list)
    hints_used: int = 0


class Progression:
    def __init__(self, cur: Curriculum, store: ProgressStore, pid: int, config):
        self.cur = cur
        self.store = store
        self.pid = pid
        self.config = config

    @property
    def unlock_all(self) -> bool:
        return bool(self.config.get("instructor.unlock_all", False))

    def level_unlocked(self, level_id: str) -> bool:
        if self.unlock_all:
            return True
        ids = [lv.id for lv in self.cur.levels]
        idx = ids.index(level_id)
        if idx == 0:
            return True
        prev = self.cur.levels[idx - 1]
        if prev.exam:
            return self.store.exam_passed(self.pid, prev.exam)
        return all(self.store.is_passed(self.pid, l) for l in prev.lesson_ids)

    def lesson_status(self, lesson_id: str, states: dict | None = None) -> str:
        states = states if states is not None else self.store.all_lesson_states(self.pid)
        st = states.get(lesson_id)
        if st and st["status"] == "passed":
            return PASSED
        lesson = self.cur.lessons[lesson_id]
        if not self.unlock_all:
            if not self.level_unlocked(lesson.level):
                return LOCKED
            for pre in self.cur.prerequisites(lesson_id):
                ps = states.get(pre)
                if not (ps and ps["status"] == "passed"):
                    return LOCKED
        return IN_PROGRESS if st else AVAILABLE

    def missing_prerequisites(self, lesson_id: str) -> list[str]:
        out = []
        lesson = self.cur.lessons[lesson_id]
        if not self.level_unlocked(lesson.level):
            lv_ids = [lv.id for lv in self.cur.levels]
            prev = self.cur.levels[lv_ids.index(lesson.level) - 1]
            out.append(self.cur.exams[prev.exam].title if prev.exam else prev.title)
        for pre in self.cur.prerequisites(lesson_id):
            if not self.store.is_passed(self.pid, pre):
                out.append(f"{self.cur.lessons[pre].code} {self.cur.lessons[pre].title}")
        return out

    def exam_available(self, exam_id: str) -> bool:
        if self.unlock_all:
            return True
        exam = self.cur.exams[exam_id]
        if exam.level is None:   # final exam
            last = self.cur.levels[-1]
            return bool(last.exam) and self.store.exam_passed(self.pid, last.exam)
        if not self.level_unlocked(exam.level):
            return False
        return all(self.store.is_passed(self.pid, l) for l in self.cur.level(exam.level).lesson_ids)

    def current_level(self) -> str:
        current = self.cur.levels[0].id
        for lv in self.cur.levels:
            if self.level_unlocked(lv.id):
                current = lv.id
        return current

    def next_lesson(self) -> str | None:
        states = self.store.all_lesson_states(self.pid)
        for lesson in self.cur.ordered_lessons():
            if self.lesson_status(lesson.id, states) in (AVAILABLE, IN_PROGRESS):
                return lesson.id
        return None

    def overview(self) -> Overview:
        states = self.store.all_lesson_states(self.pid)
        total = len(self.cur.lessons)
        passed = sum(1 for s in states.values() if s["status"] == "passed" and s["lesson_id"] in self.cur.lessons)
        level_progress = {}
        for lv in self.cur.levels:
            ids = lv.lesson_ids
            level_progress[lv.id] = (sum(1 for l in ids if states.get(l, {}).get("status") == "passed"), len(ids))
        exams = {eid: self.store.best_exam(self.pid, eid) for eid in self.cur.exams}
        n_exams = len(self.cur.exams)
        exams_passed = sum(1 for eid in self.cur.exams if self.store.exam_passed(self.pid, eid))
        units = total + n_exams
        pct = 100.0 * (passed + exams_passed) / units if units else 0.0

        scores = [s["best_score"] for s in states.values() if s["best_score"] is not None]
        scores += [e["score"] for e in exams.values() if e]
        avg = sum(scores) / len(scores) if scores else None

        improvement: list[str] = []
        for lid, s in states.items():
            if lid not in self.cur.lessons:
                continue
            l = self.cur.lessons[lid]
            if s["status"] != "passed" and s["attempts"]:
                improvement.append(f"{l.code} {l.title} - not yet passed (best {s['best_score']:.0f}%)")
            elif s["status"] == "passed" and s["attempts"] >= 3:
                improvement.append(f"{l.code} {l.title} - needed {s['attempts']} attempts; worth revising")
        recent = self.store.assessments(self.pid, limit=8)
        for a in recent:
            if not a["passed"]:
                try:
                    for topic in json.loads(a["details"] or "{}").get("revision", [])[:3]:
                        item = f"Revise: {topic}"
                        if item not in improvement:
                            improvement.append(item)
                except json.JSONDecodeError:
                    pass

        return Overview(pct, passed, total, self.current_level(), level_progress, exams,
                        competency_label(avg, passed, exams_passed, len(self.cur.levels)), avg,
                        improvement[:10], recent, self.store.total_hints(self.pid))


def competency_label(avg: float | None, lessons_passed: int, exams_passed: int, n_levels: int) -> str:
    if avg is None or lessons_passed == 0:
        return "Not yet assessed"
    if exams_passed >= n_levels + 1:
        return "Linux administrator (all levels and final examination passed)"
    if exams_passed >= n_levels:
        return "Advanced practitioner - final examination outstanding"
    if exams_passed == 2:
        return "Intermediate practitioner - working towards Advanced"
    if exams_passed == 1:
        return "Competent beginner - working towards Intermediate"
    if avg >= 90:
        return "Beginner - strong progress"
    if avg >= 75:
        return "Beginner - developing"
    return "Beginner - needs more practice"

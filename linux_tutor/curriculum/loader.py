"""Load and validate the YAML curriculum.

Layout of a curriculum directory::

    curriculum.yaml          levels -> modules -> ordered lesson ids, exam ids
    glossary.yaml            term -> definition
    level1/*.yaml            one file per lesson (any file name; the `id` key matters)
    level2/*.yaml
    level3/*.yaml
    exams/*.yaml             level and final examinations

Adding a lesson = dropping a YAML file into a level directory and listing its id in
curriculum.yaml.  No application code changes are required.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import (QUESTION_TYPES, Exam, Exercise, Lesson, Level, Module, Question,
                     Quiz, Section)

log = logging.getLogger(__name__)


class CurriculumError(Exception):
    pass


@dataclass
class Curriculum:
    title: str
    levels: list[Level]
    lessons: dict[str, Lesson]
    exams: dict[str, Exam]
    glossary: dict[str, str]
    final_exam: str | None
    root: Path
    warnings: list[str] = field(default_factory=list)

    def level(self, level_id: str) -> Level:
        for lv in self.levels:
            if lv.id == level_id:
                return lv
        raise KeyError(level_id)

    def ordered_lessons(self, level_id: str | None = None) -> list[Lesson]:
        out = []
        for lv in self.levels:
            if level_id and lv.id != level_id:
                continue
            out.extend(self.lessons[lid] for lid in lv.lesson_ids if lid in self.lessons)
        return out

    def prerequisites(self, lesson_id: str) -> list[str]:
        """Explicit prerequisites, or by default the previous lesson in the same level."""
        lesson = self.lessons[lesson_id]
        if lesson.prerequisites is not None:
            return list(lesson.prerequisites)
        ids = self.level(lesson.level).lesson_ids
        idx = ids.index(lesson_id)
        return [ids[idx - 1]] if idx > 0 else []

    def module_title(self, level_id: str, module_id: str) -> str:
        for m in self.level(level_id).modules:
            if m.id == module_id:
                return m.title
        return module_id


def _load_yaml(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise CurriculumError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise CurriculumError(f"{path}: expected a mapping at the top level")
    return data


def parse_lesson(data: dict, source: str = "") -> Lesson:
    try:
        sections = [Section(title=s["title"], content=s.get("content", ""),
                            more=s.get("more", ""), examples=s.get("examples", []))
                    for s in data.get("sections", [])]
        exercises = [Exercise.from_dict(e) for e in data.get("exercises", [])]
        qdata = data.get("quiz", {}) or {}
        questions = [Question.from_dict(q, owner=data["id"]) for q in qdata.get("questions", [])]
        return Lesson(
            id=data["id"], level=data["level"], module=data.get("module", "general"),
            title=data["title"], objectives=data.get("objectives", []),
            sections=sections, exercises=exercises,
            quiz=Quiz(questions=questions, passing_score=qdata.get("passing_score")),
            summary=data.get("summary", ""), duration=data.get("duration", 20),
            prerequisites=data.get("prerequisites"), references=data.get("references", []),
            source=source,
        )
    except KeyError as exc:
        raise CurriculumError(f"{source}: missing required key {exc}") from exc


def parse_exam(data: dict, source: str = "") -> Exam:
    try:
        return Exam(
            id=data["id"], title=data["title"], level=data.get("level"),
            description=data.get("description", ""),
            questions=[Question.from_dict(q, owner=data["id"]) for q in data.get("questions", [])],
            sample_from_lessons=data.get("sample_from_lessons", 0),
            passing_score=data.get("passing_score"), time_limit=data.get("time_limit", 0),
            source=source,
        )
    except KeyError as exc:
        raise CurriculumError(f"{source}: missing required key {exc}") from exc


def load_curriculum(root: Path, strict: bool = False) -> Curriculum:
    root = Path(root)
    index = _load_yaml(root / "curriculum.yaml")

    lessons: dict[str, Lesson] = {}
    exams: dict[str, Exam] = {}
    for path in sorted(root.glob("level*/*.yaml")):
        lesson = parse_lesson(_load_yaml(path), source=str(path.relative_to(root)))
        if lesson.id in lessons:
            raise CurriculumError(f"duplicate lesson id {lesson.id} in {path}")
        lessons[lesson.id] = lesson
    for path in sorted((root / "exams").glob("*.yaml")):
        exam = parse_exam(_load_yaml(path), source=str(path.relative_to(root)))
        exams[exam.id] = exam

    levels = []
    for i, lv in enumerate(index.get("levels", []), start=1):
        modules = [Module(id=m["id"], title=m["title"], lessons=list(m.get("lessons", [])))
                   for m in lv.get("modules", [])]
        levels.append(Level(id=lv["id"], number=lv.get("number", i), title=lv["title"],
                            description=lv.get("description", ""), modules=modules,
                            exam=lv.get("exam")))

    glossary_path = root / "glossary.yaml"
    glossary = _load_yaml(glossary_path) if glossary_path.exists() else {}

    cur = Curriculum(title=index.get("title", "Linux Tutor"), levels=levels, lessons=lessons,
                     exams=exams, glossary={str(k): str(v) for k, v in glossary.items()},
                     final_exam=index.get("final_exam"), root=root)

    # Number lessons by position within their level.
    for lv in levels:
        for n, lid in enumerate(lv.lesson_ids, start=1):
            if lid in lessons:
                lessons[lid].number = n

    problems = validate(cur)
    cur.warnings = problems
    if problems and strict:
        raise CurriculumError("\n".join(problems))
    for p in problems:
        log.warning("curriculum: %s", p)
    return cur


def validate(cur: Curriculum) -> list[str]:
    """Return a list of human-readable problems.  An empty list means the curriculum is valid."""
    from ..assessment.checks import CHECKS, DIAGNOSTICS

    problems: list[str] = []
    listed: set[str] = set()
    for lv in cur.levels:
        for lid in lv.lesson_ids:
            if lid in listed:
                problems.append(f"lesson {lid} is listed more than once")
            listed.add(lid)
            if lid not in cur.lessons:
                problems.append(f"level {lv.id} lists unknown lesson {lid}")
            elif cur.lessons[lid].level != lv.id:
                problems.append(f"lesson {lid} declares level {cur.lessons[lid].level} "
                                f"but is listed under {lv.id}")
        if lv.exam and lv.exam not in cur.exams:
            problems.append(f"level {lv.id} references unknown exam {lv.exam}")
    for lid in cur.lessons:
        if lid not in listed:
            problems.append(f"lesson {lid} ({cur.lessons[lid].source}) is not listed in curriculum.yaml")
    if cur.final_exam and cur.final_exam not in cur.exams:
        problems.append(f"unknown final exam {cur.final_exam}")

    def check_exercise(ex: Exercise, where: str) -> None:
        if not ex.checks:
            problems.append(f"{where}: exercise {ex.id} has no checks")
        for spec in ex.checks + ex.constraints:
            _validate_check(spec, f"{where}/{ex.id}", CHECKS, problems)
        for diag in ex.diagnostics:
            if "message" not in diag:
                problems.append(f"{where}/{ex.id}: diagnostic without message")
            when = diag.get("when", {})
            t = when.get("type")
            if t not in CHECKS and t not in DIAGNOSTICS:
                problems.append(f"{where}/{ex.id}: unknown diagnostic type {t!r}")
        if len(ex.hints) < 4:
            problems.append(f"{where}: exercise {ex.id} has {len(ex.hints)} hints (4 expected)")

    def check_question(q: Question, where: str) -> None:
        if q.type not in QUESTION_TYPES:
            problems.append(f"{where}: question {q.id} has unknown type {q.type}")
        if q.is_practical:
            check_exercise(q.exercise, f"{where}/{q.id}")
            return
        if q.type in ("mcq", "interpret", "troubleshoot"):
            if not isinstance(q.answer, int) or not 0 <= q.answer < len(q.options):
                problems.append(f"{where}: question {q.id} answer index invalid")
        elif q.type == "multi":
            if not isinstance(q.answer, list) or any(
                    not isinstance(a, int) or not 0 <= a < len(q.options) for a in q.answer):
                problems.append(f"{where}: question {q.id} answers invalid")
        elif q.type == "truefalse":
            if not isinstance(q.answer, bool):
                problems.append(f"{where}: question {q.id} must have a true/false answer")
        elif q.type == "short":
            if not q.answer:
                problems.append(f"{where}: question {q.id} has no accepted answers")

    for lesson in cur.lessons.values():
        where = lesson.source or lesson.id
        if not lesson.sections:
            problems.append(f"{where}: no lecture sections")
        if not lesson.quiz.questions:
            problems.append(f"{where}: no end-of-lesson assessment questions")
        ids = [e.id for e in lesson.exercises] + [q.id for q in lesson.quiz.questions]
        if len(ids) != len(set(ids)):
            problems.append(f"{where}: duplicate exercise/question ids")
        for ex in lesson.exercises:
            check_exercise(ex, where)
        for q in lesson.quiz.questions:
            check_question(q, where)
        for pre in lesson.prerequisites or []:
            if pre not in cur.lessons:
                problems.append(f"{where}: unknown prerequisite {pre}")
    for exam in cur.exams.values():
        for q in exam.questions:
            check_question(q, exam.source or exam.id)
    return problems


def _validate_check(spec: dict, where: str, registry: dict, problems: list[str]) -> None:
    t = spec.get("type")
    if t in ("all_of", "any_of", "not"):
        subs = spec.get("checks") or ([spec["check"]] if "check" in spec else [])
        if not subs:
            problems.append(f"{where}: {t} without sub-checks")
        for s in subs:
            _validate_check(s, where, registry, problems)
        return
    if t not in registry:
        problems.append(f"{where}: unknown check type {t!r}")
        return
    missing = [a for a in registry[t].required if a not in spec]
    if missing:
        problems.append(f"{where}: check {t} missing {', '.join(missing)}")

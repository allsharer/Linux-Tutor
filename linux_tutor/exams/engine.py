"""End-of-lesson assessments and level/final examinations.

An :class:`AssessmentSession` holds an ordered list of questions, records the student's
answers, grades them (practical questions through the outcome-based
:class:`~linux_tutor.assessment.engine.AssessmentEngine`) and produces a
:class:`SessionResult` with score, pass/retry decision, explanations and revision areas.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..assessment.engine import AssessmentEngine, Evaluation, Outcome
from ..curriculum.loader import Curriculum
from ..curriculum.models import Exam, Lesson, Question


@dataclass
class QuestionResult:
    question: Question
    given: Any
    score: float              # 0..1
    correct: bool
    feedback: str = ""
    evaluation: Evaluation | None = None
    hints_used: int = 0


@dataclass
class SessionResult:
    kind: str                 # "lesson" | "exam"
    ref_id: str
    score_percent: float
    passed: bool
    passing_score: int
    results: list[QuestionResult]
    revision: list[str] = field(default_factory=list)
    hints_used: int = 0
    started: float = 0.0
    finished: float = 0.0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "ref_id": self.ref_id, "score": round(self.score_percent, 1),
            "passed": self.passed, "passing_score": self.passing_score,
            "hints_used": self.hints_used, "revision": self.revision,
            "questions": [{"id": r.question.id, "type": r.question.type, "score": r.score,
                           "correct": r.correct, "given": _jsonable(r.given),
                           "feedback": r.feedback,
                           "outcome": r.evaluation.outcome.value if r.evaluation else None}
                          for r in self.results],
        }


def _jsonable(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    return str(v)


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def grade_theory(q: Question, given: Any) -> tuple[float, str]:
    """Grade a non-practical question.  Returns (score 0..1, feedback)."""
    if q.type in ("mcq", "interpret", "troubleshoot"):
        ok = given is not None and int(given) == int(q.answer)
        right = q.options[q.answer] if q.options else ""
        return (1.0 if ok else 0.0), ("" if ok else f"The correct answer is: {right}. {q.explanation}".strip())
    if q.type == "multi":
        chosen = set(given or [])
        want = set(q.answer)
        ok = chosen == want
        rights = "; ".join(q.options[i] for i in sorted(want))
        return (1.0 if ok else 0.0), ("" if ok else f"The correct answers are: {rights}. {q.explanation}".strip())
    if q.type == "truefalse":
        ok = given is not None and bool(given) == bool(q.answer)
        return (1.0 if ok else 0.0), ("" if ok else
                                       f"The statement is {'true' if q.answer else 'false'}. {q.explanation}".strip())
    if q.type == "short":
        accepted = q.answer if isinstance(q.answer, list) else [q.answer]
        text = _norm_text(given or "")
        ok = False
        for a in accepted:
            a = str(a)
            if a.startswith("re:"):
                if re.fullmatch(a[3:], (given or "").strip(), re.I):
                    ok = True
            elif _norm_text(a) == text:
                ok = True
        shown = next((str(a) for a in accepted if not str(a).startswith("re:")), "")
        return (1.0 if ok else 0.0), ("" if ok else
                                       (f"A correct answer is: {shown}. " if shown else "") + q.explanation).strip()
    raise ValueError(f"cannot grade question type {q.type}")


class AssessmentSession:
    def __init__(self, kind: str, ref_id: str, questions: list[Question], passing_score: int,
                 engine: AssessmentEngine | None, practical_weight: float = 2.0,
                 topic_titles: dict[str, str] | None = None):
        self.kind = kind
        self.ref_id = ref_id
        self.questions = questions
        self.passing_score = passing_score
        self.engine = engine
        self.practical_weight = practical_weight
        self.topic_titles = topic_titles or {}
        self.results: dict[str, QuestionResult] = {}
        self.marks: dict[str, int] = {}          # practical question -> command-log mark
        self.hints: dict[str, int] = {}
        self.started = time.time()

    def weight(self, q: Question) -> float:
        if q.weight is not None:
            return float(q.weight)
        return self.practical_weight if q.is_practical else 1.0

    def prepare_practical(self, q: Question) -> None:
        if self.engine and q.exercise:
            self.marks[q.id] = self.engine.prepare(q.exercise)

    def use_hint(self, q: Question) -> str | None:
        n = self.hints.get(q.id, 0)
        hints = q.exercise.hints if q.exercise else []
        if n >= len(hints):
            return None
        self.hints[q.id] = n + 1
        return hints[n]

    def answer(self, q: Question, given: Any = None) -> QuestionResult:
        if q.is_practical:
            if self.engine is None:
                raise RuntimeError("practical questions need a laboratory")
            ev = self.engine.evaluate(q.exercise, answer=given, since=self.marks.get(q.id))
            res = QuestionResult(q, given, ev.score, ev.outcome.is_success, ev.summary(), ev,
                                 hints_used=self.hints.get(q.id, 0))
        else:
            score, fb = grade_theory(q, given)
            res = QuestionResult(q, given, score, score >= 1.0, fb)
        self.results[q.id] = res
        return res

    def finish(self) -> SessionResult:
        total_w = sum(self.weight(q) for q in self.questions) or 1.0
        got = 0.0
        ordered = []
        revision: list[str] = []
        for q in self.questions:
            r = self.results.get(q.id) or QuestionResult(q, None, 0.0, False, "Not answered.")
            ordered.append(r)
            got += self.weight(q) * r.score
            if not r.correct:
                topic = self.topic_titles.get(q.topic, q.topic)
                if topic and topic not in revision:
                    revision.append(topic)
                if r.evaluation:
                    for rv in r.evaluation.review:
                        t = self.topic_titles.get(rv, rv)
                        if t not in revision:
                            revision.append(t)
        pct = 100.0 * got / total_w
        return SessionResult(self.kind, self.ref_id, pct, pct >= self.passing_score, self.passing_score,
                             ordered, revision, sum(self.hints.values()), self.started, time.time())


# ---------------------------------------------------------------------- construction helpers
def lesson_session(cur: Curriculum, lesson: Lesson, engine: AssessmentEngine | None, config) -> AssessmentSession:
    passing = lesson.quiz.passing_score or int(config.get("assessment.passing_score", 80))
    titles = {lesson.id: f"{lesson.code} {lesson.title}"}
    for s in lesson.sections:
        titles[s.title] = f"{lesson.title}: {s.title}"
    titles.update({lid: f"{l.code} {l.title}" for lid, l in cur.lessons.items()})
    return AssessmentSession("lesson", lesson.id, list(lesson.quiz.questions), passing, engine,
                             float(config.get("assessment.practical_weight", 2.0)), titles)


def exam_questions(cur: Curriculum, exam: Exam, seed: int | None = None) -> list[Question]:
    """The exam's own questions plus a random sample of theory questions from its lessons."""
    rng = random.Random(seed)
    questions = list(exam.questions)
    if exam.sample_from_lessons:
        pool: list[Question] = []
        for lesson in cur.ordered_lessons(exam.level):
            pool += [q for q in lesson.quiz.questions if not q.is_practical]
        # Spread the sample across lessons: shuffle, then prefer one per lesson first.
        rng.shuffle(pool)
        seen_topics: set[str] = set()
        first, rest = [], []
        for q in pool:
            (rest if q.topic in seen_topics else first).append(q)
            seen_topics.add(q.topic)
        questions += (first + rest)[: exam.sample_from_lessons]
    theory = [q for q in questions if not q.is_practical]
    practical = [q for q in questions if q.is_practical]
    rng.shuffle(theory)
    return theory + practical


def exam_session(cur: Curriculum, exam: Exam, engine: AssessmentEngine | None, config,
                 seed: int | None = None) -> AssessmentSession:
    passing = exam.passing_score or int(config.get("assessment.exam_passing_score", 80))
    titles = {lid: f"{l.code} {l.title}" for lid, l in cur.lessons.items()}
    titles[exam.id] = exam.title
    return AssessmentSession("exam", exam.id, exam_questions(cur, exam, seed), passing, engine,
                             float(config.get("assessment.practical_weight", 2.0)), titles)

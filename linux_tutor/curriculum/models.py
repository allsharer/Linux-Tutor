"""Data model for the curriculum.

The model is deliberately plain (dataclasses built from YAML dictionaries) so that a
future curriculum-editor or web front end can reuse it unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

QUESTION_TYPES = ("mcq", "multi", "truefalse", "short", "practical", "interpret", "troubleshoot")


@dataclass
class Section:
    title: str
    content: str
    more: str = ""                     # "explain further" text, shown on request
    examples: list[dict] = field(default_factory=list)   # {command, explanation, output?}


@dataclass
class Exercise:
    id: str
    title: str
    instructions: str
    checks: list[dict]
    setup: str = ""
    cleanup: str = ""
    reference: str = ""                # one model solution, shown in the final hint
    method_patterns: list[str] = field(default_factory=list)  # regexes describing the "taught" method
    diagnostics: list[dict] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    explanation: str = ""
    answer_prompt: str = ""            # if set, the student also types an answer
    review: str = ""                   # section/lesson to review on failure
    weight: float = 1.0
    # --- used only by the automated curriculum tests (tests/test_curriculum_lab.py) ---
    solution: str = ""                 # script proving the exercise can be solved (default: reference)
    alternatives: list[str] = field(default_factory=list)    # other valid methods, must also pass
    wrong: list[dict] = field(default_factory=list)          # {run, expect} attempts that must NOT pass
    test_answer: str = ""              # answer typed by the test harness for answer exercises

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Exercise":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        known.setdefault("checks", [])
        known.setdefault("instructions", "")
        return cls(**known)


@dataclass
class Question:
    id: str
    type: str
    prompt: str
    options: list[str] = field(default_factory=list)
    answer: Any = None
    explanation: str = ""
    topic: str = ""                    # area to revise when answered incorrectly
    weight: float | None = None
    exercise: Exercise | None = None   # for practical questions
    output: str = ""                   # command output shown with interpret questions

    @property
    def is_practical(self) -> bool:
        return self.exercise is not None

    @classmethod
    def from_dict(cls, d: dict[str, Any], owner: str = "") -> "Question":
        qtype = d.get("type", "mcq")
        exercise = None
        if qtype == "practical" or "checks" in d:
            ex = dict(d)
            ex.setdefault("title", d.get("title", "Practical task"))
            ex.setdefault("instructions", d.get("prompt", ""))
            exercise = Exercise.from_dict(ex)
            qtype = "practical"
        return cls(
            id=str(d["id"]),
            type=qtype,
            prompt=d.get("prompt", d.get("instructions", "")),
            options=[str(o) for o in d.get("options", [])],
            answer=d.get("answer"),
            explanation=d.get("explanation", ""),
            topic=d.get("topic", owner),
            weight=d.get("weight"),
            exercise=exercise,
            output=d.get("output", ""),
        )


@dataclass
class Quiz:
    questions: list[Question]
    passing_score: int | None = None   # None -> configuration default


@dataclass
class Lesson:
    id: str
    level: str
    module: str
    title: str
    objectives: list[str]
    sections: list[Section]
    exercises: list[Exercise]
    quiz: Quiz
    summary: str = ""
    duration: int = 20
    prerequisites: list[str] | None = None
    references: list[dict] = field(default_factory=list)
    number: int = 0                    # assigned by the loader (position in level)
    source: str = ""

    @property
    def code(self) -> str:
        return f"{LEVEL_NUMBERS.get(self.level, 0)}.{self.number:02d}"


@dataclass
class Exam:
    id: str
    title: str
    level: str | None                  # None for the final examination
    description: str
    questions: list[Question]
    sample_from_lessons: int = 0       # extra theory questions drawn from lesson quizzes
    passing_score: int | None = None
    time_limit: int = 0                # minutes, 0 = untimed
    source: str = ""


@dataclass
class Module:
    id: str
    title: str
    lessons: list[str]


@dataclass
class Level:
    id: str
    number: int
    title: str
    description: str
    modules: list[Module]
    exam: str | None

    @property
    def lesson_ids(self) -> list[str]:
        return [lid for m in self.modules for lid in m.lessons]


LEVEL_NUMBERS = {"beginner": 1, "intermediate": 2, "advanced": 3}

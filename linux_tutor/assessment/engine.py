"""Outcome-based exercise evaluation.

Marking rule: an exercise is judged *only* on the state of the laboratory after the
student has worked.  The command log is consulted for one thing - telling the student
"you used a different method from the one in the lesson, and that is fine" - and for
optional diagnostic hints.  It never decides whether the work is correct.

Outcomes
--------
CORRECT                 every requirement met, no prohibited side effects
CORRECT_ALTERNATIVE     as above, achieved with a method other than the one taught
CORRECT_SIDE_EFFECTS    requirements met, but a safety constraint was violated
PARTIAL                 some requirements met
INCORRECT               no requirement met
UNVERIFIABLE            the lab could not be inspected (not the student's fault)
"""
from __future__ import annotations

import enum
import logging
import re
import shlex
from dataclasses import dataclass, field

from ..curriculum.models import Exercise
from ..lab.base import LabBackend, LabError
from .checks import CheckContext, CheckOutcome, run_check

log = logging.getLogger(__name__)


class Outcome(str, enum.Enum):
    CORRECT = "correct"
    CORRECT_ALTERNATIVE = "correct_alternative"
    CORRECT_SIDE_EFFECTS = "correct_side_effects"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    UNVERIFIABLE = "unverifiable"

    @property
    def is_success(self) -> bool:
        return self in (Outcome.CORRECT, Outcome.CORRECT_ALTERNATIVE)

    @property
    def label(self) -> str:
        return {
            "correct": "Correct",
            "correct_alternative": "Correct - alternative method",
            "correct_side_effects": "Correct, but with unwanted side effects",
            "partial": "Partially complete",
            "incorrect": "Not yet correct",
            "unverifiable": "Could not be verified",
        }[self.value]


# Credit awarded towards a quiz/exam score for each outcome.
SCORE = {
    Outcome.CORRECT: 1.0,
    Outcome.CORRECT_ALTERNATIVE: 1.0,
    Outcome.CORRECT_SIDE_EFFECTS: 0.5,
    Outcome.INCORRECT: 0.0,
    Outcome.UNVERIFIABLE: 0.0,
}


@dataclass
class CheckReport:
    description: str
    passed: bool
    message: str = ""


@dataclass
class Evaluation:
    outcome: Outcome
    score: float
    checks: list[CheckReport] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    feedback: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)
    method_note: str = ""
    commands: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [self.outcome.label + "."]
        parts += self.feedback
        if self.method_note:
            parts.append(self.method_note)
        return "\n".join(parts)


def _describe(spec: dict) -> str:
    if "describe" in spec:
        return spec["describe"]
    t = spec.get("type", "")
    for key in ("path", "name", "pattern", "target", "user", "run"):
        if key in spec:
            return f"{t.replace('_', ' ')}: {spec[key]}"
    return t.replace("_", " ")


class CommandLog:
    """Reads the per-lab command log written by the shell integration (/var/lib/tutor/cmdlog)."""

    PATH = "/var/lib/tutor/cmdlog"

    def __init__(self, lab: LabBackend):
        self.lab = lab

    def mark(self) -> int:
        try:
            r = self.lab.exec(f"wc -l < {self.PATH} 2>/dev/null || echo 0", timeout=15)
            return int(r.stdout.strip() or 0)
        except (LabError, ValueError):
            return 0

    def since(self, line: int) -> list[str]:
        try:
            r = self.lab.exec(f"tail -n +{int(line) + 1} {self.PATH} 2>/dev/null", timeout=15)
        except LabError:
            return []
        cmds = []
        for row in r.stdout.splitlines():
            parts = row.split("\t", 4)
            if len(parts) == 5 and parts[4].strip():
                cmds.append(parts[4])
        return cmds


class AssessmentEngine:
    def __init__(self, lab: LabBackend):
        self.lab = lab
        self.cmdlog = CommandLog(lab)

    # ------------------------------------------------------------------ setup
    def prepare(self, exercise: Exercise) -> int:
        """Run the exercise set-up script (as root) and return the command-log mark."""
        if exercise.setup:
            # Clear systemd's failed state / start-rate limits first, so that pressing
            # "Set up again" repeatedly can never trip StartLimitBurst.
            script = "systemctl reset-failed >/dev/null 2>&1\n" + self._expand(exercise.setup)
            r = self.lab.exec(script, user="root", timeout=120)
            if not r.ok:
                log.warning("setup of %s failed: %s", exercise.id, r.stderr)
                raise LabError(f"The exercise could not be prepared: {r.stderr.strip()[:300]}")
        return self.cmdlog.mark()

    def _expand(self, script: str) -> str:
        return script.replace("{home}", self.lab.student_home).replace("{user}", self.lab.student_user)

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, exercise: Exercise, answer: str | None = None, since: int | None = None) -> Evaluation:
        ctx = CheckContext(self.lab, answer)
        ctx.commands = self.cmdlog.since(since) if since is not None else []
        reports: list[CheckReport] = []
        try:
            for spec in exercise.checks:
                o = run_check(ctx, spec)
                reports.append(CheckReport(_describe(spec), o.passed, o.message))
            violations = []
            for spec in exercise.constraints:
                o = run_check(ctx, spec)
                if not o.passed:
                    violations.append(o.message)
        except LabError as exc:
            return Evaluation(Outcome.UNVERIFIABLE, 0.0, reports,
                              feedback=[f"The laboratory could not be inspected ({exc}). "
                                        "Your work has not been marked wrong - check that the lab is "
                                        "running (Lab > Lab status) and try again."])

        passed = sum(r.passed for r in reports)
        total = len(reports)
        if total and passed == total:
            outcome = Outcome.CORRECT_SIDE_EFFECTS if violations else Outcome.CORRECT
        elif passed:
            outcome = Outcome.PARTIAL
        else:
            outcome = Outcome.INCORRECT

        ev = Evaluation(outcome, 0.0, reports, violations, commands=ctx.commands)
        if outcome == Outcome.PARTIAL:
            ev.score = round(0.8 * passed / total, 3)
        else:
            ev.score = SCORE[outcome]

        if outcome.is_success:
            note = self._method_note(exercise, ctx.commands)
            if note:
                ev.outcome = Outcome.CORRECT_ALTERNATIVE
                ev.method_note = note
            ev.feedback.append("Well done - the laboratory is in exactly the state that was asked for.")
        elif outcome == Outcome.CORRECT_SIDE_EFFECTS:
            ev.feedback.append("You achieved the goal, but something else changed that should not have:")
            ev.feedback += [f"  - {v}" for v in violations]
            ev.feedback.append("In real administration work, unintended changes can be as harmful as "
                               "failing the task. Consider resetting the lab and trying again more carefully.")
        else:
            if outcome == Outcome.PARTIAL:
                ev.feedback.append(f"You are part of the way there: {passed} of {total} requirements are met.")
            ev.feedback += [r.message for r in reports if not r.passed and r.message]
            ev.feedback += self._diagnose(ctx, exercise, ev)
            if exercise.review:
                ev.review.append(exercise.review)
        return ev

    def _diagnose(self, ctx: CheckContext, exercise: Exercise, ev: Evaluation) -> list[str]:
        out = []
        for diag in exercise.diagnostics:
            try:
                o = run_check(ctx, diag.get("when", {}))
            except LabError:
                continue
            if o.passed:
                msg = diag["message"]
                try:
                    msg = msg.format(**o.values)
                except (KeyError, IndexError, ValueError):
                    pass
                out.append(msg)
                if diag.get("review"):
                    ev.review.append(diag["review"])
                if not diag.get("continue"):
                    break
        return out

    @staticmethod
    def _method_note(exercise: Exercise, commands: list[str]) -> str:
        if not commands:
            return ""
        patterns = list(exercise.method_patterns)
        if not patterns and exercise.reference:
            first = shlex.split(exercise.reference.splitlines()[0], comments=True) if exercise.reference.strip() else []
            if first:
                word = first[1] if first[0] == "sudo" and len(first) > 1 else first[0]
                patterns = [rf"(^|[;&|(\s]){re.escape(word)}(\s|$)"]
        if not patterns:
            return ""
        for cmd in commands:
            if any(re.search(p, cmd) for p in patterns):
                return ""
        return ("You reached the correct result with a different method from the one shown in the "
                "lesson. That is perfectly valid - Linux usually offers several ways to do the same job. "
                f"For comparison, the lesson's approach was: {exercise.reference.strip()}")

    def cleanup(self, exercise: Exercise) -> None:
        if exercise.cleanup:
            try:
                self.lab.exec(self._expand(exercise.cleanup), user="root", timeout=60)
            except LabError:
                pass

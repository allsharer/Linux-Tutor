"""Exercise every practical task in the curriculum against a real laboratory.

For each exercise (lesson exercises, practical assessment questions, exam tasks):

1. set up the task and evaluate *without doing anything* - must NOT be marked correct;
2. set up, run the model solution as the student          - must be marked correct;
3. set up, run each listed alternative method             - must be marked correct;
4. set up, run each listed wrong attempt                  - must give the expected outcome.

Usage:  python3 -m tests.lab_harness [ID-GLOB ...] [--keep]
"""
from __future__ import annotations

import fnmatch
import sys
import time

from linux_tutor import paths
from linux_tutor.assessment.engine import AssessmentEngine, Outcome
from linux_tutor.config import Config
from linux_tutor.curriculum.loader import load_curriculum
from linux_tutor.lab.podman import PodmanLab

SUDO_SHIM = ""  # the harness lab grants passwordless sudo instead (see main)


def iter_tasks(cur):
    for lesson in cur.ordered_lessons():
        for ex in lesson.exercises:
            yield f"{lesson.id}/{ex.id}", ex
        for q in lesson.quiz.questions:
            if q.is_practical:
                yield f"{lesson.id}/{q.id}", q.exercise
    for exam in cur.exams.values():
        for q in exam.questions:
            if q.is_practical:
                yield f"{exam.id}/{q.id}", q.exercise


def answer_for(lab, ex):
    if ex.test_answer:
        return ex.test_answer
    for c in ex.checks:
        if c.get("type") == "answer":
            if "equals" in c:
                return str(c["equals"])
            if "command" in c:
                return lab.exec(c["command"], user=c.get("user", "root")).stdout.strip()
    return None


def run_as_student(lab, script: str):
    return lab.exec(SUDO_SHIM + "cd ~\n" + script, user="student", timeout=120)


def check_task(lab, eng, name, ex, verbose=False):
    problems = []
    # 1. nothing done
    mark = eng.prepare(ex)
    ans = answer_for(lab, ex)
    ev = eng.evaluate(ex, answer=None if ans is None else "", since=mark)
    if ev.outcome.is_success:
        problems.append("passes without any work being done")
    # 2. model solution
    sol = ex.solution or ex.reference
    for label, script in [("solution", sol)] + [(f"alternative {i + 1}", a) for i, a in enumerate(ex.alternatives)]:
        if not script:
            problems.append(f"no {label}")
            continue
        mark = eng.prepare(ex)
        ans = answer_for(lab, ex)
        r = run_as_student(lab, script)
        ev = eng.evaluate(ex, answer=ans, since=mark)
        if not ev.outcome.is_success:
            problems.append(f"{label} not accepted ({ev.outcome.value}): {' | '.join(ev.feedback)[:300]}"
                            f"\n        script rc={r.returncode} stderr={r.stderr.strip()[:200]}")
        elif verbose:
            print(f"    {label}: {ev.outcome.value}")
    # 3. wrong attempts
    for w in ex.wrong:
        mark = eng.prepare(ex)
        ans = answer_for(lab, ex)
        run_as_student(lab, w["run"])
        ev = eng.evaluate(ex, answer=w.get("answer", ans), since=mark)
        want = w.get("expect", "not_success")
        ok = (not ev.outcome.is_success) if want == "not_success" else ev.outcome.value == want
        if not ok:
            problems.append(f"wrong attempt {w['run']!r} gave {ev.outcome.value}, expected {want}")
        if ok and w.get("feedback") and w["feedback"].lower() not in " ".join(ev.feedback).lower():
            problems.append(f"wrong attempt {w['run']!r}: feedback lacks {w['feedback']!r}: {ev.feedback}")
    eng.cleanup(ex)
    return problems


def main(argv):
    keep = "--keep" in argv
    verbose = "-v" in argv
    globs = [a for a in argv if not a.startswith("-")] or ["*"]
    cur = load_curriculum(paths.curriculum_dir())
    lab = PodmanLab(Config(), "harness", "test")
    if not keep:
        lab.reset()
    else:
        lab.ensure_running()
    # Only in this throw-away test lab: let scripted solutions use sudo without a password.
    lab.exec("echo 'student ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/zz-harness && chmod 440 /etc/sudoers.d/zz-harness")
    eng = AssessmentEngine(lab)
    failures = 0
    count = 0
    t0 = time.time()
    for name, ex in iter_tasks(cur):
        if not any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(name.split("/")[0], g) for g in globs):
            continue
        count += 1
        try:
            problems = check_task(lab, eng, name, ex, verbose)
        except Exception as exc:
            problems = [f"harness error: {exc}"]
        if problems:
            failures += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"     - {p}")
        else:
            print(f"ok   {name}")
    print(f"\n{count - failures}/{count} practical tasks verified in {time.time() - t0:.0f}s")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

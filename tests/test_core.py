"""Unit tests: configuration, curriculum, progress store, progression and grading.

These tests do not need Podman.
"""
import json

import pytest

from linux_tutor import paths
from linux_tutor.assessment.checks import CHECKS, CheckContext, run_check, _bits
from linux_tutor.assessment.engine import AssessmentEngine, Outcome
from linux_tutor.config import Config
from linux_tutor.curriculum.loader import load_curriculum, parse_lesson, validate
from linux_tutor.curriculum.models import Exercise, Question
from linux_tutor.exams.engine import AssessmentSession, exam_questions, grade_theory, lesson_session
from linux_tutor.lab.base import ExecResult, LabBackend, LabStatus
from linux_tutor.progress.progression import AVAILABLE, IN_PROGRESS, LOCKED, PASSED, Progression
from linux_tutor.progress.store import ProgressStore


@pytest.fixture(scope="module")
def cur():
    return load_curriculum(paths.curriculum_dir(), strict=True)


# ------------------------------------------------------------------ configuration
def test_config_defaults_and_user_override(tmp_path):
    c = Config()
    assert c.get("assessment.passing_score") == 80
    c.set("assessment.passing_score", 70)
    assert Config().get("assessment.passing_score") == 70


def test_instructor_lock(tmp_path, monkeypatch):
    sysfile = tmp_path / "etc-config.json"
    sysfile.write_text(json.dumps({"assessment": {"passing_score": 90},
                                   "instructor": {"locked": ["assessment.passing_score"]}}))
    c = Config()
    assert c.get("assessment.passing_score") == 90
    with pytest.raises(PermissionError):
        c.set("assessment.passing_score", 50)
    # a user file cannot override a locked key either
    (paths.config_dir()).mkdir(parents=True, exist_ok=True)
    (paths.config_dir() / "config.json").write_text(json.dumps({"assessment": {"passing_score": 10}}))
    assert Config().get("assessment.passing_score") == 90


def test_paths_are_relocatable(tmp_path):
    assert str(paths.database_file()).startswith(str(tmp_path))
    assert paths.curriculum_dir().joinpath("curriculum.yaml").is_file()


# ------------------------------------------------------------------ curriculum
def test_curriculum_complete(cur):
    assert [lv.id for lv in cur.levels] == ["beginner", "intermediate", "advanced"]
    assert len(cur.level("beginner").lesson_ids) == 20
    assert len(cur.level("intermediate").lesson_ids) == 23
    assert len(cur.level("advanced").lesson_ids) == 22
    assert cur.final_exam in cur.exams
    assert not cur.warnings


def test_every_lesson_has_assessment_with_practical(cur):
    for lesson in cur.lessons.values():
        assert lesson.objectives, lesson.id
        assert len(lesson.sections) >= 2, lesson.id
        assert lesson.quiz.questions, lesson.id
        assert any(q.is_practical for q in lesson.quiz.questions), f"{lesson.id} has no practical question"
        for ex in lesson.exercises + [q.exercise for q in lesson.quiz.questions if q.is_practical]:
            assert len(ex.hints) == 4, f"{lesson.id}/{ex.id} needs 4 progressive hints"
            assert ex.reference or ex.solution, f"{lesson.id}/{ex.id} has no model solution"


def test_level_exams_cover_levels(cur):
    for lv in cur.levels:
        exam = cur.exams[lv.exam]
        assert exam.level == lv.id
        assert any(q.is_practical for q in exam.questions)
        qs = exam_questions(cur, exam, seed=1)
        assert len(qs) == len(exam.questions) + exam.sample_from_lessons
        # theory first, practical last
        kinds = [q.is_practical for q in qs]
        assert kinds == sorted(kinds)


def test_validator_reports_problems():
    bad = parse_lesson({"id": "x1", "level": "beginner", "title": "X", "sections": [],
                        "exercises": [{"id": "e", "title": "E", "checks": [{"type": "no_such_check"}],
                                       "hints": ["a"]}],
                        "quiz": {"questions": [{"id": "q", "type": "mcq", "prompt": "?", "options": ["a"], "answer": 5}]}})
    from linux_tutor.curriculum.loader import Curriculum
    c = Curriculum("t", [], {"x1": bad}, {}, {}, None, paths.curriculum_dir())
    problems = "\n".join(validate(c))
    assert "unknown check type" in problems
    assert "answer index invalid" in problems
    assert "no lecture sections" in problems
    assert "not listed" in problems


def test_default_prerequisite_is_previous_lesson(cur):
    ids = cur.level("beginner").lesson_ids
    assert cur.prerequisites(ids[0]) == []
    assert cur.prerequisites(ids[5]) == [ids[4]]


# ------------------------------------------------------------------ grading
def q(**kw):
    return Question.from_dict({"id": "q", "prompt": "p", **kw})


def test_grade_theory_types():
    assert grade_theory(q(type="mcq", options=["a", "b"], answer=1), 1)[0] == 1.0
    assert grade_theory(q(type="mcq", options=["a", "b"], answer=1), 0)[0] == 0.0
    assert grade_theory(q(type="multi", options=list("abcd"), answer=[0, 2]), [2, 0])[0] == 1.0
    assert grade_theory(q(type="multi", options=list("abcd"), answer=[0, 2]), [0])[0] == 0.0
    assert grade_theory(q(type="truefalse", answer=False), False)[0] == 1.0
    assert grade_theory(q(type="truefalse", answer=False), None)[0] == 0.0
    short = q(type="short", answer=["chmod o-w data.csv", r"re:chmod\s+o-w\s+data\.csv"])
    assert grade_theory(short, "  chmod   o-w data.csv ")[0] == 1.0
    assert grade_theory(short, "CHMOD o-w data.csv")[0] == 1.0
    assert grade_theory(short, "chmod 755 data.csv")[0] == 0.0
    score, fb = grade_theory(q(type="mcq", options=["x", "y"], answer=0, explanation="Because."), 1)
    assert "x" in fb and "Because." in fb


def test_session_scoring_weights_practical(cur):
    lesson = cur.lessons["b08-directories"]
    session = lesson_session(cur, lesson, engine=None, config=Config())
    theory = [x for x in session.questions if not x.is_practical]
    practical = [x for x in session.questions if x.is_practical]
    for t in theory:
        session.answer(t, t.answer if t.type != "short" else t.answer[0])
    res = session.finish()
    total = len(theory) + 2.0 * len(practical)
    assert res.score_percent == pytest.approx(100 * len(theory) / total)
    assert not res.passed            # practical work not submitted -> cannot pass on theory alone
    assert res.revision              # the unanswered practical topic is listed for revision


# ------------------------------------------------------------------ store & progression
@pytest.fixture
def store(tmp_path):
    s = ProgressStore(tmp_path / "t.db")
    yield s
    s.close()


class _Result:
    def __init__(self, kind, ref, score, passed):
        self.kind, self.ref_id, self.score_percent, self.passed = kind, ref, score, passed
        self.passing_score, self.hints_used, self.started, self.finished = 80, 1, 0.0, 1.0
        self.revision = []

    def to_dict(self):
        return {"kind": self.kind, "ref_id": self.ref_id, "score": self.score_percent,
                "passed": self.passed, "revision": self.revision}


def test_profiles_and_records(store):
    p = store.create_profile("alex", "Alex L")
    with pytest.raises(Exception):
        store.create_profile("alex")
    store.start_lesson(p.id, "b01-introduction")
    store.set_section(p.id, "b01-introduction", 3)
    assert store.lesson_state(p.id, "b01-introduction")["section_index"] == 3
    store.record_assessment(p.id, _Result("lesson", "b01-introduction", 60, False))
    assert not store.is_passed(p.id, "b01-introduction")
    store.record_assessment(p.id, _Result("lesson", "b01-introduction", 90, True))
    st = store.lesson_state(p.id, "b01-introduction")
    assert st["status"] == "passed" and st["attempts"] == 2 and st["best_score"] == 90
    store.record_exercise(p.id, "b01-introduction", "whoami", "correct", 2)
    assert store.exercise_summary(p.id, "b01-introduction")["whoami"]["hints"] == 2
    assert store.total_hints(p.id) == 4


def test_export_import_backup_restore(store, tmp_path):
    p = store.create_profile("sam")
    store.record_assessment(p.id, _Result("lesson", "b01-introduction", 85, True))
    data = store.export_profile(p.id)
    json.dumps(data)  # serialisable
    q = store.import_profile(data, rename="sam2")
    assert store.is_passed(q.id, "b01-introduction")
    with pytest.raises(ValueError):
        store.import_profile(data)            # username exists
    backup = store.backup(tmp_path / "backup.db")
    store.delete_profile(p.id)
    store.close()
    ProgressStore.restore(backup, tmp_path / "t.db")
    s2 = ProgressStore(tmp_path / "t.db")
    assert any(x.username == "sam" for x in s2.profiles())
    s2.close()


def test_progression_locks_and_unlocks(cur, store):
    p = store.create_profile("pat")
    prog = Progression(cur, store, p.id, Config())
    ids = cur.level("beginner").lesson_ids
    assert prog.lesson_status(ids[0]) == AVAILABLE
    assert prog.lesson_status(ids[1]) == LOCKED
    assert not prog.level_unlocked("intermediate")
    store.start_lesson(p.id, ids[0])
    assert prog.lesson_status(ids[0]) == IN_PROGRESS
    # reading a lesson does not unlock the next one - passing its assessment does
    store.record_assessment(p.id, _Result("lesson", ids[0], 70, False))
    assert prog.lesson_status(ids[1]) == LOCKED
    store.record_assessment(p.id, _Result("lesson", ids[0], 95, True))
    assert prog.lesson_status(ids[0]) == PASSED
    assert prog.lesson_status(ids[1]) == AVAILABLE
    assert not prog.exam_available("exam-beginner")
    for lid in ids:
        store.record_assessment(p.id, _Result("lesson", lid, 90, True))
    assert prog.exam_available("exam-beginner")
    assert not prog.level_unlocked("intermediate")
    store.record_assessment(p.id, _Result("exam", "exam-beginner", 85, True))
    assert prog.level_unlocked("intermediate")
    assert prog.lesson_status(cur.level("intermediate").lesson_ids[0]) == AVAILABLE
    assert not prog.exam_available("exam-final")
    ov = prog.overview()
    assert ov.lessons_passed == 20 and ov.current_level == "intermediate"
    assert "Competent beginner" in ov.competency


def test_unlock_all_instructor_mode(cur, store):
    p = store.create_profile("teacher")
    c = Config()
    c.data["instructor"]["unlock_all"] = True
    prog = Progression(cur, store, p.id, c)
    assert prog.lesson_status("a22-scenarios") == AVAILABLE
    assert prog.exam_available("exam-final")


# ------------------------------------------------------------------ engine logic with a fake lab
class FakeLab(LabBackend):
    """Answers check scripts from a table of (substring -> ExecResult)."""

    def __init__(self, table):
        self.table = table
        self.scripts = []

    def exec(self, script, user="root", timeout=None, stdin=None):
        self.scripts.append(script)
        for key, res in self.table.items():
            if key in script:
                return res
        return ExecResult(1, "", "")

    def status(self): return LabStatus()
    def ensure_running(self, progress=None): pass
    def shell_argv(self, user=None): return []
    def reset(self, progress=None): pass
    def stop(self): pass


def _ex(**kw):
    base = {"id": "e", "title": "t", "instructions": "", "hints": ["1", "2", "3", "4"]}
    base.update(kw)
    return Exercise.from_dict(base)


def test_outcome_classification():
    ok = ExecResult(0, "DIR\n", "")
    ex = _ex(checks=[{"type": "dir_exists", "path": "~/a"}, {"type": "dir_exists", "path": "~/b"}],
             constraints=[{"type": "file_exists", "path": "~/keep"}], reference="mkdir ~/a ~/b")
    # everything right
    lab = FakeLab({"/home/student/a": ok, "/home/student/b": ok, "/home/student/keep": ExecResult(0, "FILE\n", ""),
                   "cmdlog": ExecResult(0, "", "")})
    assert AssessmentEngine(lab).evaluate(ex).outcome == Outcome.CORRECT
    # one of two
    lab = FakeLab({"/home/student/a": ok, "/home/student/keep": ExecResult(0, "FILE\n", "")})
    ev = AssessmentEngine(lab).evaluate(ex)
    assert ev.outcome == Outcome.PARTIAL and 0 < ev.score < 1
    # side effect
    lab = FakeLab({"/home/student/a": ok, "/home/student/b": ok, "/home/student/keep": ExecResult(0, "NONE\n", "")})
    ev = AssessmentEngine(lab).evaluate(ex)
    assert ev.outcome == Outcome.CORRECT_SIDE_EFFECTS and ev.score == 0.5
    # nothing
    lab = FakeLab({"/home/student": ExecResult(0, "NONE\n", "")})
    assert AssessmentEngine(lab).evaluate(ex).outcome == Outcome.INCORRECT


def test_alternative_method_is_recognised_but_still_correct():
    ex = _ex(checks=[{"type": "dir_exists", "path": "~/a"}], reference="mkdir ~/a")
    log = "1\tstudent\t/home/student\t0\tinstall -d ~/a\n"
    lab = FakeLab({"tail -n +": ExecResult(0, log, ""), "/home/student/a": ExecResult(0, "DIR\n", "")})
    ev = AssessmentEngine(lab).evaluate(ex, since=0)
    assert ev.outcome == Outcome.CORRECT_ALTERNATIVE
    assert ev.outcome.is_success and ev.score == 1.0
    log = "1\tstudent\t/home/student\t0\tmkdir ~/a\n"
    lab = FakeLab({"tail -n +": ExecResult(0, log, ""), "/home/student/a": ExecResult(0, "DIR\n", "")})
    assert AssessmentEngine(lab).evaluate(ex, since=0).outcome == Outcome.CORRECT


def test_lab_failure_is_unverifiable_not_wrong():
    from linux_tutor.lab.base import LabError

    class Broken(FakeLab):
        def exec(self, *a, **k):
            raise LabError("container stopped")
    ev = AssessmentEngine(Broken({})).evaluate(_ex(checks=[{"type": "dir_exists", "path": "/x"}]))
    assert ev.outcome == Outcome.UNVERIFIABLE
    assert "not been marked wrong" in " ".join(ev.feedback)


def test_diagnostics_explain_mistakes():
    ex = _ex(checks=[{"type": "dir_exists", "path": "~/projects"}],
             diagnostics=[{"when": {"type": "find", "name": "projects", "kind": "d"},
                           "message": "Created at {found} instead.", "review": "b06-paths"}])
    lab = FakeLab({"find ": ExecResult(0, "/tmp/projects\n", ""), "test -d": ExecResult(0, "NONE\n", "")})
    ev = AssessmentEngine(lab).evaluate(ex)
    assert "Created at /tmp/projects instead." in ev.feedback
    assert "b06-paths" in ev.review


def test_answer_check_and_mode_bits():
    lab = FakeLab({"uname -r": ExecResult(0, "6.8.0\n", "")})
    ctx = CheckContext(lab, answer=" 6.8.0 ")
    assert run_check(ctx, {"type": "answer", "command": "uname -r"}).passed
    ctx = CheckContext(lab, answer="")
    assert not run_check(ctx, {"type": "answer", "equals": "x"}).passed
    assert _bits("u+x") == 0o100 and _bits("g+rwx,g+s".split(",")[1]) == 0o2000
    assert _bits("o+t") == 0o1000 and _bits("a+r") == 0o444


def test_check_registry_is_extensible():
    from linux_tutor.assessment.checks import CheckOutcome, check

    @check("always_true_for_test")
    def _t(ctx, spec):
        return CheckOutcome(True)
    assert "always_true_for_test" in CHECKS
    assert run_check(CheckContext(FakeLab({})), {"type": "always_true_for_test"}).passed
    del CHECKS["always_true_for_test"]

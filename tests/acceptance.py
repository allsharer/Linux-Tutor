"""End-to-end acceptance test driving the real application, as a student would.

Runs against whatever installation is importable (source tree or /usr/share/linux-tutor),
with the REAL laboratory, REAL terminal (PTY + podman exec) and REAL database:

  phase 1   create a profile, open lesson 1.01, read pages, type commands into the
            terminal widget, solve both exercises, take and pass the assessment
  phase 2   (new process) progress persisted?  reset the laboratory: progress kept,
            lab clean?
  phase 3   locked lesson refused, next lesson available, practice mode works

Usage:  QT_QPA_PLATFORM=offscreen python3 tests/acceptance.py [phase1|phase2|phase3|all]
Exit status 0 = all checks passed.
"""
import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from linux_tutor.ui.qt import QEventLoop, QTimer  # noqa: E402
from linux_tutor.ui.qt import QApplication, QMessageBox  # noqa: E402

from linux_tutor import paths  # noqa: E402
from linux_tutor.config import Config  # noqa: E402
from linux_tutor.curriculum.loader import load_curriculum  # noqa: E402
from linux_tutor.progress.store import ProgressStore  # noqa: E402
from linux_tutor.ui import main_window as mw  # noqa: E402
from linux_tutor.ui.terminal_widget import TerminalWidget  # noqa: E402

USER = "acceptance"
results = []


def check(cond, what):
    results.append((bool(cond), what))
    print(("  PASS  " if cond else "  FAIL  ") + what, flush=True)
    return cond


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_for(pred, timeout=60, step=200):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        wait(step)
    return False


def terminal(w) -> TerminalWidget:
    for i in range(w.terms.count()):
        t = w.terms.widget(i)
        if isinstance(t, TerminalWidget) and not getattr(t, "practice", False):
            return t
    raise RuntimeError("no lab terminal")


def type_cmd(w, cmd, settle=1500):
    t = terminal(w)
    t.send_text(cmd, execute=True)
    wait(settle)


def make_window(app, cfg, cur, store, profile):
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    w = mw.MainWindow(cfg, cur, store, profile)
    w.resize(1400, 900)
    w.show()
    return w


def phase1(app):
    print("Phase 1: first session")
    cfg, cur = Config(), load_curriculum(paths.curriculum_dir())
    store = ProgressStore(paths.database_file())
    old = next((p for p in store.profiles() if p.username == USER), None)
    if old:
        store.delete_profile(old.id)
    profile = store.create_profile(USER, "Acceptance Student")
    check(profile.id, "profile created")
    w = make_window(app, cfg, cur, store, profile)
    check(wait_for(lambda: w.lab_ready, 180), "laboratory started and passed its health check")
    check(wait_for(lambda: terminal(w).running(), 30), "terminal connected to the laboratory")
    wait(2500)
    type_cmd(w, "whoami; hostname")
    scr = terminal(w).screen_text()
    check("student" in scr and "linuxlab" in scr, "real Bash in the lab answers commands typed in the terminal")

    w.open_lesson("b01-introduction")
    check(w.stack.currentWidget() is w.lecture, "lesson 1.01 opened in the lecture screen")
    for i in range(1, w.lecture.page_count):
        w.lecture.go(i)
    check(w.lecture.next_btn.text() == "Start assessment", "navigated through every lecture page")
    w.lecture.tryCommand.emit("uname -r")
    wait(800)
    check("uname -r" in terminal(w).screen_text(), "'Try it' typed the example into the terminal")
    type_cmd(w, "", 800)

    # Exercise 1: whoami (answer box), exercise 2: kernel version (answer from the lab)
    panel = w.ex_panel
    for row, answer_cmd in ((0, "whoami"), (1, "uname -r")):
        panel.list.setCurrentRow(row)
        panel._prepare()
        check(wait_for(lambda: panel.task.prepared, 60), f"exercise {row + 1} set up in the lab")
        out = subprocess.run(["podman", "exec", "-u", "student", w.lab.name, "bash", "-c", answer_cmd],
                             capture_output=True, text=True).stdout.strip()
        type_cmd(w, answer_cmd)
        panel.task.answer.setText(out)
        panel._check()
        check(wait_for(lambda: "Correct" in panel.task.status.text() or "correct" in panel.task.status.text(), 60),
              f"exercise {row + 1} marked correct ({panel.task.status.text()[:60]!r})")
    # A wrong answer must not be accepted and must be explained
    panel.list.setCurrentRow(0)
    panel.task.prepared = False
    panel._prepare()
    wait_for(lambda: panel.task.prepared and panel.task.check_btn.isEnabled(), 60)
    panel.task.answer.setText("root")
    panel._check()
    wait_for(lambda: "Not yet" in panel.task.status.text(), 60)
    check("Not yet correct" in panel.task.status.text(), "a wrong answer is not accepted")
    check(len(panel.task.feedback.toPlainText()) > 20, "the mistake is explained")
    panel.task.show_hint(); panel._hint()
    check(panel.hints.get("whoami", 0) >= 1, "hints are available and recorded")

    # Assessment
    w.start_lesson_assessment()
    wait_for(lambda: w.assess.active, 60)
    check(w.stack.currentWidget() is w.assess and w.assess.active, "end-of-lesson assessment started")
    s = w.assess.session
    for i, q in enumerate(s.questions):
        w.assess._goto(i)
        if q.is_practical:
            w.assess._prepare_practical()
            wait_for(lambda: w.assess.practical.prepared, 60)
            out = subprocess.run(["podman", "exec", w.lab.name, "hostname"], capture_output=True, text=True).stdout.strip()
            w.assess.practical.answer.setText(out)
            w.assess._submit_practical()
            wait_for(lambda: q.id in s.results, 60)
        else:
            w.assess.answers[q.id] = q.answer if q.type != "short" else q.answer[0]
    w.assess._finish()
    check(w.store.is_passed(profile.id, "b01-introduction"), "assessment passed and recorded as competency")
    check("PASSED" in w.assess.results.toPlainText(), "results screen shows the pass decision")
    check(w.prog.lesson_status("b02-distributions") == "available", "next lesson unlocked")
    type_cmd(w, "echo persistent > ~/marker.txt")
    w.close()
    wait(500)
    store.close()


def phase2(app):
    print("Phase 2: restart, persistence and laboratory reset")
    cfg, cur = Config(), load_curriculum(paths.curriculum_dir())
    store = ProgressStore(paths.database_file())
    profile = next(p for p in store.profiles() if p.username == USER)
    check(store.is_passed(profile.id, "b01-introduction"), "progress survived an application restart")
    att = store.assessments(profile.id, "lesson", "b01-introduction")
    check(att and att[0]["passed"] == 1, "assessment record persisted")
    w = make_window(app, cfg, cur, store, profile)
    check(wait_for(lambda: w.lab_ready, 180), "laboratory restarted")
    r = w.lab.exec("cat /home/student/marker.txt", user="student")
    check("persistent" in r.stdout, "lab contents persist between sessions until reset")
    w._closing = True                      # as the Reset menu action does: no auto-reconnect
    for i in range(w.terms.count()):
        w.terms.widget(i).stop()
    w.lab.reset()
    w._closing = False
    r = w.lab.exec("test -e /home/student/marker.txt && echo present || echo gone", user="student")
    check("gone" in r.stdout, "laboratory reset restored a clean system")
    check(store.is_passed(profile.id, "b01-introduction"), "academic records unaffected by the reset")
    w.close()
    wait(300)
    store.close()


def phase3(app):
    print("Phase 3: progression rules and practice mode")
    cfg, cur = Config(), load_curriculum(paths.curriculum_dir())
    store = ProgressStore(paths.database_file())
    profile = next(p for p in store.profiles() if p.username == USER)
    w = make_window(app, cfg, cur, store, profile)
    w.open_lesson("b05-filesystem", quiet=True)
    check(w.current_lesson != "b05-filesystem", "locked lesson cannot be opened")
    w.open_lesson("b02-distributions")
    check(w.current_lesson == "b02-distributions", "unlocked lesson opens")
    w.show_practice()
    check(wait_for(lambda: w.practice_ready, 180), "practice laboratory started")
    pt = next(w.terms.widget(i) for i in range(w.terms.count()) if getattr(w.terms.widget(i), "practice", False))
    check(wait_for(lambda: pt.running(), 30), "practice terminal connected")
    check(w.practice_lab.name != w.lab.name, "practice mode uses a separate laboratory")
    w.close()
    wait(300)
    store.close()


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("phase1", phase1), ("phase2", phase2), ("phase3", phase3)):
        if phase in (name, "all"):
            fn(app)
    failed = [w for ok, w in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} acceptance checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

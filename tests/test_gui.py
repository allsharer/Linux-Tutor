"""GUI smoke tests (offscreen Qt).  They drive the real widgets: open a lesson, navigate the
lecture, take an assessment, check that the result is recorded and that the next lesson
unlocks.  The laboratory is not needed for these (theory-only assessment path)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from linux_tutor.ui.qt import QApplication  # noqa: E402

from linux_tutor import paths  # noqa: E402
from linux_tutor.config import Config  # noqa: E402
from linux_tutor.curriculum.loader import load_curriculum  # noqa: E402
from linux_tutor.progress.store import ProgressStore  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch):
    from linux_tutor.ui import main_window as mw
    monkeypatch.setattr(mw.MainWindow, "_startup_lab", lambda self: None)   # no container needed
    cur = load_curriculum(paths.curriculum_dir())
    store = ProgressStore(paths.database_file())
    profile = store.create_profile("gui", "GUI Tester")
    w = mw.MainWindow(Config(), cur, store, profile)
    w.show()
    yield w
    w.assess.session = None
    for i in range(w.terms.count()):
        w.terms.widget(i).stop()
    w.hide()
    store.close()


def test_lesson_navigation_and_resume(window):
    w = window
    w.open_lesson("b01-introduction")
    assert w.stack.currentWidget() is w.lecture
    assert "Introduction to Linux" in w.lecture.header.text()
    w.lecture.go(2)
    assert w.store.lesson_state(w.profile.id, "b01-introduction")["section_index"] == 2
    # locked lesson is refused
    w.open_lesson("b05-filesystem", quiet=True)
    assert w.current_lesson == "b01-introduction"
    # resume at the saved page
    w.open_lesson("b01-introduction")
    assert w.lecture.index == 2


def test_assessment_records_result_and_unlocks(window, monkeypatch):
    w = window
    w.open_lesson("b01-introduction")
    lesson = w.cur.lessons["b01-introduction"]
    # Answer only the theory questions perfectly, and treat the practical one as submitted correctly.
    from linux_tutor.exams.engine import lesson_session
    session = lesson_session(w.cur, lesson, None, w.config)
    w.assess.start(session, "test")
    for q in session.questions:
        if q.is_practical:
            from linux_tutor.exams.engine import QuestionResult
            session.results[q.id] = QuestionResult(q, None, 1.0, True, "ok")
        else:
            w.assess.answers[q.id] = q.answer if q.type != "short" else q.answer[0]
    from linux_tutor.ui.qt import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    w.assess._finish()
    assert w.store.is_passed(w.profile.id, "b01-introduction")
    assert w.prog.lesson_status("b02-distributions") == "available"
    assert "PASSED" in w.assess.results.toPlainText()


def test_dashboard_glossary_theme(window):
    w = window
    w.show_dashboard()
    assert "Course completed" in w.dashboard.browser.toPlainText()
    w._set_ui("ui.theme", "light")
    w._bump_font(2)
    assert w.config.get("ui.theme") == "light"
    from linux_tutor.ui.dialogs import GlossaryDialog
    g = GlossaryDialog(w.cur.glossary, "inode")
    assert g.list.count() >= 1


def test_terminal_emulator_renders(app):
    from linux_tutor.ui.terminal_widget import TerminalWidget
    t = TerminalWidget()
    t.resize(600, 300)
    t.feed_text("\x1b[1;32mhello\x1b[0m world\n")
    assert "hello world" in t.screen_text()
    t.grab()   # paints without error


def test_terminal_key_mapping(app):
    """Keyboard events become the byte sequences a real terminal sends (both Qt bindings)."""
    from linux_tutor.ui.qt import QEvent, QKeyEvent, Qt
    from linux_tutor.ui.terminal_widget import TerminalWidget
    t = TerminalWidget()
    sent = []
    t.session = object()                     # pretend a session is attached
    t._send = sent.append
    K, M = Qt.Key, Qt.KeyboardModifier

    def press(key, mods=M.NoModifier, text=""):
        t.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, text))

    press(K.Key_C, M.ControlModifier)
    press(K.Key_Up)
    press(K.Key_Tab, text="\t")
    press(K.Key_Return, text="\r")
    press(K.Key_A, text="a")
    press(K.Key_B, M.AltModifier, "b")
    press(K.Key_Left, M.ControlModifier)
    assert sent == [b"\x03", b"\x1b[A", b"\t", b"\r", b"a", b"\x1bb", b"\x1b[1;5D"]
    t.session = None

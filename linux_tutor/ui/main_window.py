"""Main window: navigation | (lecture / assessment / dashboard) over terminal | exercises."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from .qt import QSettings, Qt, QTimer
from .qt import QAction, QKeySequence
from .qt import (QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox,
                               QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, paths
from ..assessment.engine import AssessmentEngine
from ..curriculum.loader import Curriculum
from ..exams.engine import exam_session, lesson_session
from ..lab import LabError, create_lab
from ..progress.progression import LOCKED, Progression
from ..progress.store import ProgressStore
from .assessment_view import AssessmentView
from .dialogs import GlossaryDialog, LabDialog, ProfileDialog, SettingsDialog, about_text
from .exercise_panel import ExercisePanel
from .lecture_view import LectureView
from .nav_panel import NavPanel
from .pages import DashboardPage, ExamIntroPage, PracticePage, WelcomePage
from .terminal_widget import TerminalWidget
from .theme import apply_theme
from .workers import run_task

log = logging.getLogger(__name__)

PAGE_WELCOME, PAGE_LECTURE, PAGE_ASSESS, PAGE_DASH, PAGE_PRACTICE, PAGE_EXAM = range(6)


class MainWindow(QMainWindow):
    def __init__(self, config, cur: Curriculum, store: ProgressStore, profile):
        super().__init__()
        self.config, self.cur, self.store, self.profile = config, cur, store, profile
        self.prog = Progression(cur, store, profile.id, config)
        key = f"{profile.id}-{profile.username}"
        self.lab = create_lab(config, key, "lesson")
        self.practice_lab = create_lab(config, key, "practice")
        self.engine = AssessmentEngine(self.lab)
        self.lab_ready = False
        self.practice_ready = False
        self._lab_waiters: list = []
        self._lab_starting = False
        self.current_lesson: str | None = None
        self.current_exam: str | None = None
        self.settings = QSettings(str(paths.config_dir() / "window.ini"), QSettings.Format.IniFormat)

        self.setWindowTitle(f"{APP_NAME} - {profile.display_name}")
        theme, fs = config.get("ui.theme"), int(config.get("ui.font_size"))

        # --- panels
        self.nav = NavPanel(cur, theme)
        self.nav.lessonSelected.connect(self.open_lesson)
        self.nav.examSelected.connect(self.open_exam)
        self.nav.dashboardSelected.connect(self.show_dashboard)
        self.nav.practiceSelected.connect(self.show_practice)

        self.stack = QStackedWidget()
        self.welcome = WelcomePage(theme, fs)
        self.welcome.go_btn.clicked.connect(self.continue_learning)
        self.lecture = LectureView(cur, theme, fs)
        self.lecture.default_pass = int(config.get("assessment.passing_score", 80))
        self.lecture.tryCommand.connect(self.try_command)
        self.lecture.sectionChanged.connect(self._section_changed)
        self.lecture.startAssessment.connect(self.start_lesson_assessment)
        self.lecture.showGlossary.connect(self.show_glossary)
        self.lecture.openExercises.connect(lambda: self.ex_panel.setVisible(True))
        self.assess = AssessmentView(theme, fs)
        self.assess.finished.connect(self._assessment_finished)
        self.assess.abandoned.connect(self._assessment_abandoned)
        self.assess.reviewRequested.connect(self._review_lesson)
        self.assess.retryRequested.connect(self._retry_assessment)
        self.assess.continueRequested.connect(self._after_assessment)
        self.dashboard = DashboardPage(cur, theme, fs)
        self.dashboard.continue_btn.clicked.connect(self.continue_learning)
        self.dashboard.export_btn.clicked.connect(self.export_report)
        self.practice = PracticePage(theme, fs)
        self.practice.openTerminal.connect(self.open_practice_terminal)
        self.practice.resetLab.connect(lambda: self.reset_lab(practice=True))
        self.exam_intro = ExamIntroPage(theme, fs)
        self.exam_intro.start.connect(self.start_exam)
        for w in (self.welcome, self.lecture, self.assess, self.dashboard, self.practice, self.exam_intro):
            self.stack.addWidget(w)

        self.terms = QTabWidget()
        self.terms.setTabsClosable(True)
        self.terms.tabCloseRequested.connect(self._close_terminal)
        self.term_status = QLabel()
        self.term_status.setProperty("role", "muted")
        self.terms.setCornerWidget(self.term_status, Qt.Corner.TopRightCorner)

        self.ex_panel = ExercisePanel(cur, theme, fs)
        self.ex_panel.bind(store, profile.id, self.engine)
        self.ex_panel.labNeeded.connect(self.with_lab)
        self.ex_panel.recorded.connect(self._refresh_nav)

        self.center = QSplitter(Qt.Orientation.Vertical)
        self.center.addWidget(self.stack)
        self.center.addWidget(self.terms)
        self.center.setStretchFactor(0, 3)
        self.center.setStretchFactor(1, 2)
        self.main_split = QSplitter(Qt.Orientation.Horizontal)
        self.main_split.addWidget(self.nav)
        self.main_split.addWidget(self.center)
        self.main_split.addWidget(self.ex_panel)
        self.main_split.setStretchFactor(1, 1)
        self.main_split.setSizes([290, 900, 380])
        self.center.setSizes([480, 320])
        self.setCentralWidget(self.main_split)
        self.statusBar().showMessage("Welcome")

        self._build_menus()
        self.resize(1500, 920)
        self._restore_layout()
        self._refresh_nav()
        self.stack.setCurrentIndex(PAGE_WELCOME if config.get("ui.show_welcome", True) else PAGE_DASH)
        if profile.current_lesson and profile.current_lesson in cur.lessons and \
                self.prog.lesson_status(profile.current_lesson) != LOCKED:
            QTimer.singleShot(0, lambda: self.open_lesson(profile.current_lesson, quiet=True))
        self.new_terminal()
        QTimer.singleShot(200, self._startup_lab)

    # ------------------------------------------------------------------ menus
    def _build_menus(self):
        mb = self.menuBar()

        def act(menu, text, slot, shortcut=None, tip=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setStatusTip(tip)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        f = mb.addMenu("&File")
        act(f, "Switch profile...", self.switch_profile)
        act(f, "Export my progress...", self.export_profile, tip="Save your records as a portable JSON file")
        act(f, "Export progress report (HTML)...", self.export_report)
        f.addSeparator()
        act(f, "Back up all student data...", self.backup_data)
        act(f, "Restore student data from backup...", self.restore_data)
        f.addSeparator()
        act(f, "Settings...", self.open_settings, "Ctrl+,")
        act(f, "Quit", self.close, "Ctrl+Q")

        v = mb.addMenu("&View")
        act(v, "Welcome page", lambda: self.stack.setCurrentIndex(PAGE_WELCOME))
        act(v, "Progress dashboard", self.show_dashboard, "Ctrl+D")
        act(v, "Current lesson", lambda: self.stack.setCurrentIndex(PAGE_LECTURE) if self.current_lesson else None,
            "Ctrl+L")
        v.addSeparator()
        act(v, "Show/hide course navigation", lambda: self.nav.setVisible(not self.nav.isVisible()), "F9")
        act(v, "Show/hide exercises panel", lambda: self.ex_panel.setVisible(not self.ex_panel.isVisible()), "F10")
        act(v, "Show/hide terminal", lambda: self.terms.setVisible(not self.terms.isVisible()), "F11")
        v.addSeparator()
        act(v, "Dark theme", lambda: self._set_ui("ui.theme", "dark"))
        act(v, "Light theme", lambda: self._set_ui("ui.theme", "light"))
        act(v, "Larger text", lambda: self._bump_font(1), "Ctrl+=")
        act(v, "Smaller text", lambda: self._bump_font(-1), "Ctrl+-")

        lab = mb.addMenu("&Lab")
        act(lab, "New terminal tab", self.new_terminal, "Ctrl+Shift+T")
        act(lab, "Reconnect terminal", self._reconnect_current)
        lab.addSeparator()
        act(lab, "Practice mode", self.show_practice, "Ctrl+P")
        act(lab, "Reset lesson laboratory...", lambda: self.reset_lab(practice=False),
            tip="Restore the laboratory to a clean state. Your progress is not affected.")
        act(lab, "Reset practice laboratory...", lambda: self.reset_lab(practice=True))
        lab.addSeparator()
        act(lab, "Laboratory status and image...", self.open_lab_dialog)

        h = mb.addMenu("&Help")
        act(h, "Glossary", lambda: self.show_glossary(""), "F1")
        act(h, "How Linux Tutor works", lambda: self.stack.setCurrentIndex(PAGE_WELCOME))
        act(h, "About", lambda: QMessageBox.about(self, f"About {APP_NAME}", about_text()))

    # ------------------------------------------------------------------ laboratory
    def _startup_lab(self):
        def check(st):
            if st.engine_available and not st.image_present:
                r = QMessageBox.question(
                    self, "Set up the laboratory",
                    "The Linux laboratory has not been installed for your account yet.\n\n"
                    "Build it now? This downloads Ubuntu packages (about 300 MB) and takes a few "
                    "minutes. You can read lessons meanwhile.\n\n"
                    "(If you have a laboratory image archive, choose No and use "
                    "Lab > Laboratory status and image > Import.)")
                if r == QMessageBox.StandardButton.Yes:
                    dlg = LabDialog(self.config, self.lab, self, auto_build=True)
                    dlg.finished.connect(lambda *_: self.with_lab(lambda: None))
                    dlg.show()
                else:
                    self._terminal_message("The laboratory is not installed. Use Lab > Laboratory status "
                                           "and image to build or import it.")
                return
            if not st.engine_available:
                self._terminal_message("Podman is not available: " + "; ".join(st.problems) +
                                       "\nPractical exercises need Podman (sudo apt install podman).")
                return
            self.with_lab(lambda: None)
        run_task(self.lab.status, on_done=check, on_error=lambda e: self._terminal_message(str(e)))

    def with_lab(self, callback, practice: bool = False):
        """Run callback once the (lesson or practice) laboratory is running."""
        lab = self.practice_lab if practice else self.lab
        if (self.practice_ready if practice else self.lab_ready):
            callback()
            return
        if practice:
            self._start_lab(lab, True, callback)
            return
        self._lab_waiters.append(callback)
        if self._lab_starting:
            return
        self._lab_starting = True
        self._start_lab(lab, False, None)

    def _start_lab(self, lab, practice: bool, callback):
        self.term_status.setText("Starting laboratory...")

        def work(progress=None):
            problems = []
            for attempt in range(4):          # a just-(re)started lab may need a moment
                lab.ensure_running(progress)
                problems = lab.health_check()
                if not problems:
                    return lab.warnings
                time.sleep(2)
            raise LabError("; ".join(problems))

        def done(warnings):
            self.term_status.setText("Laboratory ready")
            for w in warnings:
                self.statusBar().showMessage(w, 15000)
            if practice:
                self.practice_ready = True
                callback()
            else:
                self.lab_ready = True
                self._lab_starting = False
                self._connect_pending_terminals()
                waiters, self._lab_waiters = self._lab_waiters, []
                for cb in waiters:
                    cb()

        def failed(err):
            self._lab_starting = False
            self.term_status.setText("Laboratory unavailable")
            self._lab_waiters.clear()
            self._terminal_message(f"The laboratory could not be started:\n  {err}\n"
                                   "Open Lab > Laboratory status and image for help.")
            QMessageBox.warning(self, "Laboratory", f"The laboratory could not be started:\n\n{err}")
        run_task(work, on_progress=lambda m: self.term_status.setText(m), on_done=done, on_error=failed)

    def _terminal_message(self, text: str):
        w = self.terms.currentWidget()
        if isinstance(w, TerminalWidget):
            w.feed_text("\r\n" + text + "\r\n")

    def new_terminal(self, practice: bool = False):
        t = TerminalWidget(font_family=self.config.get("ui.terminal_font"),
                           font_size=int(self.config.get("ui.terminal_font_size")),
                           dark=self.config.get("ui.theme") == "dark")
        t.practice = practice
        n = sum(1 for i in range(self.terms.count()) if getattr(self.terms.widget(i), "practice", False) == practice)
        label = ("PRACTICE" if practice else "Lab terminal") + (f" {n + 1}" if n else "")
        idx = self.terms.addTab(t, label)
        self.terms.setCurrentIndex(idx)
        t.finished.connect(lambda t=t: self._reconnect(t))
        if practice:
            t.feed_text("Starting the practice laboratory...\r\n")
            self.with_lab(lambda: self._attach(t), practice=True)
        elif self.lab_ready:
            self._attach(t)
        else:
            t.feed_text("Connecting to your Linux laboratory...\r\n")
        return t

    def _attach(self, t: TerminalWidget):
        lab = self.practice_lab if getattr(t, "practice", False) else self.lab
        try:
            t.start(lab.shell_argv())
            t.setFocus()
        except Exception as exc:
            t.feed_text(f"Could not open a shell: {exc}\r\n")

    def _connect_pending_terminals(self):
        for i in range(self.terms.count()):
            t = self.terms.widget(i)
            if isinstance(t, TerminalWidget) and not getattr(t, "practice", False) and not t.running():
                self._attach(t)

    def _reconnect(self, t: TerminalWidget):
        if getattr(self, "_closing", False):
            return
        if getattr(t, "practice", False):
            self.practice_ready = False
            self.with_lab(lambda: self._attach(t), practice=True)
        else:
            self.lab_ready = False
            self.with_lab(lambda: self._attach(t))

    def _reconnect_current(self):
        t = self.terms.currentWidget()
        if isinstance(t, TerminalWidget):
            t.stop()
            self._reconnect(t)

    def _close_terminal(self, idx: int):
        if self.terms.count() <= 1:
            return
        w = self.terms.widget(idx)
        self.terms.removeTab(idx)
        if isinstance(w, TerminalWidget):
            w.stop()
        w.deleteLater()

    def try_command(self, cmd: str):
        """Type an example command into the current lesson terminal (the student presses Enter)."""
        for i in range(self.terms.count()):
            t = self.terms.widget(i)
            if isinstance(t, TerminalWidget) and not getattr(t, "practice", False):
                if not self.terms.isVisible():
                    self.terms.setVisible(True)
                self.terms.setCurrentIndex(i)
                if t.running():
                    t.send_text(cmd)
                    self.statusBar().showMessage("Command typed into the terminal - press Enter to run it.", 6000)
                else:
                    self.statusBar().showMessage("The laboratory is still starting...", 4000)
                return

    def reset_lab(self, practice: bool = False):
        name = "practice laboratory" if practice else "lesson laboratory"
        if QMessageBox.question(self, "Reset laboratory",
                                f"Reset the {name}?\n\nEverything inside it (files you created, users, "
                                "installed packages) will be erased and a clean system created.\n\n"
                                "Your lesson progress, scores and examination results are NOT affected.") \
                != QMessageBox.StandardButton.Yes:
            return
        lab = self.practice_lab if practice else self.lab
        for i in range(self.terms.count()):
            t = self.terms.widget(i)
            if isinstance(t, TerminalWidget) and getattr(t, "practice", False) == practice:
                t.stop()
                t.feed_text("\r\n[resetting laboratory...]\r\n")
        if practice:
            self.practice_ready = False
        else:
            self.lab_ready = False
            self.ex_panel.marks.clear()
            self.ex_panel._select(self.ex_panel.list.currentRow())

        def done(_):
            if practice:
                self.practice_ready = True
            else:
                self.lab_ready = True
            for i in range(self.terms.count()):
                t = self.terms.widget(i)
                if isinstance(t, TerminalWidget) and getattr(t, "practice", False) == practice:
                    t.screen.reset()
                    self._attach(t)
            self.term_status.setText("Laboratory reset")
            QMessageBox.information(self, "Reset laboratory", f"The {name} has been reset to a clean state.")
        run_task(lab.reset, on_progress=lambda m: self.term_status.setText(m), on_done=done,
                 on_error=lambda e: QMessageBox.warning(self, "Reset laboratory", f"Reset failed: {e}"))

    def open_lab_dialog(self):
        dlg = LabDialog(self.config, self.lab, self)
        dlg.exec()
        if not self.lab_ready:
            self.with_lab(lambda: None)

    # ------------------------------------------------------------------ navigation
    def _refresh_nav(self):
        self.nav.refresh(self.prog, self.profile.display_name, self.current_lesson)

    def _busy_assessment(self) -> bool:
        if self.assess.active:
            QMessageBox.information(self, "Assessment in progress",
                                    "Finish or abandon the current assessment first.")
            self.stack.setCurrentIndex(PAGE_ASSESS)
            return True
        return False

    def open_lesson(self, lesson_id: str, quiet: bool = False):
        if self._busy_assessment():
            return
        status = self.prog.lesson_status(lesson_id)
        lesson = self.cur.lessons[lesson_id]
        if status == LOCKED:
            if not quiet:
                missing = self.prog.missing_prerequisites(lesson_id)
                QMessageBox.information(self, "Lesson locked",
                                        f"'{lesson.title}' is locked.\n\nFirst pass:\n  - " + "\n  - ".join(missing))
            return
        self.current_lesson = lesson_id
        self.store.start_lesson(self.profile.id, lesson_id)
        st = self.store.lesson_state(self.profile.id, lesson_id) or {}
        self.lecture.set_lesson(lesson, st.get("section_index", 0), st.get("status") == "passed")
        self.ex_panel.set_lesson(lesson)
        self.stack.setCurrentIndex(PAGE_LECTURE)
        self._refresh_nav()

    def _section_changed(self, idx: int):
        if self.current_lesson:
            self.store.set_section(self.profile.id, self.current_lesson, idx)

    def continue_learning(self):
        lid = self.current_lesson if self.current_lesson and not self.store.is_passed(
            self.profile.id, self.current_lesson) else self.prog.next_lesson()
        if lid:
            self.open_lesson(lid)
            return
        for lv in self.cur.levels:
            if lv.exam and self.prog.exam_available(lv.exam) and not self.store.exam_passed(self.profile.id, lv.exam):
                self.open_exam(lv.exam)
                return
        if self.cur.final_exam and self.prog.exam_available(self.cur.final_exam):
            self.open_exam(self.cur.final_exam)
            return
        self.show_dashboard()

    def show_dashboard(self):
        if self.assess.active:
            return self._busy_assessment()
        self.dashboard.show_progress(self.prog, self.store.profile(self.profile.id))
        self.stack.setCurrentIndex(PAGE_DASH)

    def show_practice(self):
        if self._busy_assessment():
            return
        self.stack.setCurrentIndex(PAGE_PRACTICE)
        if not any(getattr(self.terms.widget(i), "practice", False) for i in range(self.terms.count())):
            self.open_practice_terminal()

    def open_practice_terminal(self):
        self.new_terminal(practice=True)

    def show_glossary(self, term: str = ""):
        GlossaryDialog(self.cur.glossary, term, self).exec()

    # ------------------------------------------------------------------ assessments
    def start_lesson_assessment(self):
        if not self.current_lesson or self._busy_assessment():
            return
        lesson = self.cur.lessons[self.current_lesson]

        def go():
            session = lesson_session(self.cur, lesson, self.engine, self.config)
            self.current_exam = None
            self.assess.start(session, f"Assessment - Lesson {lesson.code}: {lesson.title}", allow_hints=True)
            self.stack.setCurrentIndex(PAGE_ASSESS)
            self.nav.setEnabled(False)
            self.ex_panel.setEnabled(False)
        if any(q.is_practical for q in lesson.quiz.questions):
            self.statusBar().showMessage("Preparing the laboratory for the assessment...", 5000)
            self.with_lab(go)
        else:
            go()

    def open_exam(self, exam_id: str):
        if self._busy_assessment():
            return
        self.exam_intro.show_exam(self.cur, self.prog, exam_id, int(self.config.get("assessment.exam_passing_score")))
        self.stack.setCurrentIndex(PAGE_EXAM)

    def start_exam(self, exam_id: str):
        exam = self.cur.exams[exam_id]
        if not self.prog.exam_available(exam_id):
            return

        def go():
            session = exam_session(self.cur, exam, self.engine, self.config)
            self.current_exam = exam_id
            self.assess.start(session, exam.title, allow_hints=bool(self.config.get("assessment.allow_hints_in_exams")))
            self.stack.setCurrentIndex(PAGE_ASSESS)
            self.nav.setEnabled(False)
            self.ex_panel.setEnabled(False)
        self.with_lab(go)

    def _assessment_finished(self, result):
        self.nav.setEnabled(True)
        self.ex_panel.setEnabled(True)
        self.store.record_assessment(self.profile.id, result)
        self._refresh_nav()
        if result.passed and result.kind == "exam":
            exam = self.cur.exams[result.ref_id]
            ids = [lv.id for lv in self.cur.levels]
            if exam.level and ids.index(exam.level) + 1 < len(ids):
                nxt = self.cur.levels[ids.index(exam.level) + 1]
                QMessageBox.information(self, "Level complete",
                                        f"Congratulations! You passed the {exam.title}.\n\n"
                                        f"Level {nxt.number}: {nxt.title} is now unlocked.")
            elif exam.level:
                QMessageBox.information(self, "Level complete",
                                        f"Congratulations! You passed the {exam.title}.\n\n"
                                        "The final examination is now unlocked.")
            else:
                QMessageBox.information(self, "Course complete",
                                        "Congratulations! You have passed the final examination and "
                                        "completed the Linux Tutor course.")

    def _assessment_abandoned(self):
        self.nav.setEnabled(True)
        self.ex_panel.setEnabled(True)
        if self.current_exam:
            self.open_exam(self.current_exam)
        else:
            self.stack.setCurrentIndex(PAGE_LECTURE if self.current_lesson else PAGE_DASH)

    def _review_lesson(self):
        if self.current_lesson:
            self.stack.setCurrentIndex(PAGE_LECTURE)
            self.lecture.go(1)

    def _retry_assessment(self):
        if self.current_exam:
            self.start_exam(self.current_exam)
        else:
            self.start_lesson_assessment()

    def _after_assessment(self):
        if self.current_exam:
            exam_id, self.current_exam = self.current_exam, None
            if self.store.exam_passed(self.profile.id, exam_id):
                self.continue_learning()
            else:
                self.open_exam(exam_id)
            return
        if self.current_lesson and self.store.is_passed(self.profile.id, self.current_lesson):
            nxt = self.prog.next_lesson()
            if nxt and nxt != self.current_lesson:
                self.open_lesson(nxt)
                return
            self.continue_learning()
        else:
            self.stack.setCurrentIndex(PAGE_LECTURE)

    # ------------------------------------------------------------------ profile & data
    def switch_profile(self):
        if self._busy_assessment():
            return
        dlg = ProfileDialog(self.store, self)
        if dlg.exec() and dlg.selected and dlg.selected.id != self.profile.id:
            self._switch_to = dlg.selected
            self.close()

    def export_profile(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Export progress",
                                            str(Path.home() / f"linux-tutor-{self.profile.username}.json"),
                                            "JSON (*.json)")
        if fn:
            Path(fn).write_text(json.dumps(self.store.export_profile(self.profile.id), indent=2))
            self.statusBar().showMessage(f"Progress exported to {fn}", 8000)

    def export_report(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Export progress report",
                                            str(Path.home() / f"linux-tutor-report-{self.profile.username}.html"),
                                            "HTML (*.html)")
        if fn:
            self.dashboard.show_progress(self.prog, self.store.profile(self.profile.id))
            Path(fn).write_text(self.dashboard.browser.toHtml())
            self.statusBar().showMessage(f"Report saved to {fn}", 8000)

    def backup_data(self):
        default = paths.backup_dir() / f"tutor-{datetime.now():%Y%m%d-%H%M%S}.db"
        fn, _ = QFileDialog.getSaveFileName(self, "Back up student data", str(default), "Database (*.db)")
        if fn:
            self.store.backup(Path(fn))
            QMessageBox.information(self, "Backup", f"All student profiles and records were saved to\n{fn}")

    def restore_data(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Restore student data", str(paths.backup_dir()), "Database (*.db)")
        if not fn:
            return
        if QMessageBox.question(self, "Restore", "Replace ALL current student records with this backup? "
                                "The current data is kept as tutor.db.before-restore. "
                                "Linux Tutor will close; start it again afterwards.") != QMessageBox.StandardButton.Yes:
            return
        self._restore_from = Path(fn)
        self.close()

    # ------------------------------------------------------------------ appearance
    def open_settings(self):
        if SettingsDialog(self.config, self).exec():
            self.engine.lab.config = self.config
            self._apply_appearance()

    def _set_ui(self, key, value):
        self.config.set(key, value)
        self._apply_appearance()

    def _bump_font(self, delta: int):
        fs = max(8, min(24, int(self.config.get("ui.font_size")) + delta))
        tfs = max(8, min(28, int(self.config.get("ui.terminal_font_size")) + delta))
        self.config.set("ui.font_size", fs)
        self.config.set("ui.terminal_font_size", tfs)
        self._apply_appearance()

    def _apply_appearance(self):
        theme, fs = self.config.get("ui.theme"), int(self.config.get("ui.font_size"))
        apply_theme(QApplication.instance(), theme, fs)
        for w in (self.lecture, self.assess, self.dashboard, self.practice, self.exam_intro, self.welcome):
            w.theme, w.font_size = theme, fs
        self.nav.theme = theme
        self.assess.practical.restyle(theme, fs)
        self.lecture.restyle(theme, fs)
        self.ex_panel.restyle(theme, fs)
        self.lecture.default_pass = int(self.config.get("assessment.passing_score", 80))
        from .pages import PRACTICE_TEXT, WELCOME_TEXT
        from .render import render_markdown
        self.practice.set_html(render_markdown(PRACTICE_TEXT, theme))
        self.welcome.set_html(render_markdown(WELCOME_TEXT, theme))
        if self.stack.currentIndex() == PAGE_DASH:
            self.show_dashboard()
        for i in range(self.terms.count()):
            t = self.terms.widget(i)
            if isinstance(t, TerminalWidget):
                t.set_theme(theme == "dark")
                t.set_font(self.config.get("ui.terminal_font"), int(self.config.get("ui.terminal_font_size")))
        self._refresh_nav()

    def _restore_layout(self):
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        for key, split in (("main_split", self.main_split), ("center_split", self.center)):
            st = self.settings.value(key)
            if st:
                split.restoreState(st)

    def closeEvent(self, ev):
        if self.assess.active and QMessageBox.question(
                self, "Quit", "An assessment is in progress and will not be recorded. Quit anyway?") != QMessageBox.StandardButton.Yes:
            ev.ignore()
            return
        self._closing = True
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("main_split", self.main_split.saveState())
        self.settings.setValue("center_split", self.center.saveState())
        for i in range(self.terms.count()):
            t = self.terms.widget(i)
            if isinstance(t, TerminalWidget):
                t.stop()
        self.statusBar().showMessage("Stopping the laboratory...")
        QApplication.processEvents()
        for lab in (self.lab, self.practice_lab):
            try:
                lab.stop()
            except Exception:
                pass
        super().closeEvent(ev)

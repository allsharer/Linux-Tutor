"""Right-hand panel: the lesson's practical exercises with hints and feedback."""
from __future__ import annotations

from .qt import Qt, Signal
from .qt import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..assessment.engine import AssessmentEngine, Evaluation
from ..curriculum.loader import Curriculum
from ..curriculum.models import Lesson
from ..progress.store import ProgressStore
from .practical import PracticalTask
from .workers import run_task


class ExercisePanel(QWidget):
    labNeeded = Signal(object)        # callback to run once the lab is ready
    recorded = Signal()

    def __init__(self, cur: Curriculum, theme: str, font_size: int, parent=None):
        super().__init__(parent)
        self.cur = cur
        self.lesson: Lesson | None = None
        self.engine: AssessmentEngine | None = None
        self.store: ProgressStore | None = None
        self.pid: int | None = None
        self.marks: dict[str, int] = {}
        self.hints: dict[str, int] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        head = QLabel("Practical exercises")
        head.setProperty("role", "banner")
        lay.addWidget(head)
        self.info = QLabel("Open a lesson to see its exercises.")
        self.info.setWordWrap(True)
        self.info.setProperty("role", "muted")
        lay.addWidget(self.info)
        self.list = QListWidget()
        self.list.setMaximumHeight(130)
        self.list.currentRowChanged.connect(self._select)
        lay.addWidget(self.list)
        self.task = PracticalTask(theme, font_size)
        self.task.prepareRequested.connect(self._prepare)
        self.task.checkRequested.connect(self._check)
        self.task.hintRequested.connect(self._hint)
        lay.addWidget(self.task, 1)

    def bind(self, store: ProgressStore, pid: int, engine: AssessmentEngine) -> None:
        self.store, self.pid, self.engine = store, pid, engine

    def set_lesson(self, lesson: Lesson | None) -> None:
        self.lesson = lesson
        self.marks.clear()
        self.list.clear()
        if not lesson:
            self.task.set_exercise(None)
            return
        summary = self.store.exercise_summary(self.pid, lesson.id) if self.store else {}
        self.hints = {k: int(v["hints"] or 0) for k, v in summary.items()}
        for ex in lesson.exercises:
            s = summary.get(ex.id)
            mark = "✔ " if s and s["successes"] else ("▶ " if s else "○ ")
            item = QListWidgetItem(mark + ex.title)
            item.setData(Qt.ItemDataRole.UserRole, ex.id)
            self.list.addItem(item)
        self.info.setText(f"{len(lesson.exercises)} exercise(s). Exercises are for practice: try as often as "
                          "you like. Hints are recorded but never counted against you."
                          if lesson.exercises else "This lesson has no separate exercises - "
                                                   "go straight to the assessment when ready.")
        if lesson.exercises:
            self.list.setCurrentRow(0)
        else:
            self.task.set_exercise(None)

    def restyle(self, theme, font_size):
        self.task.restyle(theme, font_size)

    def current(self):
        row = self.list.currentRow()
        if self.lesson and 0 <= row < len(self.lesson.exercises):
            return self.lesson.exercises[row]
        return None

    def _select(self, row: int):
        ex = self.current()
        self.task.set_exercise(ex, self.hints.get(ex.id, 0) if ex else 0)
        if ex and ex.id in self.marks:
            self.task.set_prepared()

    def _prepare(self):
        ex = self.current()
        if not ex:
            return

        def go():
            self.task.set_busy(True, "Preparing the laboratory for this exercise...")
            run_task(self.engine.prepare, ex, on_done=lambda m: self._prepared(ex, m),
                     on_error=lambda e: (self.task.set_busy(False),
                                         self.task.status.setText(f"Could not prepare the exercise: {e}")))
        self.labNeeded.emit(go)

    def _prepared(self, ex, mark):
        self.marks[ex.id] = mark
        self.task.set_busy(False)
        if self.current() is ex:
            self.task.set_prepared()

    def _hint(self):
        ex = self.current()
        if not ex:
            return
        self.task.show_hint()
        self.hints[ex.id] = self.task.hints_shown

    def _check(self):
        ex = self.current()
        if not ex or ex.id not in self.marks:
            return
        answer = self.task.answer_text()
        self.task.set_busy(True, "Inspecting the laboratory...")
        run_task(self.engine.evaluate, ex, answer, self.marks[ex.id],
                 on_done=lambda ev: self._evaluated(ex, ev),
                 on_error=lambda e: (self.task.set_busy(False), self.task.status.setText(f"Check failed: {e}")))

    def _evaluated(self, ex, ev: Evaluation):
        self.task.set_busy(False)
        titles = [f"{self.cur.lessons[r].code} {self.cur.lessons[r].title}" if r in self.cur.lessons else r
                  for r in ev.review]
        if self.current() is ex:
            self.task.show_evaluation(ev, titles)
        if self.store and self.lesson:
            self.store.record_exercise(self.pid, self.lesson.id, ex.id, ev.outcome.value,
                                       self.hints.get(ex.id, 0), "\n".join(ev.feedback)[:2000])
            row = self.lesson.exercises.index(ex)
            item = self.list.item(row)
            if item and ev.outcome.is_success:
                item.setText("✔ " + ex.title)
            elif item and item.text().startswith("○"):
                item.setText("▶ " + ex.title)
            self.recorded.emit()

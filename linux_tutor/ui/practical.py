"""Widget for one practical task: instructions, optional answer box, hints, check and feedback.

Used both for lesson exercises (right-hand panel) and for practical questions inside
assessments and examinations.
"""
from __future__ import annotations

import html

from .qt import Qt, Signal
from .qt import (QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..assessment.engine import Evaluation, Outcome
from ..curriculum.models import Exercise
from .render import page, render_markdown
from .theme import colors, content_css

HINT_LABELS = ["Hint 1 - the concept", "Hint 2 - the Linux feature to use",
               "Hint 3 - an example command", "Hint 4 - complete explanation"]

OUTCOME_STYLE = {
    Outcome.CORRECT: "good", Outcome.CORRECT_ALTERNATIVE: "good",
    Outcome.CORRECT_SIDE_EFFECTS: "warn", Outcome.PARTIAL: "warn",
    Outcome.INCORRECT: "bad", Outcome.UNVERIFIABLE: "muted",
}


class PracticalTask(QWidget):
    checkRequested = Signal()       # owner runs the evaluation in the background
    prepareRequested = Signal()
    hintRequested = Signal()

    def __init__(self, theme: str, font_size: int, check_label: str = "Check my work",
                 allow_hints: bool = True, parent=None):
        super().__init__(parent)
        self.theme, self.font_size = theme, font_size
        self.exercise: Exercise | None = None
        self.hints_shown = 0
        self.allow_hints = allow_hints
        self.prepared = False
        self._last_eval = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel()
        self.title.setProperty("role", "subtitle")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        lay.addWidget(self.body, 3)

        self.answer_label = QLabel()
        self.answer_label.setWordWrap(True)
        self.answer = QLineEdit()
        self.answer.setPlaceholderText("Type your answer here")
        self.answer.returnPressed.connect(self.checkRequested)
        lay.addWidget(self.answer_label)
        lay.addWidget(self.answer)

        row = QHBoxLayout()
        self.prepare_btn = QPushButton("Set up task")
        self.prepare_btn.setToolTip("Prepare the laboratory for this task (creates any files it needs).")
        self.prepare_btn.clicked.connect(self.prepareRequested)
        self.hint_btn = QPushButton("Hint")
        self.hint_btn.clicked.connect(self.hintRequested)
        self.check_btn = QPushButton(check_label)
        self.check_btn.setProperty("primary", True)
        self.check_btn.clicked.connect(self.checkRequested)
        row.addWidget(self.prepare_btn)
        row.addWidget(self.hint_btn)
        row.addStretch()
        row.addWidget(self.check_btn)
        lay.addLayout(row)

        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.feedback = QTextBrowser()
        lay.addWidget(self.feedback, 2)
        self.set_exercise(None)

    # ------------------------------------------------------------------
    def set_exercise(self, ex: Exercise | None, hints_shown: int = 0) -> None:
        self.exercise = ex
        self.hints_shown = hints_shown
        self.prepared = False
        has = ex is not None
        for w in (self.prepare_btn, self.check_btn, self.hint_btn):
            w.setEnabled(has)
        self.answer.clear()
        self._last_eval = None
        self.answer.setVisible(bool(has and ex.answer_prompt))
        self.answer_label.setVisible(bool(has and ex.answer_prompt))
        self.feedback.clear()
        self.status.clear()
        if not has:
            self.title.setText("No task selected")
            self.body.setHtml("")
            return
        self.title.setText(ex.title)
        self.answer_label.setText(ex.answer_prompt)
        self._render_body()
        self._update_hint_button()
        self.check_btn.setEnabled(False)
        self.status.setText("Press <b>Set up task</b> to prepare the laboratory, then work in the terminal.")

    def _render_body(self):
        ex = self.exercise
        c = colors(self.theme)
        text = render_markdown(ex.instructions, self.theme)
        if self.hints_shown:
            text += "<hr>"
            for i in range(self.hints_shown):
                text += (f'<p><span style="color:{c["accent2"]}; font-weight:bold">{HINT_LABELS[min(i, 3)]}</span>'
                         f'<br>{html.escape(ex.hints[i])}</p>')
            if self.hints_shown >= len(ex.hints) and ex.explanation:
                text += render_markdown(ex.explanation, self.theme)
        self.body.setHtml(page(text, content_css(self.theme, self.font_size)))

    def _update_hint_button(self):
        ex = self.exercise
        n = len(ex.hints) if ex else 0
        self.hint_btn.setVisible(self.allow_hints)
        self.hint_btn.setEnabled(bool(ex) and self.hints_shown < n)
        self.hint_btn.setText(f"Hint ({self.hints_shown}/{n})")

    def show_hint(self) -> None:
        if self.exercise and self.hints_shown < len(self.exercise.hints):
            self.hints_shown += 1
            self._render_body()
            self._update_hint_button()
            sb = self.body.verticalScrollBar()
            sb.setValue(sb.maximum())

    def set_prepared(self) -> None:
        self.prepared = True
        self.check_btn.setEnabled(True)
        self.prepare_btn.setText("Set up again")
        self.status.setText("The task is ready. Work in the terminal below, then press "
                            f"<b>{self.check_btn.text()}</b>.")

    def set_busy(self, busy: bool, message: str = "") -> None:
        for w in (self.prepare_btn, self.check_btn):
            w.setEnabled(not busy and (w is self.prepare_btn or self.prepared))
        if message:
            self.status.setText(message)

    def restyle(self, theme: str, font_size: int) -> None:
        self.theme, self.font_size = theme, font_size
        if self.exercise:
            self._render_body()
        if self._last_eval:
            self.show_evaluation(*self._last_eval)

    def show_evaluation(self, ev: Evaluation, review_titles: list[str] | None = None) -> None:
        self._last_eval = (ev, review_titles)
        c = colors(self.theme)
        cls = OUTCOME_STYLE.get(ev.outcome, "muted")
        color = {"good": c["good"], "warn": c["warn"], "bad": c["bad"], "muted": c["muted"]}[cls]
        self.status.setText(f'<span style="color:{color}; font-weight:bold; font-size:{self.font_size + 2}pt">'
                            f'{html.escape(ev.outcome.label)}</span>')
        parts = []
        for line in ev.feedback:
            parts.append(f"<p>{html.escape(line)}</p>")
        if ev.method_note:
            parts.append(f'<p style="color:{c["accent"]}">{html.escape(ev.method_note)}</p>')
        if ev.checks:
            items = "".join(
                f'<li><span style="color:{c["good"] if r.passed else c["bad"]}">'
                f'{"&#10004;" if r.passed else "&#10008;"}</span> {html.escape(r.description)}</li>'
                for r in ev.checks)
            parts.append(f'<p style="color:{c["muted"]}">What was checked:</p><ul>{items}</ul>')
        if review_titles:
            parts.append("<p><b>Suggested revision:</b> " + html.escape(", ".join(review_titles)) + "</p>")
        if not ev.outcome.is_success and ev.outcome != Outcome.UNVERIFIABLE:
            parts.append(f'<p style="color:{c["muted"]}">You can try again as many times as you like. '
                         "Use a hint if you are stuck - hints are recorded but never count against "
                         "an exercise.</p>")
        self.feedback.setHtml(page("".join(parts), content_css(self.theme, self.font_size)))

    def answer_text(self) -> str | None:
        return self.answer.text() if self.answer.isVisible() else None

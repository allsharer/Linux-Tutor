"""Assessment and examination screen: one question at a time, then a results report."""
from __future__ import annotations

import html

from .qt import Qt, Signal
from .qt import (QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QProgressBar, QPushButton, QRadioButton, QStackedWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..assessment.engine import AssessmentEngine
from ..curriculum.models import Question
from ..exams.engine import AssessmentSession, SessionResult
from .practical import PracticalTask
from .render import md, page, render_markdown
from .theme import colors, content_css
from .workers import run_task

TYPE_LABEL = {"mcq": "Multiple choice", "multi": "Choose all that apply", "truefalse": "True or false",
              "short": "Short answer", "practical": "Practical task (in the terminal)",
              "interpret": "Interpret the output", "troubleshoot": "Troubleshooting scenario"}


class AssessmentView(QWidget):
    finished = Signal(object)        # SessionResult
    abandoned = Signal()
    reviewRequested = Signal()
    retryRequested = Signal()
    continueRequested = Signal()

    def __init__(self, theme: str, font_size: int, parent=None):
        super().__init__(parent)
        self.theme, self.font_size = theme, font_size
        self.session: AssessmentSession | None = None
        self.idx = 0
        self.answers: dict[str, object] = {}
        self.title = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.header = QLabel()
        self.header.setProperty("role", "banner")
        lay.addWidget(self.header)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # --- question page
        qpage = QWidget()
        ql = QVBoxLayout(qpage)
        ql.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.qlabel = QLabel()
        self.qlabel.setProperty("role", "muted")
        self.qprogress = QProgressBar()
        self.qprogress.setMaximumWidth(240)
        self.qprogress.setMaximumHeight(10)
        self.qprogress.setTextVisible(False)
        top.addWidget(self.qlabel)
        top.addStretch()
        top.addWidget(self.qprogress)
        ql.addLayout(top)
        self.prompt = QTextBrowser()
        self.prompt.setMaximumHeight(16777215)
        ql.addWidget(self.prompt, 2)
        self.answer_area = QWidget()
        self.answer_layout = QVBoxLayout(self.answer_area)
        self.answer_layout.setContentsMargins(4, 4, 4, 4)
        ql.addWidget(self.answer_area, 1)
        self.practical = PracticalTask(theme, font_size, check_label="Submit task")
        self.practical.prepareRequested.connect(self._prepare_practical)
        self.practical.checkRequested.connect(self._submit_practical)
        self.practical.hintRequested.connect(self._hint)
        ql.addWidget(self.practical, 3)
        nav = QHBoxLayout()
        self.prev_btn = QPushButton("< Previous")
        self.prev_btn.clicked.connect(lambda: self._goto(self.idx - 1))
        self.quit_btn = QPushButton("Abandon")
        self.quit_btn.clicked.connect(self._abandon)
        self.next_btn = QPushButton("Next >")
        self.next_btn.clicked.connect(lambda: self._goto(self.idx + 1))
        self.finish_btn = QPushButton("Finish and mark")
        self.finish_btn.setProperty("primary", True)
        self.finish_btn.clicked.connect(self._finish)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.quit_btn)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        nav.addWidget(self.finish_btn)
        ql.addLayout(nav)
        self.stack.addWidget(qpage)

        # --- results page
        rpage = QWidget()
        rl = QVBoxLayout(rpage)
        rl.setContentsMargins(0, 0, 0, 0)
        self.results = QTextBrowser()
        self.results.setOpenExternalLinks(False)
        rl.addWidget(self.results, 1)
        rb = QHBoxLayout()
        self.review_btn = QPushButton("Review the lesson")
        self.review_btn.clicked.connect(self.reviewRequested)
        self.retry_btn = QPushButton("Try again")
        self.retry_btn.clicked.connect(self.retryRequested)
        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setProperty("primary", True)
        self.continue_btn.clicked.connect(self.continueRequested)
        rb.addWidget(self.review_btn)
        rb.addStretch()
        rb.addWidget(self.retry_btn)
        rb.addWidget(self.continue_btn)
        rl.addLayout(rb)
        self.stack.addWidget(rpage)

    # ------------------------------------------------------------------
    def start(self, session: AssessmentSession, title: str, allow_hints: bool = True) -> None:
        self.session = session
        self.title = title
        self.answers = {}
        self.idx = 0
        self.practical.allow_hints = allow_hints
        self.header.setText(title)
        self.stack.setCurrentIndex(0)
        self._goto(0)

    @property
    def active(self) -> bool:
        return self.session is not None and self.stack.currentIndex() == 0

    def _clear_answer_area(self):
        while self.answer_layout.count():
            item = self.answer_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _save_current(self):
        if not self.session or not self.session.questions:
            return
        q = self.session.questions[self.idx]
        if q.is_practical:
            return
        if q.type in ("mcq", "interpret", "troubleshoot", "truefalse"):
            b = self._group.checkedId() if hasattr(self, "_group") else -1
            if b >= 0:
                self.answers[q.id] = (b == 0) if q.type == "truefalse" else b
        elif q.type == "multi":
            self.answers[q.id] = [i for i, cb in enumerate(self._checks) if cb.isChecked()]
        elif q.type == "short":
            self.answers[q.id] = self._line.text()

    def _goto(self, idx: int) -> None:
        s = self.session
        if not s or not 0 <= idx < len(s.questions):
            return
        self._save_current()
        self.idx = idx
        q = s.questions[idx]
        n = len(s.questions)
        self.qlabel.setText(f"Question {idx + 1} of {n}  -  {TYPE_LABEL.get(q.type, q.type)}"
                            + (f"  (weight x{s.weight(q):g})" if s.weight(q) != 1 else ""))
        self.qprogress.setMaximum(n)
        self.qprogress.setValue(idx + 1)
        self._clear_answer_area()
        css = content_css(self.theme, self.font_size)
        if q.is_practical:
            self.prompt.setVisible(False)
            self.answer_area.setVisible(False)
            self.practical.setVisible(True)
            self.practical.set_exercise(q.exercise, s.hints.get(q.id, 0))
            if q.id in s.marks:
                self.practical.set_prepared()
            if q.id in s.results and s.results[q.id].evaluation:
                self.practical.status.setText("Submitted. You may change your work and submit again "
                                              "before finishing.")
        else:
            self.practical.setVisible(False)
            self.prompt.setVisible(True)
            self.answer_area.setVisible(True)
            body = render_markdown(q.prompt, self.theme)
            if q.output:
                body += f"<pre>{html.escape(q.output)}</pre>"
            self.prompt.setHtml(page(body, css))
            given = self.answers.get(q.id)
            if q.type in ("mcq", "interpret", "troubleshoot", "truefalse"):
                self._group = QButtonGroup(self)
                opts = ["True", "False"] if q.type == "truefalse" else q.options
                for i, o in enumerate(opts):
                    rb = QRadioButton(o)
                    self._group.addButton(rb, i)
                    self.answer_layout.addWidget(rb)
                    if q.type == "truefalse" and given is not None and (i == 0) == bool(given):
                        rb.setChecked(True)
                    elif q.type != "truefalse" and given == i:
                        rb.setChecked(True)
            elif q.type == "multi":
                self._checks = []
                for i, o in enumerate(q.options):
                    cb = QCheckBox(o)
                    cb.setChecked(i in (given or []))
                    self._checks.append(cb)
                    self.answer_layout.addWidget(cb)
            elif q.type == "short":
                self._line = QLineEdit(given or "")
                self._line.setPlaceholderText("Type your answer")
                self._line.returnPressed.connect(lambda: self._goto(self.idx + 1))
                self.answer_layout.addWidget(self._line)
            self.answer_layout.addStretch()
        self.prev_btn.setEnabled(idx > 0)
        self.next_btn.setEnabled(idx < n - 1)

    # ------------------------------------------------------------------ practical
    def _prepare_practical(self):
        q = self.session.questions[self.idx]
        self.practical.set_busy(True, "Preparing the laboratory...")
        run_task(self.session.prepare_practical, q,
                 on_done=lambda _: (self.practical.set_busy(False), self.practical.set_prepared()),
                 on_error=lambda e: (self.practical.set_busy(False),
                                     self.practical.status.setText(f"Could not prepare the task: {e}")))

    def _submit_practical(self):
        q = self.session.questions[self.idx]
        if not self.practical.prepared:
            return
        answer = self.practical.answer_text()
        self.practical.set_busy(True, "Checking the laboratory...")

        def done(res):
            self.practical.set_busy(False)
            self.practical.status.setText("Your work has been submitted. It will be marked when you "
                                          "finish; you may still improve it and submit again.")
        run_task(self.session.answer, q, answer, on_done=done,
                 on_error=lambda e: (self.practical.set_busy(False),
                                     self.practical.status.setText(f"Submission failed: {e}")))

    def _hint(self):
        q = self.session.questions[self.idx]
        if self.session.use_hint(q) is not None:
            self.practical.show_hint()

    # ------------------------------------------------------------------ finishing
    def _abandon(self):
        if QMessageBox.question(self, "Abandon assessment",
                                "Leave this assessment? Your answers will not be marked or recorded.") \
                == QMessageBox.StandardButton.Yes:
            self.session = None
            self.abandoned.emit()

    def _finish(self):
        self._save_current()
        s = self.session
        unanswered = [q for q in s.questions
                      if (q.is_practical and q.id not in s.results) or (not q.is_practical and q.id not in self.answers)]
        if unanswered:
            r = QMessageBox.question(self, "Finish assessment",
                                     f"{len(unanswered)} question(s) have not been answered or submitted "
                                     "and will score zero. Finish anyway?")
            if r != QMessageBox.StandardButton.Yes:
                return
        for q in s.questions:
            if not q.is_practical and q.id in self.answers:
                s.answer(q, self.answers[q.id])
        result = s.finish()
        self.show_results(result)
        self.finished.emit(result)

    def show_results(self, r: SessionResult) -> None:
        c = colors(self.theme)
        verdict = (f'<p style="font-size:{self.font_size + 6}pt; color:{c["good"]}"><b>PASSED</b></p>'
                   if r.passed else
                   f'<p style="font-size:{self.font_size + 6}pt; color:{c["bad"]}"><b>NOT YET PASSED</b></p>')
        body = f"<h1>{html.escape(self.title)} - results</h1>{verdict}"
        body += (f"<p>Your score: <b>{r.score_percent:.0f}%</b> &nbsp; (pass mark {r.passing_score}%)."
                 f" Hints used: {r.hints_used}.</p>")
        if r.passed:
            body += ("<p>Well done. You have demonstrated the competency this assessment requires"
                     + (" and the next part of the course is now unlocked." if r.kind else ".") + "</p>")
        else:
            body += ("<p>Don't be discouraged - this is how learning works. Review the areas listed "
                     "below, practise in the terminal, and try again when you are ready.</p>")
        if r.revision:
            body += "<h2>Areas to revise</h2><ul>" + "".join(f"<li>{html.escape(t)}</li>" for t in r.revision) + "</ul>"
        body += "<h2>Question by question</h2><table width='100%' cellspacing='0' cellpadding='6'>"
        for i, qr in enumerate(r.results, 1):
            q: Question = qr.question
            mark = (f'<span style="color:{c["good"]}">&#10004; correct</span>' if qr.correct else
                    f'<span style="color:{c["warn"]}">&#9680; partly correct</span>' if qr.score > 0 else
                    f'<span style="color:{c["bad"]}">&#10008; incorrect</span>')
            prompt = (q.exercise.title if q.is_practical else q.prompt.strip().splitlines()[0])
            body += (f'<tr bgcolor="{c["alt"] if i % 2 else c["base"]}"><td valign="top"><b>{i}.</b></td>'
                     f'<td valign="top">{html.escape(prompt)}'
                     + (f'<br><span style="color:{c["muted"]}">{html.escape(qr.feedback)}</span>'
                        if (not qr.correct and qr.feedback) else "")
                     + (f'<br><span style="color:{c["muted"]}">{html.escape(q.explanation)}</span>'
                        if (qr.correct and q.explanation and not q.is_practical) else "")
                     + f'</td><td valign="top" align="right">{mark}</td></tr>')
        body += "</table>"
        self.results.setHtml(page(body, content_css(self.theme, self.font_size)))
        self.retry_btn.setVisible(True)
        self.review_btn.setVisible(r.kind == "lesson")
        self.continue_btn.setText("Continue" if r.passed else "Back to the lesson" if r.kind == "lesson" else "Close")
        self.stack.setCurrentIndex(1)
        self.session = None

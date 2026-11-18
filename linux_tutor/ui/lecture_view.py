"""The lecture screen: one manageable section at a time, with navigation."""
from __future__ import annotations

import html
from urllib.parse import unquote

from .qt import QUrl, Signal
from .qt import (QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..curriculum.loader import Curriculum
from ..curriculum.models import Lesson
from .render import examples_html, md, page, render_markdown
from .theme import colors, content_css


class LectureView(QWidget):
    tryCommand = Signal(str)
    sectionChanged = Signal(int)
    startAssessment = Signal()
    showGlossary = Signal(str)
    openExercises = Signal()

    def __init__(self, cur: Curriculum, theme: str, font_size: int, parent=None):
        super().__init__(parent)
        self.cur = cur
        self.theme, self.font_size = theme, font_size
        self.lesson: Lesson | None = None
        self.index = 0
        self.show_more = False
        self.passed = False
        self.default_pass = 80

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.header = QLabel()
        self.header.setProperty("role", "banner")
        lay.addWidget(self.header)
        top = QHBoxLayout()
        self.section_label = QLabel()
        self.section_label.setProperty("role", "muted")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(10)
        top.addWidget(self.section_label)
        top.addStretch()
        top.addWidget(self.progress)
        lay.addLayout(top)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._link)
        lay.addWidget(self.browser, 1)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("< Previous")
        self.prev_btn.setShortcut("Alt+Left")
        self.prev_btn.clicked.connect(lambda: self.go(self.index - 1))
        self.more_btn = QPushButton("Explain further")
        self.more_btn.setToolTip("Show an additional, more detailed explanation of this section")
        self.more_btn.clicked.connect(self._toggle_more)
        self.gloss_btn = QPushButton("Glossary")
        self.gloss_btn.clicked.connect(lambda: self.showGlossary.emit(""))
        self.ex_btn = QPushButton("Exercises")
        self.ex_btn.clicked.connect(self.openExercises)
        self.next_btn = QPushButton("Next >")
        self.next_btn.setShortcut("Alt+Right")
        self.next_btn.setProperty("primary", True)
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.more_btn)
        nav.addWidget(self.gloss_btn)
        nav.addStretch()
        nav.addWidget(self.ex_btn)
        nav.addWidget(self.next_btn)
        lay.addLayout(nav)

    # pages: 0 = introduction/objectives, 1..n = sections, n+1 = summary & assessment
    @property
    def page_count(self) -> int:
        return len(self.lesson.sections) + 2 if self.lesson else 0

    def set_lesson(self, lesson: Lesson, index: int = 0, passed: bool = False) -> None:
        self.lesson = lesson
        self.passed = passed
        level = self.cur.level(lesson.level)
        self.header.setText(f"Lesson {lesson.code}  -  {lesson.title}      "
                            f"[{level.title} / {self.cur.module_title(lesson.level, lesson.module)}]")
        self.go(max(0, min(index, self.page_count - 1)))

    def restyle(self, theme: str, font_size: int) -> None:
        self.theme, self.font_size = theme, font_size
        if self.lesson:
            self.go(self.index)

    def _next(self):
        if self.index < self.page_count - 1:
            self.go(self.index + 1)
        else:
            self.startAssessment.emit()

    def _toggle_more(self):
        self.show_more = not self.show_more
        self.go(self.index, keep_more=True)

    def go(self, index: int, keep_more: bool = False) -> None:
        if not self.lesson or not 0 <= index < self.page_count:
            return
        if not keep_more:
            self.show_more = False
        self.index = index
        L = self.lesson
        c = colors(self.theme)
        n = len(L.sections)
        if index == 0:
            title = "Introduction"
            body = f"<h1>{html.escape(L.title)}</h1>"
            body += f'<p class="muted">Lesson {L.code} &middot; about {L.duration} minutes &middot; ' \
                    f'{n} sections, {len(L.exercises)} practical exercises, end-of-lesson assessment</p>'
            body += "<h2>In this lesson you will learn to</h2><ul>" + \
                    "".join(f"<li>{html.escape(o)}</li>" for o in L.objectives) + "</ul>"
            pre = [p for p in self.cur.prerequisites(L.id) if p in self.cur.lessons]
            if pre:
                body += "<p class='muted'>Builds on: " + ", ".join(
                    html.escape(f"{self.cur.lessons[p].code} {self.cur.lessons[p].title}") for p in pre) + "</p>"
            body += (f'<p>Read each section, try the examples in the <b>terminal</b> below, then practise '
                     f'with the <b>exercises</b> on the right. When you are ready, take the '
                     f'<b>end-of-lesson assessment</b>. You need {L.quiz.passing_score or self.default_pass}% '
                     f'to unlock the next lesson.</p>')
            if self.passed:
                body += f'<p class="good">You have already passed this lesson - you are reviewing it.</p>'
            more = ""
        elif index <= n:
            s = L.sections[index - 1]
            title = s.title
            body = f"<h2>{index}. {html.escape(s.title)}</h2>" + render_markdown(s.content, self.theme)
            body += examples_html(s.examples, self.theme)
            more = s.more
            if self.show_more:
                extra = s.more or self._auto_more(s.content)
                body += (f'<table width="100%" cellpadding="8" bgcolor="{c["alt"]}" style="margin-top:10px"><tr><td>'
                         f'<span style="color:{c["accent2"]}; font-weight:bold">Further explanation</span>'
                         f'{render_markdown(extra, self.theme)}</td></tr></table>')
        else:
            title = "Summary"
            body = "<h2>Summary</h2>"
            body += render_markdown(L.summary, self.theme) if L.summary else \
                "<ul>" + "".join(f"<li>{html.escape(o)}</li>" for o in L.objectives) + "</ul>"
            body += ("<h2>What next?</h2><p>Make sure you have tried the <b>exercises</b> on the right. "
                     "Then press <b>Start assessment</b>. The assessment mixes theory questions with "
                     "practical tasks in the laboratory; practical tasks carry extra weight.</p>")
            if L.references:
                body += "<h3>Further reading</h3><ul>" + "".join(
                    f'<li><a href="{html.escape(r.get("url", ""))}">{html.escape(r.get("title", r.get("url", "")))}</a></li>'
                    for r in L.references) + "</ul>"
            more = ""
        self.browser.setHtml(page(body, content_css(self.theme, self.font_size)))
        self.section_label.setText(f"Page {index + 1} of {self.page_count}: {title}")
        self.progress.setMaximum(self.page_count - 1)
        self.progress.setValue(index)
        self.prev_btn.setEnabled(index > 0)
        self.more_btn.setVisible(0 < index <= n)
        self.more_btn.setText("Hide further explanation" if self.show_more else "Explain further")
        self.next_btn.setText("Start assessment" if index == self.page_count - 1 else "Next >")
        self.sectionChanged.emit(index)

    def _auto_more(self, content: str) -> str:
        """Fallback 'explain further': glossary definitions of terms used in the section."""
        terms = [t for t in self.cur.glossary if t.lower() in content.lower()]
        if not terms:
            return ("Try the examples in the terminal and watch what happens - experimenting is the "
                    "best explanation. You can also run `man <command>` for the full manual.")
        return "Key terms used in this section:\n\n" + "\n".join(
            f"* **{t}** - {self.cur.glossary[t]}" for t in sorted(terms)[:12])

    def _link(self, url: QUrl):
        s = url.toString()
        if s.startswith("tutor-try:"):
            self.tryCommand.emit(unquote(s[len("tutor-try:"):]))
        elif s.startswith("glossary:"):
            self.showGlossary.emit(unquote(s[len("glossary:"):]))
        elif url.scheme() in ("http", "https"):
            from .qt import QDesktopServices
            QDesktopServices.openUrl(url)

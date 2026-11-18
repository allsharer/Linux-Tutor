"""Left panel: levels, modules, lessons and examinations with their status."""
from __future__ import annotations

from .qt import Qt, Signal
from .qt import QBrush, QColor
from .qt import (QLabel, QProgressBar, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..curriculum.loader import Curriculum
from ..progress.progression import AVAILABLE, IN_PROGRESS, LOCKED, PASSED, Progression
from .theme import colors

ICON = {PASSED: "✔", IN_PROGRESS: "▶", AVAILABLE: "○", LOCKED: "\U0001F512"}
STATUS_TEXT = {PASSED: "passed", IN_PROGRESS: "in progress", AVAILABLE: "available", LOCKED: "locked"}


class NavPanel(QWidget):
    lessonSelected = Signal(str)
    examSelected = Signal(str)
    dashboardSelected = Signal()
    practiceSelected = Signal()

    def __init__(self, cur: Curriculum, theme: str, parent=None):
        super().__init__(parent)
        self.cur = cur
        self.theme = theme
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.profile_label = QLabel()
        self.profile_label.setProperty("role", "subtitle")
        self.level_label = QLabel()
        self.level_label.setProperty("role", "muted")
        self.bar = QProgressBar()
        self.bar.setFormat("%p% of the course")
        lay.addWidget(self.profile_label)
        lay.addWidget(self.level_label)
        lay.addWidget(self.bar)
        dash = QPushButton("Progress dashboard")
        dash.clicked.connect(self.dashboardSelected)
        practice = QPushButton("Practice mode (ungraded)")
        practice.setToolTip("Explore a separate laboratory freely - nothing is marked")
        practice.clicked.connect(self.practiceSelected)
        lay.addWidget(dash)
        lay.addWidget(practice)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.itemActivated.connect(self._activated)
        self.tree.itemClicked.connect(self._activated)
        lay.addWidget(self.tree, 1)
        legend = QLabel(f"{ICON[PASSED]} passed   {ICON[IN_PROGRESS]} in progress   "
                        f"{ICON[AVAILABLE]} available   {ICON[LOCKED]} locked")
        legend.setProperty("role", "muted")
        legend.setWordWrap(True)
        lay.addWidget(legend)
        self.items: dict[str, QTreeWidgetItem] = {}

    def refresh(self, prog: Progression, profile_name: str, current: str | None = None) -> None:
        c = colors(self.theme)
        ov = prog.overview()
        self.profile_label.setText(profile_name)
        self.level_label.setText(f"Level: {self.cur.level(ov.current_level).title}  -  "
                                 f"{ov.lessons_passed}/{ov.lessons_total} lessons passed")
        self.bar.setValue(round(ov.percent_complete))
        expanded = {k for k, it in self.items.items() if it.isExpanded()}
        first = not self.items
        self.tree.clear()
        self.items = {}
        states = prog.store.all_lesson_states(prog.pid)
        for lv in self.cur.levels:
            unlocked = prog.level_unlocked(lv.id)
            done, total = ov.level_progress[lv.id]
            lv_item = QTreeWidgetItem([f"{'' if unlocked else ICON[LOCKED] + ' '}Level {lv.number}: "
                                       f"{lv.title}  ({done}/{total})"])
            f = lv_item.font(0)
            f.setBold(True)
            lv_item.setFont(0, f)
            lv_item.setToolTip(0, lv.description)
            lv_item.setData(0, Qt.ItemDataRole.UserRole, ("level", lv.id))
            self.tree.addTopLevelItem(lv_item)
            self.items[f"level:{lv.id}"] = lv_item
            for m in lv.modules:
                m_item = QTreeWidgetItem([m.title])
                m_item.setForeground(0, QBrush(QColor(c["accent2"])))
                m_item.setData(0, Qt.ItemDataRole.UserRole, ("module", m.id))
                lv_item.addChild(m_item)
                self.items[f"module:{lv.id}:{m.id}"] = m_item
                for lid in m.lessons:
                    if lid not in self.cur.lessons:
                        continue
                    lesson = self.cur.lessons[lid]
                    st = prog.lesson_status(lid, states)
                    item = QTreeWidgetItem([f"{ICON[st]}  {lesson.code}  {lesson.title}"])
                    item.setData(0, Qt.ItemDataRole.UserRole, ("lesson", lid))
                    tip = f"{lesson.title} - {STATUS_TEXT[st]}"
                    s = states.get(lid)
                    if s and s.get("best_score") is not None:
                        tip += f" (best score {s['best_score']:.0f}%, {s['attempts']} attempt(s))"
                    item.setToolTip(0, tip)
                    if st == LOCKED:
                        item.setForeground(0, QBrush(QColor(c["muted"])))
                    elif st == PASSED:
                        item.setForeground(0, QBrush(QColor(c["good"])))
                    m_item.addChild(item)
                    self.items[f"lesson:{lid}"] = item
                    if lid == current:
                        m_item.setExpanded(True)
                        lv_item.setExpanded(True)
                        self.tree.setCurrentItem(item)
                if first and any(prog.lesson_status(l, states) in (AVAILABLE, IN_PROGRESS) for l in m.lessons if l in self.cur.lessons):
                    m_item.setExpanded(True)
            if lv.exam and lv.exam in self.cur.exams:
                self._exam_item(lv_item, lv.exam, prog, c)
            if first and unlocked:
                lv_item.setExpanded(True)
        if self.cur.final_exam and self.cur.final_exam in self.cur.exams:
            root = QTreeWidgetItem(["Final examination"])
            f = root.font(0)
            f.setBold(True)
            root.setFont(0, f)
            self.tree.addTopLevelItem(root)
            self._exam_item(root, self.cur.final_exam, prog, c)
            root.setExpanded(True)
        for k in expanded:
            if k in self.items:
                self.items[k].setExpanded(True)

    def _exam_item(self, parent, exam_id, prog: Progression, c):
        exam = self.cur.exams[exam_id]
        passed = prog.store.exam_passed(prog.pid, exam_id)
        avail = prog.exam_available(exam_id)
        best = prog.store.best_exam(prog.pid, exam_id)
        icon = ICON[PASSED] if passed else (ICON[AVAILABLE] if avail else ICON[LOCKED])
        text = f"{icon}  {exam.title}"
        if best:
            text += f"  ({best['score']:.0f}%)"
        item = QTreeWidgetItem([text])
        item.setData(0, Qt.ItemDataRole.UserRole, ("exam", exam_id))
        item.setForeground(0, QBrush(QColor(c["good"] if passed else c["accent"] if avail else c["muted"])))
        item.setToolTip(0, exam.description)
        parent.addChild(item)
        self.items[f"exam:{exam_id}"] = item

    def _activated(self, item, _col=0):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, ident = data
        if kind == "lesson":
            self.lessonSelected.emit(ident)
        elif kind == "exam":
            self.examSelected.emit(ident)

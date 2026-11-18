"""Informational pages shown in the main area: dashboard, practice mode, welcome, exam intro."""
from __future__ import annotations

import html
import json
from datetime import datetime

from .qt import Signal
from .qt import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ..curriculum.loader import Curriculum
from ..progress.progression import Progression
from .render import page, render_markdown
from .theme import colors, content_css


def _bar(pct: float, c: dict, width: int = 260) -> str:
    filled = max(0, min(width, int(width * pct / 100)))
    return (f'<table cellspacing="0" cellpadding="0" width="{width}"><tr>'
            f'<td width="{max(filled, 1)}" bgcolor="{c["highlight"]}" height="12"></td>'
            f'<td width="{max(width - filled, 1)}" bgcolor="{c["alt"]}"></td></tr></table>')


class HtmlPage(QWidget):
    def __init__(self, theme: str, font_size: int, parent=None):
        super().__init__(parent)
        self.theme, self.font_size = theme, font_size
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.banner = QLabel()
        self.banner.setProperty("role", "banner")
        lay.addWidget(self.banner)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        lay.addWidget(self.browser, 1)
        self.buttons = QHBoxLayout()
        lay.addLayout(self.buttons)

    def set_html(self, body: str) -> None:
        self.browser.setHtml(page(body, content_css(self.theme, self.font_size)))


class DashboardPage(HtmlPage):
    def __init__(self, cur: Curriculum, theme, font_size, parent=None):
        super().__init__(theme, font_size, parent)
        self.cur = cur
        self.banner.setText("Progress dashboard")
        self.continue_btn = QPushButton("Continue learning")
        self.continue_btn.setProperty("primary", True)
        self.export_btn = QPushButton("Export progress report...")
        self.buttons.addWidget(self.export_btn)
        self.buttons.addStretch()
        self.buttons.addWidget(self.continue_btn)

    def show_progress(self, prog: Progression, profile) -> None:
        c = colors(self.theme)
        ov = prog.overview()
        cur = self.cur
        b = f"<h1>{html.escape(profile.display_name)}</h1>"
        b += (f'<p class="muted">Student profile <b>{html.escape(profile.username)}</b> &middot; created '
              f'{datetime.fromtimestamp(profile.created_at):%d %b %Y}</p>')
        b += "<table cellpadding='6'>"
        b += f"<tr><td>Course completed</td><td>{_bar(ov.percent_complete, c)}</td><td><b>{ov.percent_complete:.0f}%</b></td></tr>"
        b += f"<tr><td>Current level</td><td colspan='2'><b>{cur.level(ov.current_level).title}</b></td></tr>"
        b += f"<tr><td>Lessons passed</td><td colspan='2'><b>{ov.lessons_passed}</b> of {ov.lessons_total}</td></tr>"
        b += (f"<tr><td>Average best score</td><td colspan='2'><b>"
              f"{'-' if ov.average_score is None else f'{ov.average_score:.0f}%'}</b></td></tr>")
        b += f"<tr><td>Overall competency</td><td colspan='2'><b>{html.escape(ov.competency)}</b></td></tr>"
        b += f"<tr><td>Hints used</td><td colspan='2'>{ov.hints_used}</td></tr></table>"

        b += "<h2>Levels</h2><table cellpadding='6'>"
        for lv in cur.levels:
            done, total = ov.level_progress[lv.id]
            pct = 100 * done / total if total else 0
            ex = ov.exams.get(lv.exam) if lv.exam else None
            exam_txt = ("not attempted" if not ex else
                        f"best {ex['score']:.0f}% - {'passed' if prog.store.exam_passed(prog.pid, lv.exam) else 'not passed'}")
            lock = "" if prog.level_unlocked(lv.id) else " (locked)"
            b += (f"<tr><td><b>{lv.number}. {lv.title}</b>{lock}</td><td>{_bar(pct, c, 200)}</td>"
                  f"<td>{done}/{total} lessons</td><td class='muted'>Exam: {exam_txt}</td></tr>")
        if cur.final_exam:
            ex = ov.exams.get(cur.final_exam)
            best = "not attempted" if not ex else "best {:.0f}%".format(ex["score"])
            b += (f"<tr><td><b>Final examination</b></td><td colspan='3' class='muted'>"
                  f"{best}</td></tr>")
        b += "</table>"

        b += "<h2>Areas requiring improvement</h2>"
        if ov.improvement_areas:
            b += "<ul>" + "".join(f"<li>{html.escape(a)}</li>" for a in ov.improvement_areas) + "</ul>"
        else:
            b += "<p class='muted'>Nothing flagged - keep going!</p>"

        states = prog.store.all_lesson_states(prog.pid)
        done = [(lid, s) for lid, s in states.items() if s["status"] == "passed" and lid in cur.lessons]
        b += "<h2>Completed lessons</h2>"
        if done:
            hints = {}
            for lid, _ in done:
                hints[lid] = sum(int(v["hints"] or 0) for v in prog.store.exercise_summary(prog.pid, lid).values())
            done.sort(key=lambda x: x[1]["completed_at"] or 0)
            b += "<table cellpadding='5' cellspacing='0' width='100%'>"
            b += "<tr><th>Lesson</th><th>Completed</th><th>Best score</th><th>Attempts</th><th>Exercise hints</th></tr>"
            for lid, s in done:
                l = cur.lessons[lid]
                when = datetime.fromtimestamp(s["completed_at"]).strftime("%d %b %Y") if s["completed_at"] else "-"
                b += (f"<tr><td>{l.code} {html.escape(l.title)}</td><td>{when}</td>"
                      f"<td>{(s['best_score'] or 0):.0f}%</td><td>{s['attempts']}</td><td>{hints[lid]}</td></tr>")
            b += "</table>"
        else:
            b += "<p class='muted'>No lesson completed yet.</p>"

        b += "<h2>Recent assessment results</h2>"
        if ov.recent:
            b += "<table cellpadding='5' cellspacing='0' width='100%'>"
            b += "<tr><th>Date</th><th>Assessment</th><th>Score</th><th>Result</th><th>Hints</th></tr>"
            for a in ov.recent:
                if a["kind"] == "lesson" and a["ref_id"] in cur.lessons:
                    name = f"{cur.lessons[a['ref_id']].code} {cur.lessons[a['ref_id']].title}"
                else:
                    name = cur.exams[a["ref_id"]].title if a["ref_id"] in cur.exams else a["ref_id"]
                res = "<span class='good'>passed</span>" if a["passed"] else "<span class='bad'>retry</span>"
                b += (f"<tr><td>{datetime.fromtimestamp(a['finished_at']):%d %b %Y %H:%M}</td>"
                      f"<td>{html.escape(name)}</td><td>{a['score']:.0f}%</td><td>{res}</td>"
                      f"<td>{a['hints_used']}</td></tr>")
            b += "</table>"
        else:
            b += "<p class='muted'>No assessments taken yet.</p>"
        self.set_html(b)


class PracticePage(HtmlPage):
    openTerminal = Signal()
    resetLab = Signal()

    def __init__(self, theme, font_size, parent=None):
        super().__init__(theme, font_size, parent)
        self.banner.setText("PRACTICE MODE  -  nothing here is graded")
        self.banner.setProperty("role", "practice")
        open_btn = QPushButton("Open a practice terminal")
        open_btn.setProperty("primary", True)
        open_btn.clicked.connect(self.openTerminal)
        reset_btn = QPushButton("Reset the practice lab")
        reset_btn.clicked.connect(self.resetLab)
        self.buttons.addWidget(reset_btn)
        self.buttons.addStretch()
        self.buttons.addWidget(open_btn)
        self.set_html(render_markdown(PRACTICE_TEXT, theme))


PRACTICE_TEXT = """
# Practice mode

Practice mode gives you a **separate laboratory** that has nothing to do with your lessons.
Nothing you do here is marked or recorded, and it cannot affect your lesson exercises.

You have full administrator rights (`sudo`, password `student`).  **Break things on purpose**
and then work out how to fix them - that is how system administrators really learn.

:::tip
If the practice lab gets into a state you cannot fix, press **Reset the practice lab**.
You get a factory-fresh system in a few seconds.
:::

## Ideas for experiments

| Try this | Then work out... |
|---|---|
| `sudo chmod 000 /etc/hostname` | why `cat /etc/hostname` fails, and how to repair it |
| `sudo systemctl stop cron` | how to tell what is running, and how to restart it |
| Fill a file system: `fallocate -l 200M ~/big` | how to find what is using space (`du`, `df`) |
| `sudo mv /usr/bin/nano /usr/bin/nano.bak` | what "command not found" really means (`type`, `$PATH`) |
| Write a script with an infinite loop and run it in the background | how to find and stop it (`ps`, `kill`, `jobs`) |
| `sudo userdel -r` a user you created | what happens to their files |
| Add a broken line to `/etc/fstab` | how `mount -a` reports problems |
| `sudo nft add rule inet filter input drop` (after creating the table) | how firewalls block traffic |

## Things that work in the lab

`systemctl`, `journalctl`, `cron`, `sshd`, users and groups, `apt install` (offline
repository: `tree`, `sl`, `figlet`, `hello`, `jq`, `ncdu`, `cowsay`, `htop`), ACLs,
capabilities, `nft`, `mount -t tmpfs`, disk *image* files with `mkfs`, `parted`, `fdisk`.

Run `lab-info` in the terminal for details.
"""


class ExamIntroPage(HtmlPage):
    start = Signal(str)

    def __init__(self, theme, font_size, parent=None):
        super().__init__(theme, font_size, parent)
        self.exam_id = ""
        self.start_btn = QPushButton("Begin examination")
        self.start_btn.setProperty("primary", True)
        self.start_btn.clicked.connect(lambda: self.start.emit(self.exam_id))
        self.buttons.addStretch()
        self.buttons.addWidget(self.start_btn)

    def show_exam(self, cur: Curriculum, prog: Progression, exam_id: str, passing: int) -> None:
        exam = cur.exams[exam_id]
        self.exam_id = exam_id
        self.banner.setText(exam.title)
        avail = prog.exam_available(exam_id)
        n_prac = sum(1 for q in exam.questions if q.is_practical)
        b = f"<h1>{html.escape(exam.title)}</h1>" + render_markdown(exam.description, self.theme)
        b += (f"<ul><li>{len(exam.questions) + exam.sample_from_lessons} questions, of which "
              f"{n_prac} are practical tasks in the laboratory</li>"
              f"<li>Pass mark: {exam.passing_score or passing}%</li>"
              f"<li>Practical tasks carry extra weight and are marked on the result you achieve, "
              f"not on the commands you type</li>"
              f"<li>Hints are not available in examinations</li></ul>")
        hist = prog.store.assessments(prog.pid, "exam", exam_id)
        if hist:
            b += "<h3>Previous attempts</h3><ul>" + "".join(
                f"<li>{datetime.fromtimestamp(h['finished_at']):%d %b %Y}: {h['score']:.0f}% "
                f"({'passed' if h['passed'] else 'not passed'})</li>" for h in hist[:5]) + "</ul>"
        if not avail:
            if exam.level:
                b += ("<p class='warn'>This examination unlocks when you have passed every lesson in "
                      f"the {html.escape(cur.level(exam.level).title)} level.</p>")
            else:
                b += "<p class='warn'>The final examination unlocks after the Advanced level examination.</p>"
        else:
            b += ("<p>The examination uses your lesson laboratory. Tasks may create files there. "
                  "When you are ready, press <b>Begin examination</b>.</p>")
        self.start_btn.setEnabled(avail)
        self.set_html(b)


class WelcomePage(HtmlPage):
    def __init__(self, theme, font_size, parent=None):
        super().__init__(theme, font_size, parent)
        self.banner.setText("Welcome to Linux Tutor")
        self.go_btn = QPushButton("Start / continue learning")
        self.go_btn.setProperty("primary", True)
        self.buttons.addStretch()
        self.buttons.addWidget(self.go_btn)
        self.set_html(render_markdown(WELCOME_TEXT, theme))


WELCOME_TEXT = """
# Welcome to Linux Tutor

Linux Tutor is your personal Linux instructor, a real Linux laboratory and an examiner in
one application.

```
 +-----------------+--------------------------------------+-----------------+
 |  Course         |  Lecture: explanations and examples  |  Exercises,     |
 |  navigation     |                                      |  hints and      |
 |                 +--------------------------------------+  feedback       |
 |  (your levels,  |  Terminal: a real Bash shell in your |                 |
 |   lessons and   |  own isolated Linux laboratory       |                 |
 |   exams)        |                                      |                 |
 +-----------------+--------------------------------------+-----------------+
```

**How it works**

1. Choose a lesson on the left.  Read it section by section.
2. Try the examples in the **terminal**.  It is a genuine Linux system running in a safe,
   isolated container - you cannot damage your own computer, and you can reset it at any time.
3. Do the **exercises** on the right.  The tutor examines the *result* of your work, so any
   correct method is accepted.  Ask for hints when you need them.
4. Take the **end-of-lesson assessment**.  Pass it to unlock the next lesson.
5. Each level ends with an **examination**; passing it unlocks the next level.

Use **Practice mode** whenever you want to experiment without being graded.
"""

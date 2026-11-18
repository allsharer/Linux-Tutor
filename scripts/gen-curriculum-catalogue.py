#!/usr/bin/env python3
"""Print a Markdown catalogue of the curriculum (used in CURRICULUM.md)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from linux_tutor import paths  # noqa: E402
from linux_tutor.curriculum.loader import load_curriculum  # noqa: E402

cur = load_curriculum(paths.curriculum_dir())
tot_ex = tot_q = tot_p = 0
print("| Code | Lesson | Exercises | Assessment questions (practical) |")
print("|---|---|---|---|")
for lv in cur.levels:
    print(f"| **{lv.number}** | **{lv.title} level** - examination: {cur.exams[lv.exam].title} | | |")
    for m in lv.modules:
        for lid in m.lessons:
            l = cur.lessons[lid]
            n_p = sum(q.is_practical for q in l.quiz.questions)
            tot_ex += len(l.exercises); tot_q += len(l.quiz.questions); tot_p += n_p
            print(f"| {l.code} | {l.title} *({m.title})* | {len(l.exercises)} | {len(l.quiz.questions)} ({n_p}) |")
exam_p = sum(q.is_practical for e in cur.exams.values() for q in e.questions)
print(f"\n**Totals:** {len(cur.lessons)} lessons, {tot_ex} exercises, {tot_q} assessment questions "
      f"({tot_p} practical), {len(cur.exams)} examinations with {exam_p} practical tasks, "
      f"{len(cur.glossary)} glossary terms.")

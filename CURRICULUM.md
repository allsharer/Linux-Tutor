# Curriculum

The curriculum lives in `curriculum/` as YAML files and is loaded at start-up; nothing is
hard-coded in the application.

```
curriculum/
├── curriculum.yaml      levels -> modules -> ordered lesson ids; exam ids
├── glossary.yaml        term: definition
├── level1/*.yaml        Beginner lessons      (one file per lesson)
├── level2/*.yaml        Intermediate lessons
├── level3/*.yaml        Advanced lessons
├── exams/*.yaml         level examinations and the final examination
└── plugins/*.py         optional extra check types (trusted code)
```

## Teaching design

* **Concepts before commands.**  Each lesson starts with *why* (the idea, a diagram), then
  *how* (commands with output explained), then practice.
* **One idea per page.**  Lectures are split into sections shown one at a time, each with
  an optional "Explain further" page.
* **Learning by doing.**  Every lesson has practical exercises (2-3) in the real lab, and
  every end-of-lesson assessment includes at least one practical task.
* **Any valid method.**  Exercises state the *goal*, not the command.  Lessons mention
  alternatives and the tutor recognises them.
* **Spiral progression.**  Later lessons reuse earlier skills (redirection appears in lesson 1.02
  informally, is taught in 1.17, deepened in 2.08 and used everywhere after).
* **Realistic scenarios.**  Intermediate and Advanced tasks are framed as real requests:
  "a service will not start", "onboard a colleague", "a disk is full".
* **Honest limits.**  Where the container cannot do something real (kernel modules, LVM),
  the lesson says so and teaches with configuration files and real tool output instead.

## Progression

* A lesson unlocks when its prerequisites are **passed** (default: the previous lesson of
  the level).  Passing = scoring at least the pass mark (default 80 %) in the
  end-of-lesson assessment.
* A level examination unlocks when every lesson of the level is passed; passing it unlocks
  the next level.  The final examination unlocks after the Advanced examination.
* Instructors can open everything with `"instructor": {"unlock_all": true}`.

## Catalogue

| Code | Lesson | Exercises | Assessment questions (practical) |
|---|---|---|---|
| **1** | **Beginner level** - examination: Beginner Level Examination | | |
| 1.01 | Introduction to Linux *(Getting started)* | 2 | 7 (1) |
| 1.02 | Understanding Linux distributions *(Getting started)* | 2 | 6 (1) |
| 1.03 | The Linux desktop and the command-line interface *(Getting started)* | 2 | 6 (1) |
| 1.04 | Opening and using a terminal *(Getting started)* | 2 | 7 (1) |
| 1.05 | Understanding the Linux filesystem *(The filesystem)* | 2 | 7 (1) |
| 1.06 | Absolute and relative paths *(The filesystem)* | 2 | 7 (1) |
| 1.07 | Navigating directories *(The filesystem)* | 2 | 6 (1) |
| 1.08 | Creating and removing directories *(The filesystem)* | 3 | 6 (1) |
| 1.09 | Creating, viewing and editing files *(The filesystem)* | 3 | 7 (1) |
| 1.10 | Copying, moving and renaming files *(The filesystem)* | 3 | 7 (1) |
| 1.11 | Understanding filenames and extensions *(The filesystem)* | 2 | 7 (1) |
| 1.12 | Introduction to Linux commands *(Working with commands)* | 3 | 6 (1) |
| 1.13 | Understanding command syntax and options *(Working with commands)* | 2 | 6 (1) |
| 1.14 | Getting help using man, info and --help *(Working with commands)* | 2 | 7 (1) |
| 1.15 | Understanding users and groups *(Users and permissions)* | 3 | 7 (1) |
| 1.16 | Basic file permissions *(Users and permissions)* | 3 | 7 (1) |
| 1.17 | Introduction to pipes and redirection *(Putting commands to work)* | 3 | 7 (1) |
| 1.18 | Basic text processing *(Putting commands to work)* | 3 | 7 (1) |
| 1.19 | Understanding processes *(Putting commands to work)* | 3 | 7 (1) |
| 1.20 | Basic system information *(Putting commands to work)* | 2 | 6 (1) |
| **2** | **Intermediate level** - examination: Intermediate Level Examination | | |
| 2.01 | Advanced filesystem navigation *(Files in depth)* | 3 | 6 (1) |
| 2.02 | File ownership and permissions *(Files in depth)* | 2 | 7 (1) |
| 2.03 | chmod, chown and chgrp *(Files in depth)* | 2 | 6 (1) |
| 2.04 | Symbolic and hard links *(Files in depth)* | 3 | 7 (1) |
| 2.05 | Searching files using find, locate and grep *(Files in depth)* | 3 | 6 (1) |
| 2.06 | Text processing with sed, awk, cut, sort and friends *(Text and data streams)* | 3 | 7 (1) |
| 2.07 | Pipes and command chaining *(Text and data streams)* | 3 | 6 (1) |
| 2.08 | Input/output redirection *(Text and data streams)* | 2 | 6 (1) |
| 2.09 | Environment variables *(The shell and scripting)* | 2 | 7 (1) |
| 2.10 | Shell scripting fundamentals *(The shell and scripting)* | 3 | 7 (1) |
| 2.11 | Conditional statements *(The shell and scripting)* | 3 | 7 (1) |
| 2.12 | Loops and functions *(The shell and scripting)* | 3 | 7 (1) |
| 2.13 | Process management *(Processes and jobs)* | 2 | 7 (1) |
| 2.14 | Job control *(Processes and jobs)* | 1 | 7 (1) |
| 2.15 | Package management *(Software)* | 3 | 7 (1) |
| 2.16 | Software installation and removal *(Software)* | 3 | 7 (1) |
| 2.17 | Disk usage and storage management *(Storage)* | 3 | 6 (1) |
| 2.18 | Mounting and unmounting filesystems *(Storage)* | 3 | 7 (1) |
| 2.19 | Networking fundamentals *(Networking)* | 3 | 7 (1) |
| 2.20 | SSH fundamentals *(Networking)* | 2 | 7 (1) |
| 2.21 | Scheduling tasks using cron *(Operations)* | 2 | 7 (1) |
| 2.22 | Logs and system monitoring *(Operations)* | 2 | 7 (1) |
| 2.23 | Basic troubleshooting *(Operations)* | 2 | 6 (1) |
| **3** | **Advanced level** - examination: Advanced Level Examination | | |
| 3.01 | Advanced Bash scripting *(Advanced shell and text)* | 2 | 7 (1) |
| 3.02 | Shell functions and advanced parameter expansion *(Advanced shell and text)* | 2 | 7 (1) |
| 3.03 | Regular expressions *(Advanced shell and text)* | 2 | 7 (1) |
| 3.04 | Advanced text processing *(Advanced shell and text)* | 3 | 7 (1) |
| 3.05 | Systemd and service management *(The system)* | 2 | 7 (1) |
| 3.06 | Boot processes and system initialisation *(The system)* | 3 | 7 (1) |
| 3.07 | User and group administration *(The system)* | 3 | 7 (1) |
| 3.08 | Advanced permissions and ACLs *(The system)* | 2 | 7 (1) |
| 3.09 | Linux capabilities *(The system)* | 2 | 7 (1) |
| 3.10 | Disk partitioning and filesystem management *(Storage administration)* | 2 | 7 (1) |
| 3.11 | LVM and storage administration *(Storage administration)* | 2 | 7 (1) |
| 3.12 | Networking configuration and troubleshooting *(Network administration)* | 2 | 7 (1) |
| 3.13 | Firewall management *(Network administration)* | 2 | 7 (1) |
| 3.14 | SSH administration and security *(Network administration)* | 2 | 7 (1) |
| 3.15 | Process priorities and resource management *(Resources, kernel and logs)* | 2 | 7 (1) |
| 3.16 | Kernel fundamentals and modules *(Resources, kernel and logs)* | 3 | 7 (1) |
| 3.17 | System logs and journalctl *(Resources, kernel and logs)* | 2 | 7 (1) |
| 3.18 | Backup and recovery *(Operations and security)* | 2 | 7 (1) |
| 3.19 | Automation and task scheduling *(Operations and security)* | 2 | 7 (1) |
| 3.20 | Security hardening *(Operations and security)* | 3 | 7 (1) |
| 3.21 | Troubleshooting complex system problems *(Operations and security)* | 2 | 7 (1) |
| 3.22 | System administration scenarios *(Operations and security)* | 3 | 5 (1) |

**Totals:** 65 lessons, 157 exercises, 439 assessment questions (65 practical), 4 examinations with 20 practical tasks, 91 glossary terms.

Each examination combines its own scenario-based practical tasks (new situations, not
repeated exercises) with a random sample of theory questions drawn across the level's
lessons; practical questions count double.

## Lesson file format

```yaml
id: b08-directories            # unique; referenced from curriculum.yaml
level: beginner                # beginner | intermediate | advanced
module: filesystem             # module id from curriculum.yaml
title: Creating and removing directories
duration: 25                   # minutes (informational)
prerequisites: [b07-navigating]  # optional; default = previous lesson of the level
objectives: [ ... ]            # shown on the introduction page and the summary
summary: |                     # optional Markdown for the summary page
references: [{title: ..., url: ...}]

sections:                      # the lecture, one page per section
  - title: Creating a directory with mkdir
    content: |                 # Markdown; call-outs with :::note / :::tip / :::warning / :::important
      ...
    more: |                    # optional "Explain further" text
    examples:                  # optional; each gets a "Try it" link that types the command
      - {command: "mkdir ~/notes", explanation: "...", output: "..."}

exercises:                     # practical exercises (right-hand panel)
  - id: make-projects
    title: Create a projects directory
    instructions: |            # Markdown - state the GOAL, not the command
    answer_prompt: "..."       # optional: also show an answer box (for "find out X" tasks)
    setup: |                   # bash, run as root in the lab when the task is set up;
                               # {home} and {user} are expanded
    cleanup: |                 # optional bash run afterwards
    reference: mkdir ~/projects        # the lesson's method (shown in the last hint and
                                       # used to recognise "alternative methods")
    method_patterns: ['mkdir']         # optional regexes describing the taught method
    checks:                    # ALL must pass - see ASSESSMENT.md for the check types
      - {type: dir_exists, path: ~/projects, fail: "Custom explanation"}
    constraints:               # safety: must still hold, else "correct with side effects"
      - {type: file_exists, path: ~/keep-me/data.txt}
    diagnostics:               # explain WHY it failed; first matching entry is shown
      - when: {type: find, name: projects, kind: d, exclude: [~/projects]}
        message: "Created at {found} instead of your home directory..."
        review: b06-paths      # lesson to suggest for revision
    hints:                     # exactly four, progressively more explicit
      - conceptual hint
      - which Linux feature to use
      - a command example
      - complete explanation
    explanation: |             # shown after the last hint
    # used only by the automated tests (tests/lab_harness.py):
    solution: ...              # script that solves it (default: reference)
    alternatives: [...]        # other valid methods - must ALSO be marked correct
    wrong: [{run: ..., expect: partial|incorrect|correct_side_effects, feedback: substring}]
    test_answer: ...           # answer typed by the harness for answer_prompt exercises

quiz:                          # the end-of-lesson assessment
  passing_score: 80            # optional; default from configuration
  questions:
    - {id: q1, type: mcq, prompt: ..., options: [...], answer: 1, explanation: ..., topic: ...}
    - {id: q2, type: multi, options: [...], answer: [0, 2]}
    - {id: q3, type: truefalse, answer: false}
    - {id: q4, type: short, answer: ["-i", "re:--interactive(=always)?"]}  # strings or re: regexes
    - {id: q5, type: interpret, output: "...command output...", options: [...], answer: 2}
    - {id: q6, type: troubleshoot, prompt: "scenario...", options: [...], answer: 1}
    - id: q7
      type: practical          # same fields as an exercise
      prompt: ...
      checks: [...]
      hints: [...]
```

`topic` names the section (or lesson id) to list under "Areas to revise" when the question
is answered wrongly.

## Adding a lesson

1. Copy an existing lesson file into the right `levelN/` directory and edit it.
2. Add its id to the right module in `curriculum.yaml`.
3. `python3 -m linux_tutor.cli validate` - must report 0 warnings.
4. `python3 -m tests.lab_harness <lesson-id>` - every practical task must be solvable by
   its solution and alternatives, unsolved without work, and wrong attempts must be caught.
5. Open it in the application (`"instructor": {"unlock_all": true}` helps).

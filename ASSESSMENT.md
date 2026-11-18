# Assessment methodology

## Principle: mark the outcome, not the keystrokes

Linux almost always offers several ways to reach a goal.  `mkdir ~/projects`,
`cd ~ && mkdir projects`, `mkdir "$HOME/projects"` and `install -d ~/projects` all create
the same directory.  Linux Tutor therefore **never compares the student's command with an
expected command**.  It inspects the **state of the laboratory** after the student has
worked, with objective checks executed inside the lab.

Conversely, typing a command that *looks* right earns nothing unless it worked: the test
suite verifies that `echo mkdir ~/projects` (which prints but does nothing) is not
rewarded.

## The pipeline for one task

```
Set up task ──► setup script (root) ──► remember command-log position
                                         │
Student works in the real terminal ◄─────┘
                                         │
Check my work ─► checks (all must pass) ─► constraints (side effects) ─► classify
                         │ failed?
                         └─► diagnostics: find out WHY, explain, suggest revision
```

### Check types (`linux_tutor/assessment/checks.py`)

| Area | Checks |
|---|---|
| Filesystem | `path_exists`, `file_exists`, `dir_exists`, `not_exists`, `dir_empty`, `symlink` (target / resolves_to / valid), `hardlink` |
| Content | `file_contains` (text / regexes), `file_not_contains`, `file_equals`, `file_lines`, `file_matches_command` (content equals live output of a command in the lab) |
| Permissions | `mode` (exact octal, or `has`/`lacks` like `u+x`, `g+s`, `o+w`), `owner` (user/group), `acl`, `capability` |
| Accounts | `user_exists` (shell/home/uid/comment), `user_absent`, `group_exists`, `user_in_group`, `user_locked` |
| Processes & services | `process_running` (pattern, user), `process_absent`, `process_nice`, `service_active`, `service_enabled`, `port_listening` |
| System | `package_installed`, `crontab_contains`, `mounted` (type/options), `nft_ruleset_contains`, `journal_contains` (unit/tag), `env_var` (in a *new* login shell, exported) |
| Behaviour | `command` (run a verification command: exit code, stdout equals/contains/regex), `script` (run the student's script with arguments/stdin as the student; exit code and output) |
| Knowledge | `answer` (typed answer equals a value, matches a regex, or equals the live output of a command in the lab) |
| Logic | `all_of`, `any_of` (alternative acceptable outcomes), `not` |
| Diagnostics only | `find` (where did the student create it instead?), `history_matches` (hint based on what was typed - never used for marking) |

Checks prefer **behavioural verification** over appearance: scripts are executed with
test arguments; access rights are tested by actually reading a file *as another user*;
firewall rules are tested by connecting to the port; services must be running *and*
answering; environment variables are read from a fresh login shell.

## Outcomes

| Outcome | Meaning | Credit in assessments |
|---|---|---|
| **Correct** | every check passed, no constraint violated | 100 % |
| **Correct - alternative method** | as above, but the commands typed did not use the lesson's method (`method_patterns`, or the first word of `reference`); the student is told this is perfectly valid and shown the lesson's approach for comparison | 100 % |
| **Correct, but with unwanted side effects** | the goal is met but a constraint failed (e.g. deleted more than asked, made a file world-writable, replaced PATH, modified a vendor unit file) | 50 % |
| **Partially complete** | some checks passed | 80 % × fraction passed |
| **Not yet correct** | no check passed | 0 % |
| **Could not be verified** | the lab could not be inspected (not running, timed out) - explicitly *not* counted as the student's mistake | 0 % (retry) |

## Feedback

Each failed check has a specific message ("~/projects exists but it is a regular file,
not a directory").  Diagnostics then look for the typical mistake and explain it:

> The directory was created at /tmp/projects, not in your home directory.  A relative
> name is created inside your *current* directory...  Review: 1.06 Absolute and relative paths.

Other diagnostic examples in the curriculum: a name with the wrong case; `>` used where
`>>` was needed; the `$PORT` placeholder expanded by an unquoted here-document; minute
and hour fields swapped in a crontab; `usermod -G` without `-a`; a missing `+` in
`lvextend -L`.

## Hints

Every exercise has exactly four hints, revealed one at a time:

1. **concept** - what kind of thing is needed;
2. **Linux feature** - which command/option/file;
3. **example** - a concrete command;
4. **complete explanation** - how and why it works (plus the exercise's explanation).

Hints never block or reduce an exercise's result; the number used is **recorded** (per
exercise and per assessment) and shown on the dashboard.  In examinations hints are
disabled by default (`assessment.allow_hints_in_exams`).

## End-of-lesson assessments

* Question types: multiple choice, multiple answer, true/false, short answer (exact
  strings or regular expressions), command-output interpretation, troubleshooting
  scenarios, and **practical tasks** in the lab.
* Practical questions have weight 2 (configurable `assessment.practical_weight`); every
  lesson's assessment contains at least one.
* Practical answers are evaluated on submission and may be resubmitted until the
  assessment is finished.  Theory answers are marked at the end.
* The results page shows the score, the pass/retry decision, every question with the
  correct answer and an explanation for wrong answers, and **areas to revise** (from each
  question's `topic` and from diagnostics).
* Pass mark: 80 % by default; configurable per lesson (`quiz.passing_score`), globally,
  and lockable by an instructor.

## Examinations

Level examinations add new scenario-based practical tasks (the student must transfer
skills to unfamiliar situations) to a random sample of theory questions across the
whole level, chosen to spread across lessons.  The final examination spans all levels.
Passing a level examination unlocks the next level.

## Quality assurance of the assessments

Every practical task in the curriculum (157 exercises + 65 assessment tasks + 20
examination tasks) is executed by `tests/lab_harness.py` in a real laboratory:

1. evaluated with **no work done** → must *not* pass (no trivially-true checks);
2. the model **solution** → must pass;
3. every listed **alternative** method → must pass with the same result;
4. every listed **wrong** attempt → must give the expected outcome and feedback.

See TESTING.md for the latest results.

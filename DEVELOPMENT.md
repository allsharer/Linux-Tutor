# Development guide

## Setting up

```bash
sudo apt install podman uidmap python3-pyqt6 python3-pyte python3-yaml python3-markdown \
                 python3-pytest dpkg-dev rsync
python3 -m linux_tutor.cli build        # laboratory image
python3 -m linux_tutor --verbose        # run from the source tree
```

Optional: `python3-pyside6.qtwidgets` to test the PySide6 binding
(`LINUX_TUTOR_QT=pyside6|pyqt6` selects one).

To keep your own profile untouched while developing, relocate Linux Tutor's data
(**not** `XDG_DATA_HOME`, which would also move Podman's image store):

```bash
export LINUX_TUTOR_USER_DATA_DIR=/tmp/lt/data LINUX_TUTOR_CONFIG_DIR=/tmp/lt/config \
       LINUX_TUTOR_STATE_DIR=/tmp/lt/state LINUX_TUTOR_CACHE_DIR=/tmp/lt/cache
```

## Code layout and rules

See ARCHITECTURE.md.  Conventions:

* Python ≥ 3.10, `from __future__ import annotations`, standard library + Ubuntu packages only.
* Nothing outside `linux_tutor/ui/` imports Qt; UI code imports Qt names **only** from
  `linux_tutor/ui/qt.py` and uses fully-qualified enums (`Qt.Orientation.Horizontal`).
* No hard-coded paths: use `linux_tutor/paths.py`.
* Never execute student-influenced strings on the host; lab work goes through
  `LabBackend.exec()`.
* Slow operations (anything touching Podman) run through `ui/workers.run_task`.
* In lab scripts, beware of `pkill -f NAME` - it matches the `bash -c` script containing
  NAME and kills itself.  Use `pkill -x`, a copied binary with a unique name, or an
  anchored pattern (`'^python3 -m http.server 8080'`).
* Do not rely on `/usr/bin/nc` being signal-able in the lab (host AppArmor profile); copy
  it to a unique name instead.

## Adding a lesson

See CURRICULUM.md ("Adding a lesson").  Always run:

```bash
python3 -m linux_tutor.cli validate
python3 -m tests.lab_harness 'my-lesson-id'          # --keep reuses the running test lab
```

## Adding a check type

```python
# linux_tutor/assessment/checks.py  (or a plugin: <curriculum>/plugins/mycheck.py)
from linux_tutor.assessment.checks import CheckOutcome, check

@check("timezone_is", required=("zone",))
def timezone_is(ctx, spec):
    """The system time zone equals `zone`."""
    r = ctx.sh("timedatectl show -p Timezone --value")
    zone = r.stdout.strip()
    return CheckOutcome(zone == spec["zone"],
                        spec.get("fail", f"The time zone is {zone}, not {spec['zone']}."))
```

Existing lessons are unaffected; the validator recognises the new type automatically.

## Changing the laboratory image

Edit `lab/Containerfile` / `lab/files/`, **bump `LAB_IMAGE_VERSION`** in
`linux_tutor/lab/__init__.py`, rebuild (`python3 -m linux_tutor.cli build`), then run the
full harness (`python3 -m tests.lab_harness`).

## Tests

See TESTING.md.  Before committing: `python3 -m pytest -q` and, for curriculum or engine
changes, `python3 -m tests.lab_harness`.

## Releasing

1. Update `__version__`, CHANGELOG.md.
2. `python3 -m pytest -q && python3 -m tests.lab_harness`
3. `scripts/build-release.sh --with-image`
4. Clean-system test (DEPLOYMENT.md / TESTING.md).

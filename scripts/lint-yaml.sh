#!/bin/sh
# Quick YAML syntax check of every curriculum file (prints only errors).
cd "$(dirname "$0")/.." || exit 1
python3 - <<'PY'
import glob, yaml
bad = 0
for f in sorted(glob.glob("curriculum/**/*.yaml", recursive=True)):
    try:
        yaml.safe_load(open(f))
    except yaml.YAMLError as e:
        bad += 1
        m = getattr(e, "problem_mark", None)
        print(f"{f}:{m.line + 1 if m else '?'}: {getattr(e, 'problem', e)}")
raise SystemExit(1 if bad else 0)
PY

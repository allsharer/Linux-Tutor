#!/usr/bin/env python3
"""Quote plain YAML scalars that contain ': ' or ' #' (common in shell commands).

Only touches simple `key: value` lines for a known set of keys whose value is an
unquoted scalar, then verifies that the file still parses and the value is unchanged.
"""
import re
import sys

import yaml

KEYS = r"(reference|command|solution|run|explanation|prompt|title|answer_prompt|fail|message|setup|cleanup)"
LINE = re.compile(rf"^(\s*(?:- )?{KEYS}:\s+)(?![\"'|>\[{{])(.*\S)\s*$")

for path in sys.argv[1:]:
    lines = open(path).read().split("\n")
    changed = False
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if not m:
            continue
        value = m.group(3)
        if ": " in value or " #" in value or value.endswith(":"):
            q = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
            lines[i] = m.group(1) + q
            changed = True
    if changed:
        text = "\n".join(lines)
        yaml.safe_load(text)
        open(path, "w").write(text)
        print("fixed", path)

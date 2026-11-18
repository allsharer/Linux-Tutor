"""Outcome checks: objective tests of the laboratory's *state*.

Every check inspects the system (files, permissions, users, processes, services,
command output...) inside the lab.  None of them look at which command the student
typed, so any valid method of reaching the outcome is accepted.

Adding a new kind of assessment = writing one function decorated with ``@check``.
Existing lessons are unaffected.  Third-party checks can be dropped into
``$XDG_DATA_HOME/linux-tutor/plugins/*.py`` or ``<curriculum>/plugins/*.py``.

A check function receives a :class:`CheckContext` and the check specification
(the YAML mapping) and returns a :class:`CheckOutcome`.
"""
from __future__ import annotations

import importlib.util
import logging
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..lab.base import ExecResult, LabBackend, LabError

log = logging.getLogger(__name__)


@dataclass
class CheckOutcome:
    passed: bool
    message: str = ""          # explanation shown to the student when the check fails
    detail: str = ""           # technical detail (observed value)
    values: dict = field(default_factory=dict)   # used to format diagnostic messages


@dataclass
class CheckDef:
    func: Callable
    required: tuple[str, ...]
    description: str


CHECKS: dict[str, CheckDef] = {}
DIAGNOSTICS: dict[str, CheckDef] = {}


def check(name: str, required: tuple[str, ...] = (), registry: dict | None = None):
    def deco(func):
        (CHECKS if registry is None else registry)[name] = CheckDef(
            func, required, (func.__doc__ or "").strip().splitlines()[0] if func.__doc__ else "")
        return func
    return deco


class CheckContext:
    """Gives checks access to the lab plus a little cached session information."""

    def __init__(self, lab: LabBackend, answer: str | None = None):
        self.lab = lab
        self.answer = answer
        self.home = lab.student_home
        self.user = lab.student_user

    def path(self, p: str) -> str:
        p = str(p).replace("{home}", self.home).replace("{user}", self.user)
        if p == "~":
            return self.home
        if p.startswith("~/"):
            return self.home + p[1:]
        return p

    def q(self, p: str) -> str:
        return shlex.quote(self.path(p))

    def sh(self, script: str, user: str = "root", timeout: float | None = 30) -> ExecResult:
        return self.lab.exec(script, user=user, timeout=timeout)

    def read(self, path: str) -> str | None:
        r = self.sh(f"cat -- {self.q(path)}")
        return r.stdout if r.ok else None


def _msg(spec: dict, default: str) -> str:
    return spec.get("fail", default)


def _norm(text: str, spec: dict) -> str:
    if spec.get("ignore_case"):
        text = text.lower()
    if spec.get("ignore_whitespace", True):
        text = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return text


# --------------------------------------------------------------------------- filesystem
@check("path_exists", ("path",))
def path_exists(ctx: CheckContext, spec: dict) -> CheckOutcome:
    """A file, directory or link exists at the path."""
    r = ctx.sh(f"test -e {ctx.q(spec['path'])} -o -L {ctx.q(spec['path'])}")
    return CheckOutcome(r.ok, _msg(spec, f"Nothing exists at {ctx.path(spec['path'])}."))


@check("file_exists", ("path",))
def file_exists(ctx, spec):
    """A regular file exists at the path."""
    p = ctx.q(spec["path"])
    r = ctx.sh(f"if test -f {p}; then echo FILE; elif test -e {p}; then stat -c %F {p}; else echo NONE; fi")
    kind = r.stdout.strip()
    if kind == "FILE":
        return CheckOutcome(True)
    if kind == "NONE":
        return CheckOutcome(False, _msg(spec, f"The file {ctx.path(spec['path'])} does not exist."))
    return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} exists but it is a {kind}, not a regular file."),
                        detail=kind)


@check("dir_exists", ("path",))
def dir_exists(ctx, spec):
    """A directory exists at the path."""
    p = ctx.q(spec["path"])
    r = ctx.sh(f"if test -d {p} && ! test -L {p}; then echo DIR; elif test -e {p}; then stat -c %F {p}; else echo NONE; fi")
    kind = r.stdout.strip()
    if kind == "DIR":
        return CheckOutcome(True)
    if kind == "NONE":
        return CheckOutcome(False, _msg(spec, f"The directory {ctx.path(spec['path'])} does not exist."))
    return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} exists but it is a {kind}, not a directory."))


@check("not_exists", ("path",))
def not_exists(ctx, spec):
    """Nothing exists at the path (it was removed or never created)."""
    r = ctx.sh(f"test -e {ctx.q(spec['path'])} -o -L {ctx.q(spec['path'])}")
    return CheckOutcome(not r.ok, _msg(spec, f"{ctx.path(spec['path'])} still exists."))


@check("dir_empty", ("path",))
def dir_empty(ctx, spec):
    """The directory exists and contains nothing."""
    r = ctx.sh(f"test -d {ctx.q(spec['path'])} && test -z \"$(ls -A {ctx.q(spec['path'])})\"")
    return CheckOutcome(r.ok, _msg(spec, f"{ctx.path(spec['path'])} is not an empty directory."))


@check("symlink", ("path",))
def symlink(ctx, spec):
    """The path is a symbolic link (optionally pointing at `target`, or resolving to `resolves_to`)."""
    p = ctx.q(spec["path"])
    r = ctx.sh(f"test -L {p} && readlink {p} && (readlink -f {p} || true)")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} is not a symbolic link."))
    lines = r.stdout.splitlines() + ["", ""]
    target, resolved = lines[0], lines[1]
    if "target" in spec and target != ctx.path(spec["target"]):
        return CheckOutcome(False, _msg(spec, f"The link points to '{target}', expected '{ctx.path(spec['target'])}'."),
                            detail=target)
    if "resolves_to" in spec and resolved != ctx.path(spec["resolves_to"]):
        return CheckOutcome(False, _msg(spec, f"The link resolves to '{resolved}', not '{ctx.path(spec['resolves_to'])}'."),
                            detail=resolved)
    if spec.get("valid") and ctx.sh(f"test -e {p}").returncode != 0:
        return CheckOutcome(False, _msg(spec, "The symbolic link is broken (its target does not exist)."))
    return CheckOutcome(True, values={"target": target})


@check("hardlink", ("path", "other"))
def hardlink(ctx, spec):
    """Two paths are hard links to the same inode."""
    a, b = ctx.q(spec["path"]), ctx.q(spec["other"])
    r = ctx.sh(f"test -f {a} && ! test -L {a} && test -f {b} && [ \"$(stat -c %d:%i {a})\" = \"$(stat -c %d:%i {b})\" ]")
    if r.ok:
        return CheckOutcome(True)
    if ctx.sh(f"test -L {a}").ok:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} is a symbolic link, not a hard link."))
    return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} is not a hard link to {ctx.path(spec['other'])} "
                                          "(they do not share an inode)."))


@check("file_contains", ("path",))
def file_contains(ctx, spec):
    """The file contains `text` (substring), or every regex in `regex`/`lines`."""
    content = ctx.read(spec["path"])
    if content is None:
        return CheckOutcome(False, _msg(spec, f"Cannot read {ctx.path(spec['path'])} - does it exist?"))
    flags = re.I if spec.get("ignore_case") else 0
    hay = content.lower() if spec.get("ignore_case") else content
    texts = spec.get("text")
    texts = [texts] if isinstance(texts, str) else (texts or [])
    for t in texts:
        if (t.lower() if spec.get("ignore_case") else t) not in hay:
            return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} does not contain '{t}'."), detail=content[:500])
    regexes = spec.get("regex")
    regexes = [regexes] if isinstance(regexes, str) else (regexes or [])
    for rx in regexes:
        if not re.search(rx, content, flags | re.M):
            return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} does not contain the expected content."),
                                detail=content[:500])
    return CheckOutcome(True)


@check("file_not_contains", ("path",))
def file_not_contains(ctx, spec):
    """The file does not contain `text` or match `regex`."""
    content = ctx.read(spec["path"]) or ""
    if "text" in spec and spec["text"] in content:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} still contains '{spec['text']}'."))
    if "regex" in spec and re.search(spec["regex"], content, re.M):
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} still contains unwanted content."))
    return CheckOutcome(True)


@check("file_equals", ("path",))
def file_equals(ctx, spec):
    """The file content equals `content` (trailing whitespace ignored)."""
    content = ctx.read(spec["path"])
    if content is None:
        return CheckOutcome(False, _msg(spec, f"Cannot read {ctx.path(spec['path'])} - does it exist?"))
    ok = _norm(content, spec) == _norm(str(spec.get("content", "")), spec)
    return CheckOutcome(ok, _msg(spec, f"The content of {ctx.path(spec['path'])} is not what was asked for."),
                        detail=content[:500])


@check("file_matches_command", ("path", "command"))
def file_matches_command(ctx, spec):
    """The file content equals the output of `command` run in the lab (computed live)."""
    content = ctx.read(spec["path"])
    if content is None:
        return CheckOutcome(False, _msg(spec, f"Cannot read {ctx.path(spec['path'])} - does it exist?"))
    r = ctx.sh(spec["command"].replace("~/", ctx.home + "/"), user=spec.get("user", "root"))
    ok = _norm(content, spec) == _norm(r.stdout, spec)
    return CheckOutcome(ok, _msg(spec, f"The content of {ctx.path(spec['path'])} is not the expected result."),
                        detail=content[:500])


@check("file_lines", ("path",))
def file_lines(ctx, spec):
    """The file has exactly `count` lines (or at least `min` / at most `max`)."""
    r = ctx.sh(f"wc -l < {ctx.q(spec['path'])}")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"Cannot read {ctx.path(spec['path'])}."))
    n = int(r.stdout.strip() or 0)
    ok = ("count" not in spec or n == spec["count"]) and n >= spec.get("min", 0) and n <= spec.get("max", 10**9)
    return CheckOutcome(ok, _msg(spec, f"{ctx.path(spec['path'])} has {n} lines."), detail=str(n))


@check("mode", ("path",))
def mode(ctx, spec):
    """Permission bits equal `mode` (octal, e.g. '750'), or include `has` / exclude `lacks` (e.g. 'u+x')."""
    r = ctx.sh(f"stat -c %a {ctx.q(spec['path'])}")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} does not exist."))
    actual = int(r.stdout.strip(), 8)
    if "mode" in spec:
        want = int(str(spec["mode"]), 8)
        if actual != want:
            return CheckOutcome(False, _msg(spec, f"The permissions of {ctx.path(spec['path'])} are "
                                                  f"{actual:o} ({_symbolic(actual)}); expected {want:o} ({_symbolic(want)})."),
                                detail=f"{actual:o}", values={"actual": f"{actual:o}"})
    for key, should in (("has", True), ("lacks", False)):
        for item in (spec.get(key) or "").split(","):
            item = item.strip()
            if not item:
                continue
            bits = _bits(item)
            present = (actual & bits) == bits if should else (actual & bits) == 0
            if not present:
                verb = "should have" if should else "should not have"
                return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} {verb} permission {item} "
                                                      f"(current: {actual:o} {_symbolic(actual)})."),
                                    values={"actual": f"{actual:o}"})
    return CheckOutcome(True, values={"actual": f"{actual:o}"})


def _bits(item: str) -> int:
    who, _, perms = item.partition("+")
    shift = {"u": 6, "g": 3, "o": 0}
    val = 0
    special = {"s": {"u": 0o4000, "g": 0o2000}, "t": {"o": 0o1000}}
    for w in who or "ugo":
        if w == "a":
            for ww in "ugo":
                val |= _bits(f"{ww}+{perms}")
            continue
        for p in perms:
            if p in "rwx":
                val |= {"r": 4, "w": 2, "x": 1}[p] << shift[w]
            elif p in special and w in special[p]:
                val |= special[p][w]
    return val


def _symbolic(mode_bits: int) -> str:
    out = ""
    for shift in (6, 3, 0):
        v = (mode_bits >> shift) & 7
        out += ("r" if v & 4 else "-") + ("w" if v & 2 else "-") + ("x" if v & 1 else "-")
    return out


@check("owner", ("path",))
def owner(ctx, spec):
    """The file is owned by `user` and/or group `group`."""
    r = ctx.sh(f"stat -c '%U %G' {ctx.q(spec['path'])}")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} does not exist."))
    u, g = r.stdout.split()
    if "user" in spec and u != spec["user"]:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} is owned by user '{u}', not '{spec['user']}'."),
                            values={"actual": u})
    if "group" in spec and g != spec["group"]:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['path'])} belongs to group '{g}', not '{spec['group']}'."),
                            values={"actual": g})
    return CheckOutcome(True)


@check("acl", ("path", "entry"))
def acl(ctx, spec):
    """`getfacl` shows the ACL entry (e.g. 'user:bob:rw-'), optionally default:."""
    r = ctx.sh(f"getfacl -cp {ctx.q(spec['path'])} 2>/dev/null")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"Cannot read the ACL of {ctx.path(spec['path'])}."))
    lines = [l.split("#")[0].strip() for l in r.stdout.splitlines()]
    ok = spec["entry"] in lines
    return CheckOutcome(ok, _msg(spec, f"The ACL of {ctx.path(spec['path'])} has no entry '{spec['entry']}'."),
                        detail=r.stdout)


@check("capability", ("path", "contains"))
def capability(ctx, spec):
    """`getcap` output for the file contains the given capability text."""
    r = ctx.sh(f"getcap {ctx.q(spec['path'])}")
    ok = spec["contains"] in r.stdout
    return CheckOutcome(ok, _msg(spec, f"{ctx.path(spec['path'])} does not have the capability {spec['contains']}."),
                        detail=r.stdout.strip())


# --------------------------------------------------------------------------- users & groups
@check("user_exists", ("name",))
def user_exists(ctx, spec):
    """A user account exists, optionally with `shell`, `home`, `uid`, `comment`."""
    r = ctx.sh(f"getent passwd {shlex.quote(spec['name'])}")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"There is no user account called '{spec['name']}'."))
    f = r.stdout.strip().split(":")
    for key, idx in (("uid", 2), ("comment", 4), ("home", 5), ("shell", 6)):
        if key in spec and str(spec[key]) != f[idx]:
            return CheckOutcome(False, _msg(spec, f"User '{spec['name']}' exists but its {key} is '{f[idx]}', "
                                                  f"expected '{spec[key]}'."))
    if spec.get("home_exists") and not ctx.sh(f"test -d {shlex.quote(f[5])}").ok:
        return CheckOutcome(False, _msg(spec, f"User '{spec['name']}' has no home directory on disk ({f[5]})."))
    return CheckOutcome(True)


@check("user_absent", ("name",))
def user_absent(ctx, spec):
    """No user account with this name exists."""
    r = ctx.sh(f"getent passwd {shlex.quote(spec['name'])}")
    return CheckOutcome(not r.ok, _msg(spec, f"The user '{spec['name']}' still exists."))


@check("group_exists", ("name",))
def group_exists(ctx, spec):
    """A group exists (optionally with `gid`)."""
    r = ctx.sh(f"getent group {shlex.quote(spec['name'])}")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"There is no group called '{spec['name']}'."))
    if "gid" in spec and r.stdout.split(":")[2] != str(spec["gid"]):
        return CheckOutcome(False, _msg(spec, f"Group '{spec['name']}' has the wrong GID."))
    return CheckOutcome(True)


@check("user_in_group", ("user", "group"))
def user_in_group(ctx, spec):
    """The user is a member of the group (primary or supplementary)."""
    r = ctx.sh(f"id -nG {shlex.quote(spec['user'])}")
    if not r.ok:
        return CheckOutcome(False, _msg(spec, f"The user '{spec['user']}' does not exist."))
    ok = spec["group"] in r.stdout.split()
    return CheckOutcome(ok, _msg(spec, f"'{spec['user']}' is not a member of '{spec['group']}' "
                                       f"(groups: {r.stdout.strip()})."))


@check("user_locked", ("name",))
def user_locked(ctx, spec):
    """The user's password is locked (passwd -S reports L)."""
    r = ctx.sh(f"passwd -S {shlex.quote(spec['name'])}")
    ok = r.ok and r.stdout.split()[1:2] == ["L"]
    want = spec.get("locked", True)
    return CheckOutcome(ok == want, _msg(spec, f"The account '{spec['name']}' is {'not ' if want else ''}locked."))


# --------------------------------------------------------------------------- processes & services
@check("process_running", ("pattern",))
def process_running(ctx, spec):
    """A process whose command line matches `pattern` is running (optionally as `user`)."""
    u = f"-u {shlex.quote(spec['user'])} " if "user" in spec else ""
    r = ctx.sh(f"pgrep {u}-f -- {shlex.quote(spec['pattern'])} | grep -vx \"$$\"")
    return CheckOutcome(r.ok and bool(r.stdout.strip()),
                        _msg(spec, f"No running process matches '{spec['pattern']}'."))


@check("process_absent", ("pattern",))
def process_absent(ctx, spec):
    """No process matching `pattern` is running."""
    r = ctx.sh(f"pgrep -f -- {shlex.quote(spec['pattern'])} | grep -vx \"$$\"")
    return CheckOutcome(not r.stdout.strip(), _msg(spec, f"A process matching '{spec['pattern']}' is still running."))


@check("process_nice", ("pattern", "nice"))
def process_nice(ctx, spec):
    """The (first) process matching `pattern` has niceness `nice` (or >= `min`)."""
    r = ctx.sh(f"ps -o ni= -p $(pgrep -f -- {shlex.quote(spec['pattern'])} | grep -vx \"$$\" | head -1)")
    if not r.ok or not r.stdout.strip():
        return CheckOutcome(False, _msg(spec, f"No process matching '{spec['pattern']}' is running."))
    ni = int(r.stdout.split()[0])
    ok = ni == int(spec["nice"])
    return CheckOutcome(ok, _msg(spec, f"The process has nice value {ni}, expected {spec['nice']}."), detail=str(ni))


@check("service_active", ("name",))
def service_active(ctx, spec):
    """systemd reports the unit as active (or `state` if given)."""
    want = spec.get("state", "active")
    r = ctx.sh(f"systemctl is-active {shlex.quote(spec['name'])}")
    state = r.stdout.strip()
    return CheckOutcome(state == want, _msg(spec, f"The service {spec['name']} is '{state}', expected '{want}'."),
                        detail=state)


@check("service_enabled", ("name",))
def service_enabled(ctx, spec):
    """systemd reports the unit as enabled (or `state`, e.g. 'disabled', 'masked')."""
    want = spec.get("state", "enabled")
    r = ctx.sh(f"systemctl is-enabled {shlex.quote(spec['name'])}")
    state = r.stdout.strip()
    return CheckOutcome(state == want, _msg(spec, f"The service {spec['name']} is '{state}', expected '{want}'."),
                        detail=state)


@check("port_listening", ("port",))
def port_listening(ctx, spec):
    """Something is listening on TCP `port`."""
    r = ctx.sh(f"ss -Hltn 'sport = :{int(spec['port'])}'")
    return CheckOutcome(bool(r.stdout.strip()), _msg(spec, f"Nothing is listening on TCP port {spec['port']}."))


# --------------------------------------------------------------------------- packages, cron, mounts
@check("package_installed", ("name",))
def package_installed(ctx, spec):
    """The Debian package is installed (`installed: false` to require removal)."""
    r = ctx.sh(f"dpkg-query -W -f='${{db:Status-Status}}' {shlex.quote(spec['name'])} 2>/dev/null")
    installed = r.stdout.strip() == "installed"
    want = spec.get("installed", True)
    return CheckOutcome(installed == want, _msg(spec, f"The package {spec['name']} is "
                                                      f"{'not ' if want else 'still '}installed."))


@check("crontab_contains", ("user", "regex"))
def crontab_contains(ctx, spec):
    """The user's crontab has a line matching `regex`."""
    r = ctx.sh(f"crontab -l -u {shlex.quote(spec['user'])} 2>/dev/null")
    lines = [l for l in r.stdout.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    ok = any(re.search(spec["regex"], l) for l in lines)
    return CheckOutcome(ok, _msg(spec, f"No crontab entry for {spec['user']} matches what was asked."),
                        detail="\n".join(lines))


@check("mounted", ("target",))
def mounted(ctx, spec):
    """A filesystem is mounted at `target` (optionally of `fstype`, with `options`)."""
    r = ctx.sh(f"findmnt -n -o FSTYPE,OPTIONS --mountpoint {ctx.q(spec['target'])}")
    if not r.ok or not r.stdout.strip():
        return CheckOutcome(False, _msg(spec, f"Nothing is mounted on {ctx.path(spec['target'])}."))
    fstype, opts = (r.stdout.split() + [""])[:2]
    if "fstype" in spec and fstype != spec["fstype"]:
        return CheckOutcome(False, _msg(spec, f"{ctx.path(spec['target'])} is mounted as {fstype}, not {spec['fstype']}."))
    for o in spec.get("options", []):
        if o not in opts.split(","):
            return CheckOutcome(False, _msg(spec, f"The mount is missing the option {o}."))
    return CheckOutcome(True)


@check("nft_ruleset_contains", ("regex",))
def nft_ruleset_contains(ctx, spec):
    """`nft list ruleset` contains a match for `regex`."""
    r = ctx.sh("nft list ruleset 2>/dev/null")
    ok = bool(re.search(spec["regex"], r.stdout, re.M))
    return CheckOutcome(ok, _msg(spec, "The firewall rules do not contain what was asked for."), detail=r.stdout[:800])


@check("journal_contains", ("regex",))
def journal_contains(ctx, spec):
    """The systemd journal (optionally for `unit` / `tag`) contains a line matching `regex`."""
    sel = ""
    if "unit" in spec:
        sel += f" -u {shlex.quote(spec['unit'])}"
    if "tag" in spec:
        sel += f" -t {shlex.quote(spec['tag'])}"
    r = ctx.sh(f"journalctl --no-pager -q -o cat{sel} | tail -n 2000")
    ok = bool(re.search(spec["regex"], r.stdout, re.M))
    return CheckOutcome(ok, _msg(spec, "The expected message was not found in the system journal."))


# --------------------------------------------------------------------------- commands & scripts
def _compare_output(text: str, spec: dict, prefix: str) -> tuple[bool, str]:
    if f"{prefix}equals" in spec and _norm(text, spec) != _norm(str(spec[f"{prefix}equals"]), spec):
        return False, f"output was:\n{text.strip()[:400]}"
    if f"{prefix}contains" in spec:
        items = spec[f"{prefix}contains"]
        for item in [items] if isinstance(items, str) else items:
            if str(item) not in text:
                return False, f"output does not contain '{item}'"
    if f"{prefix}regex" in spec:
        rx = spec[f"{prefix}regex"]
        for r in [rx] if isinstance(rx, str) else rx:
            if not re.search(r, text, re.M):
                return False, "output does not match what was expected"
    if f"{prefix}not_contains" in spec and str(spec[f"{prefix}not_contains"]) in text:
        return False, f"output contains '{spec[prefix + 'not_contains']}'"
    return True, ""


@check("command", ("run",))
def command(ctx, spec):
    """Run a verification command in the lab and test its exit status and/or output."""
    r = ctx.sh(spec["run"], user=spec.get("user", "root"), timeout=spec.get("timeout", 30))
    if "exit_code" in spec and r.returncode != int(spec["exit_code"]):
        return CheckOutcome(False, _msg(spec, f"The verification command exited with {r.returncode}."),
                            detail=(r.stdout + r.stderr)[:500])
    ok, why = _compare_output(r.stdout, spec, "stdout_")
    if not ok:
        return CheckOutcome(False, _msg(spec, f"Verification failed: {why}."), detail=r.stdout[:500])
    return CheckOutcome(True, values={"output": r.stdout.strip()})


@check("script", ("path",))
def script(ctx, spec):
    """Execute the student's script (as the student) and test exit status/output."""
    p = ctx.path(spec["path"])
    if not ctx.sh(f"test -f {shlex.quote(p)}").ok:
        return CheckOutcome(False, _msg(spec, f"The script {p} does not exist."))
    if spec.get("executable", True) and not ctx.sh(f"test -x {shlex.quote(p)}").ok:
        return CheckOutcome(False, spec.get("fail_not_executable",
                                            f"{p} exists but is not executable. Use chmod +x to make it runnable."))
    args = " ".join(shlex.quote(str(a)) for a in spec.get("args", []))
    setup = spec.get("before", "")
    runner = shlex.quote(p) if spec.get("executable", True) else f"bash {shlex.quote(p)}"
    cmdline = f"cd {shlex.quote(ctx.home)}; {setup}\n{runner} {args}"
    r = ctx.lab.exec(cmdline, user=spec.get("user", ctx.user), timeout=spec.get("timeout", 20),
                     stdin=spec.get("stdin"))
    if "exit_code" in spec and r.returncode != int(spec["exit_code"]):
        return CheckOutcome(False, _msg(spec, f"The script exited with status {r.returncode}, "
                                              f"expected {spec['exit_code']}.") +
                            (f"\nError output: {r.stderr.strip()[:300]}" if r.stderr.strip() else ""),
                            detail=r.stdout[:500])
    ok, why = _compare_output(r.stdout, spec, "")
    if not ok:
        return CheckOutcome(False, _msg(spec, f"The script ran, but its {why}.") +
                            (f"\nError output: {r.stderr.strip()[:300]}" if r.stderr.strip() else ""),
                            detail=r.stdout[:500])
    return CheckOutcome(True)


@check("answer", ())
def answer(ctx, spec):
    """The student's typed answer equals `equals`, matches `regex`, or equals the output of `command`."""
    given = (ctx.answer or "").strip()
    if not given:
        return CheckOutcome(False, spec.get("fail_empty", "Type your answer in the answer box."))
    if "command" in spec:
        r = ctx.sh(spec["command"], user=spec.get("user", "root"))
        expected = r.stdout.strip()
        ok = _norm(given, spec) == _norm(expected, spec)
    elif "regex" in spec:
        ok = bool(re.fullmatch(spec["regex"], given, re.I if spec.get("ignore_case", True) else 0))
    else:
        ok = _norm(given, {**spec, "ignore_case": spec.get("ignore_case", True)}) == \
            _norm(str(spec.get("equals", "")), {**spec, "ignore_case": spec.get("ignore_case", True)})
    return CheckOutcome(ok, _msg(spec, f"'{given}' is not the correct answer."))


@check("env_var", ("name",))
def env_var(ctx, spec):
    """A new interactive login shell of the student has variable `name` (set to `value` if given)."""
    name = spec["name"]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return CheckOutcome(False, "invalid variable name in exercise definition")
    probe = f'printf "%s:%s" "${{{name}+set}}" "${{{name}}}"'
    r = ctx.lab.exec(f"bash -lic {shlex.quote(probe)} 2>/dev/null </dev/null", user=ctx.user, timeout=20)
    flag, _, value = r.stdout.partition(":")
    if flag != "set":
        return CheckOutcome(False, _msg(spec, f"A new shell does not have the variable {name}. "
                                              "Did you add it to ~/.bashrc (or ~/.profile)?"))
    if "value" in spec and value != str(spec["value"]):
        return CheckOutcome(False, _msg(spec, f"{name} is '{value}', expected '{spec['value']}'."))
    if spec.get("exported") and not ctx.lab.exec(
            f"bash -lic env 2>/dev/null </dev/null | grep -q '^{name}='", user=ctx.user, timeout=20).ok:
        return CheckOutcome(False, _msg(spec, f"{name} is set but not exported, so programs will not see it."))
    return CheckOutcome(True)


# --------------------------------------------------------------------------- combinators
def _run_sub(ctx, sub: dict) -> CheckOutcome:
    return run_check(ctx, sub)


@check("all_of", ())
def all_of(ctx, spec):
    """All sub-checks pass."""
    for sub in spec.get("checks", []):
        o = _run_sub(ctx, sub)
        if not o.passed:
            return CheckOutcome(False, spec.get("fail", o.message))
    return CheckOutcome(True)


@check("any_of", ())
def any_of(ctx, spec):
    """At least one sub-check passes (alternative acceptable outcomes)."""
    msgs = []
    for sub in spec.get("checks", []):
        o = _run_sub(ctx, sub)
        if o.passed:
            return CheckOutcome(True)
        msgs.append(o.message)
    return CheckOutcome(False, spec.get("fail", msgs[0] if msgs else "No acceptable outcome found."))


@check("not", ())
def not_(ctx, spec):
    """The sub-check fails."""
    o = _run_sub(ctx, spec["check"])
    return CheckOutcome(not o.passed, spec.get("fail", "An unwanted condition is present."))


# --------------------------------------------------------------------------- diagnostics only
@check("find", ("name",), registry=DIAGNOSTICS)
def find(ctx, spec):
    """Search the lab for something called `name` (used to explain *where* a mistake went)."""
    roots = " ".join(ctx.q(r) for r in spec.get("under", ["/home", "/tmp", "/root", "/var/tmp", "/opt", "/srv"]))
    kind = {"d": "-type d", "f": "-type f", "l": "-type l"}.get(spec.get("kind", ""), "")
    exclude = [ctx.path(e) for e in spec.get("exclude", [])]
    r = ctx.sh(f"find {roots} -xdev {kind} -name {shlex.quote(spec['name'])} 2>/dev/null | head -20")
    found = [p for p in r.stdout.splitlines() if p and p not in exclude]
    return CheckOutcome(bool(found), values={"found": found[0] if found else "", "all": ", ".join(found)})


@check("history_matches", ("regex",), registry=DIAGNOSTICS)
def history_matches(ctx, spec):
    """A command typed during this exercise matches `regex` (diagnostic hints only, never marking)."""
    for cmd in getattr(ctx, "commands", []):
        m = re.search(spec["regex"], cmd)
        if m:
            return CheckOutcome(True, values={"command": cmd, **m.groupdict()})
    return CheckOutcome(False)


# --------------------------------------------------------------------------- dispatch
def run_check(ctx: CheckContext, spec: dict) -> CheckOutcome:
    t = spec.get("type")
    d = CHECKS.get(t) or DIAGNOSTICS.get(t)
    if not d:
        raise LabError(f"unknown check type {t!r}")
    return d.func(ctx, spec)


def load_plugins(dirs: list[Path]) -> list[str]:
    """Import extra check modules.  Returns the names of loaded plugin files."""
    loaded = []
    for d in dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(f"linux_tutor_plugin_{path.stem}", path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    loaded.append(path.name)
            except Exception:   # a broken plugin must not stop the tutor
                log.exception("failed to load assessment plugin %s", path)
    return loaded

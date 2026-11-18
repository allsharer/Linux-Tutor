"""Integration tests against a real, isolated Podman laboratory.

Most importantly: they prove that DIFFERENT valid commands achieving the same outcome
receive the SAME (correct) mark, and that wrong or partial work is not rewarded.

Run all curriculum tasks with:  LINUX_TUTOR_FULL_LAB_TESTS=1 python3 -m pytest tests/test_lab.py
"""
import os

import pytest

from linux_tutor import paths
from linux_tutor.assessment.engine import AssessmentEngine, Outcome
from linux_tutor.curriculum.loader import load_curriculum
from tests.lab_harness import check_task, iter_tasks

pytestmark = pytest.mark.lab


@pytest.fixture(scope="module")
def cur():
    return load_curriculum(paths.curriculum_dir())


@pytest.fixture(scope="module")
def engine(lab):
    return AssessmentEngine(lab)


def run(lab, cmd):
    return lab.exec("cd ~\n" + cmd, user="student", timeout=60)


# --------------------------------------------------------------- isolation
def test_lab_is_isolated(lab):
    r = lab.exec("ip -o link | awk -F': ' '{print $2}' | sort | tr '\\n' ' '; echo; "
                 "cat /etc/lab-netmode; hostname; id -u; stat -c %U /home/student; "
                 "ls /home; test -e /home/ubuntu && echo HOSTHOME || echo nohosthome")
    out = r.stdout
    assert out.splitlines()[0].strip() == "lo", "network must be disabled (loopback only)"
    assert "offline" in out
    assert "linuxlab" in out
    assert "nohosthome" in out, "the host's home directory must not be visible"


def test_no_host_network(lab):
    r = lab.exec("curl -s -m 3 -o /dev/null -w '%{http_code}' http://1.1.1.1/ ; echo; "
                 "getent hosts archive.ubuntu.com || echo NORESOLVE")
    assert r.stdout.startswith("000")
    assert "NORESOLVE" in r.stdout


def test_root_in_lab_is_not_host_root(lab):
    # The kernel refuses host-global operations even to the lab's root user.
    r = lab.exec("sysctl -w vm.swappiness=1 2>&1; date -s '2001-01-01' 2>&1 | tail -1; "
                 "mount -t proc none /mnt 2>&1 | tail -1; true")
    assert "denied" in r.stdout.lower() or "not permitted" in r.stdout.lower()


def test_pids_limit_stops_fork_bombs(lab):
    r = lab.exec("cat /sys/fs/cgroup/pids.max 2>/dev/null || echo none")
    assert r.stdout.strip() not in ("max", "none"), "a pids limit must be applied to the lab"


# --------------------------------------------------------------- outcome-based marking
def test_mkdir_projects_three_ways(cur, lab, engine):
    """The specification's own example: three different commands, one result, same mark."""
    ex = cur.lessons["b08-directories"].exercises[0]
    results = []
    for cmd in ['mkdir ~/projects', 'cd ~ && mkdir projects', 'mkdir "$HOME/projects"']:
        mark = engine.prepare(ex)
        run(lab, cmd)
        ev = engine.evaluate(ex, since=mark)
        results.append((ev.outcome.is_success, ev.score))
    assert results == [(True, 1.0)] * 3


def test_wrong_location_explained(cur, lab, engine):
    ex = cur.lessons["b08-directories"].exercises[0]
    mark = engine.prepare(ex)
    run(lab, "rm -rf /tmp/projects; cd /tmp && mkdir projects")
    ev = engine.evaluate(ex, since=mark)
    assert ev.outcome == Outcome.INCORRECT
    text = " ".join(ev.feedback)
    assert "/tmp/projects" in text and "home directory" in text
    lab.exec("rm -rf /tmp/projects")


def test_partial_and_side_effects(cur, lab, engine):
    ex = cur.lessons["b08-directories"].exercises[2]          # tidy-up
    mark = engine.prepare(ex)
    run(lab, "rmdir ~/old-empty")
    assert engine.evaluate(ex, since=mark).outcome == Outcome.PARTIAL
    mark = engine.prepare(ex)
    run(lab, "rm -rf ~/old-* ~/keep-me")
    assert engine.evaluate(ex, since=mark).outcome == Outcome.CORRECT_SIDE_EFFECTS


def test_permissions_symbolic_and_octal_equivalent(cur, lab, engine):
    ex = next(e for e in cur.lessons["b16-permissions"].exercises if e.id == "private-file")
    for cmd in ["chmod 600 ~/diary.txt", "chmod go= ~/diary.txt", "chmod u=rw,go-rwx ~/diary.txt"]:
        mark = engine.prepare(ex)
        run(lab, cmd)
        assert engine.evaluate(ex, since=mark).outcome.is_success, cmd


def test_command_typed_but_not_effective_is_not_rewarded(cur, lab, engine):
    ex = cur.lessons["b08-directories"].exercises[0]
    mark = engine.prepare(ex)
    run(lab, "echo mkdir ~/projects")                       # looks right, does nothing
    assert not engine.evaluate(ex, since=mark).outcome.is_success


SAMPLE = ["b09-files/shopping", "b10-copy-move/organise", "i03-chmod-chown-chgrp/team-dir",
          "i09-environment/export-editor", "a05-systemd/write-service", "a08-acls/grant-user"]


@pytest.mark.parametrize("task", SAMPLE)
def test_curriculum_sample(task, cur, lab, engine):
    tasks = dict(iter_tasks(cur))
    assert check_task(lab, engine, task, tasks[task]) == []


@pytest.mark.skipif(not os.environ.get("LINUX_TUTOR_FULL_LAB_TESTS"), reason="set LINUX_TUTOR_FULL_LAB_TESTS=1")
def test_every_practical_task(cur, lab, engine):
    failures = {}
    for name, ex in iter_tasks(cur):
        problems = check_task(lab, engine, name, ex)
        if problems:
            failures[name] = problems
    assert not failures, failures

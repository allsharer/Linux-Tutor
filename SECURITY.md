# Security and isolation model

Students execute arbitrary commands - including as root with `sudo` - so isolating those
commands from the host is a core requirement.  This document explains the design, the
safeguards, what was verified, and the **limitations**.  A rootless container is *not*
assumed to be a perfect security boundary.

## Threat model

* **Primary:** accidental damage by learners (`rm -rf /`, `chmod -R 777 /`, fork bombs,
  filling disks, breaking networking) must not affect the host or other users.
* **Secondary:** a curious or mischievous student trying to reach the host's files or
  network from the lab.
* **Out of scope:** a determined attacker with a kernel 0-day.  The lab shares the host
  kernel; a kernel privilege-escalation bug could escape any container.  For hostile
  multi-tenant use, run Linux Tutor inside a VM per student or implement a VM `LabBackend`.

## The isolation layers

| Layer | Setting | Effect |
|---|---|---|
| No host execution | The only host process started for the terminal is `podman exec ... bash` | Student commands run only inside the container |
| Rootless Podman | containers run under the student's own host UID | "root" in the lab is mapped to the host user's UID; lab users map to unprivileged sub-UIDs (`/etc/subuid`).  Root in the lab has **no** privileges on the host |
| User namespace | automatic in rootless mode | capabilities granted in the lab apply only to namespaces owned by that user namespace (its own network, mounts, UTS); host-wide operations are denied (verified: `sysctl vm.*`, setting the clock, mounting `/proc`) |
| Filesystem | **no host directories are mounted** | the lab sees only its own overlay filesystem; the host home directory is invisible (tested) |
| Network | `--network none` by default | only a loopback interface; no route to the host's LAN or the Internet (tested).  An instructor may enable `pasta`/`slirp4netns` in Settings |
| Resources | `--memory 1g --cpus 1.5 --pids-limit 1024` (configurable) | runaway programs and fork bombs are contained by cgroups v2 |
| Capabilities | Podman's default set **plus** `NET_ADMIN`, `NET_RAW`, `SYS_ADMIN`, `AUDIT_WRITE` | needed for firewall, interface, mount and namespace lessons; all are namespaced to the lab's own user namespace |
| Devices | only `/dev/fuse` is added | for `fuse2fs` (mounting disk images); no block devices, no loop devices |
| seccomp | Podman's default profile | blocks dangerous system calls (kexec, module loading, keyring abuse, ...) |
| Disposable | `Reset laboratory` deletes and recreates the container from the read-only image | any damage inside the lab is undone in seconds |
| Records | stored on the host, outside every container | resets or a compromised lab cannot alter grades directly |

`sudo` inside the lab requires the password `student`.  This is deliberate - it teaches
sudo realistically - and is not a security control (the lab's root is unprivileged on the
host anyway).

### Why some capabilities are added

* `NET_ADMIN`, `NET_RAW` - nftables firewall, `ip link/addr/route`, network namespaces,
  `ping`.  They affect only the lab's network namespace (which, by default, is not
  connected to anything).
* `SYS_ADMIN` - `mount -t tmpfs`, bind mounts, `fuse2fs`, `nsenter`, systemd features.  In
  rootless mode it is restricted to namespaces owned by the lab's user namespace; it cannot
  mount host block devices or change host mounts.  It nevertheless widens the kernel
  attack surface (more code paths reachable), which is the main residual risk.  Remove it
  from `lab.extra_caps` in `/etc/linux-tutor/config.json` for higher assurance - the
  mounting lessons will then not work.

### `/proc/sys`

Podman mounts `/proc/sys` read-only.  The lab image contains a boot unit
(`tutor-procsys.service`) that remounts it read-write *inside the lab's mount namespace*
so that network sysctls (`net.*`, which belong to the lab's network namespace) can be
practised.  Host-wide parameters (`kernel.*`, `vm.*`) remain unwritable because the
kernel checks capabilities against the initial user namespace (verified in tests).

## Additional safeguards

* The application never runs a student-supplied string on the host: checks and setup
  scripts come from the curriculum files and are executed *inside* the lab via
  `podman exec`.
* Curriculum and plugin files are trusted code (they define what runs in the lab and, for
  plugins, inside the application).  Install lessons and plugins only from trusted sources.
* The student database is created with mode 0600 and the data directory 0700.
* Run Linux Tutor as a normal user.  `linux-tutor-lab check` warns if Podman is not running
  rootless (for example when started as root), because the user-namespace protection
  described above would then be missing.

## Known limitations

1. **Shared kernel.**  Kernel vulnerabilities could allow escape.  Keep the host updated.
2. **AppArmor.**  Rootless Podman on Ubuntu runs containers with the AppArmor label
   `runc (unconfined)`/unconfined because unprivileged users cannot load AppArmor profiles.
   Host *path-based* AppArmor profiles may still attach to binaries inside the lab: on
   Ubuntu 26.04 the `nc.openbsd` profile confines `nc` in the lab and, for instance,
   prevents it from being signalled.  Exercises avoid depending on such programs.
3. **No hardware or kernel administration.**  Loading kernel modules, LVM (device-mapper),
   loop devices, GRUB and the initramfs belong to the host kernel and are not available.
   The corresponding lessons teach them with configuration files, real tool output and
   planning exercises, and say so explicitly.  A future VM backend can lift this.
4. **Resource limits need cgroup delegation.**  On hosts where the user's systemd session
   does not delegate the memory/cpu/pids controllers, Podman cannot apply limits; the tutor
   then starts the lab without them and shows a warning.  Ubuntu desktop sessions delegate
   them by default.
5. **Lab state is per user, not per student.**  Several profiles of the same Linux user
   each get their own containers, but they are all owned by that Linux user - a student who
   can run `podman` on the host could inspect another profile's lab.  For classroom use
   give each student their own Linux account.
6. **Disk usage.**  Each lab adds a writable overlay layer; a student filling it consumes
   host disk space in `~/.local/share/containers`.  Resetting the lab frees it.  Podman's
   `--storage-opt size=` requires XFS quotas and is not enabled by default.
7. **Answer integrity.**  Students control their lab, so a determined student could make a
   check pass by faking state (e.g. writing expected output into a file by hand where the
   check only reads that file).  Checks prefer verifying real behaviour (running scripts,
   querying services, testing access as another user) to reduce this, but the tutor is a
   learning tool, not a proctored certification system.

## Verification

`tests/test_lab.py` verifies on every test run that the lab has only a loopback
interface, cannot reach the Internet or resolve external names, cannot see the host's
home directory, cannot change host-wide kernel settings or the clock, and has a pids
limit.  See TESTING.md.

## Reporting

Please report security problems privately to the maintainers rather than in a public
issue.

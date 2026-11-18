# Backup and restore

## What to back up

| Data | Location | Important? |
|---|---|---|
| Student profiles, progress, scores, exam results, hint usage | `~/.local/share/linux-tutor/tutor.db` (SQLite) | **yes** |
| In-app backups | `~/.local/share/linux-tutor/backups/` | yes |
| User settings, window layout | `~/.config/linux-tutor/` | optional |
| Instructor configuration | `/etc/linux-tutor/config.json` | yes, for instructors |
| Laboratory contents (files a student created in the lab) | Podman containers | no - disposable by design |

The laboratory is deliberately **not** part of the academic record; it can be reset or
rebuilt at any time.

## From the application

* **File → Back up all student data...** writes a consistent copy of the whole database
  (all profiles) - safe while the application is running.  Default location:
  `~/.local/share/linux-tutor/backups/tutor-YYYYMMDD-HHMMSS.db`.
* **File → Restore student data from backup...** replaces the database with a backup.  The
  current database is first saved as `tutor.db.before-restore`.  The application closes;
  start it again.
* **File → Export my progress...** writes one profile as JSON - portable to another
  computer, importable from the profile chooser (**Import...**).
* **File → Export progress report (HTML)** - a human-readable report, e.g. for a teacher.

## From the command line

```bash
# consistent backup while the app may be running (sqlite3 package needed for the CLI tool)
sqlite3 ~/.local/share/linux-tutor/tutor.db ".backup '$HOME/tutor-backup.db'"

# or simply copy the file while Linux Tutor is closed
cp ~/.local/share/linux-tutor/tutor.db ~/tutor-backup.db

# whole user data incl. settings
tar czf linux-tutor-userdata.tgz -C ~ .local/share/linux-tutor .config/linux-tutor

# restore (Linux Tutor closed)
cp ~/tutor-backup.db ~/.local/share/linux-tutor/tutor.db
rm -f ~/.local/share/linux-tutor/tutor.db-wal ~/.local/share/linux-tutor/tutor.db-shm
```

## Moving a student to another computer

1. Old computer: File → Export my progress → `linux-tutor-alex.json`.
2. New computer: start Linux Tutor → profile chooser → **Import...** → choose the file.

## Laboratory data

Students who want to keep files they created in the lab can copy them out:

```bash
podman cp linux-tutor-lesson-1-alex:/home/student/myscript.sh ~/
```

Laboratory *image* backup (for offline reinstallation): `linux-tutor-lab export FILE.tar`.

# Uninstalling Linux Tutor

Removing the application **does not** delete student records unless you ask for it.

## Quick removal

From the release bundle directory:

```bash
./uninstall.sh                 # remove the application, keep records and laboratory
./uninstall.sh --lab           # also remove YOUR laboratory containers and image
./uninstall.sh --purge-data    # also delete YOUR profiles, scores and settings (asks first)
```

## Manual removal

```bash
# 1. laboratory (as each user who used Linux Tutor)
linux-tutor-lab remove-all                         # containers
podman rmi localhost/linux-tutor-lab:1             # image (~1.4 GB)

# 2. the application (once, as an administrator)
sudo apt purge linux-tutor                         # purge also removes /etc/linux-tutor

# 3. student data (as each user) - ONLY if you no longer need the records
#    Back them up first if in doubt (see BACKUP-RESTORE.md).
rm -rf ~/.local/share/linux-tutor ~/.config/linux-tutor ~/.local/state/linux-tutor ~/.cache/linux-tutor
```

Dependencies installed with the package (Podman, PyQt6, ...) are left in place because
other software may use them.  Remove unused ones with `sudo apt autoremove` if you wish.

## Reinstalling

Reinstalling (`./install.sh`) finds the existing records in `~/.local/share/linux-tutor`
and continues where the student left off.  This was verified as part of the deployment
test (see TESTING.md).

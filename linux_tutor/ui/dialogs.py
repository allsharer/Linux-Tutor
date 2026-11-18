"""Dialogs: profiles, settings, glossary, laboratory management, about."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .qt import Qt
from .qt import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QTextBrowser, QVBoxLayout)

from .. import APP_NAME, __version__, paths
from ..lab import LAB_IMAGE_VERSION, LabError
from ..progress.store import ProgressStore
from .workers import run_task


# ---------------------------------------------------------------------- profiles
class ProfileDialog(QDialog):
    """Choose, create, import or delete a student profile."""

    def __init__(self, store: ProgressStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.selected = None
        self.setWindowTitle(f"{APP_NAME} - choose your profile")
        self.resize(480, 420)
        lay = QVBoxLayout(self)
        title = QLabel(f"Welcome to {APP_NAME}")
        title.setProperty("role", "title")
        lay.addWidget(title)
        lay.addWidget(QLabel("Choose your student profile, or create a new one:"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda *_: self._accept())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        new = QPushButton("New profile...")
        new.clicked.connect(self._new)
        imp = QPushButton("Import...")
        imp.clicked.connect(self._import)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete)
        row.addWidget(new)
        row.addWidget(imp)
        row.addWidget(delete)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Start")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._reload()

    def _reload(self):
        self.list.clear()
        for p in self.store.profiles():
            last = datetime.fromtimestamp(p.last_active or p.created_at)
            item = QListWidgetItem(f"{p.display_name}  ({p.username})  -  last used {last:%d %b %Y}")
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _new(self):
        name, ok = QInputDialog.getText(self, "New profile", "Your name:")
        if not ok or not name.strip():
            return
        user, ok = QInputDialog.getText(self, "New profile", "Username (a short name, no spaces):",
                                        text=name.strip().split()[0].lower())
        if not ok or not user.strip():
            return
        try:
            p = self.store.create_profile(user.strip().replace(" ", "_"), name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "New profile", f"Could not create the profile: {exc}")
            return
        self._reload()
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == p.id:
                self.list.setCurrentRow(i)

    def _import(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Import profile", str(Path.home()), "Profile export (*.json)")
        if not fn:
            return
        try:
            data = json.loads(Path(fn).read_text())
            try:
                self.store.import_profile(data)
            except ValueError as exc:
                if "already exists" not in str(exc):
                    raise
                new, ok = QInputDialog.getText(self, "Import profile", f"{exc}. Import it under a new username:")
                if not ok or not new.strip():
                    return
                self.store.import_profile(data, rename=new.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Import profile", f"Import failed: {exc}")
        self._reload()

    def _delete(self):
        item = self.list.currentItem()
        if not item:
            return
        if QMessageBox.question(self, "Delete profile",
                                f"Permanently delete '{item.text().split('  -  ')[0]}' and all its records?\n"
                                "Consider exporting it first (File > Export progress).") == QMessageBox.StandardButton.Yes:
            self.store.delete_profile(item.data(Qt.ItemDataRole.UserRole))
            self._reload()

    def _accept(self):
        item = self.list.currentItem()
        if not item:
            QMessageBox.information(self, "Profile", "Create a profile first.")
            return
        self.selected = self.store.profile(item.data(Qt.ItemDataRole.UserRole))
        self.accept()


# ---------------------------------------------------------------------- settings
class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        lay = QFormLayout(self)
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(config.get("ui.theme"))
        self.font = QSpinBox()
        self.font.setRange(8, 24)
        self.font.setValue(int(config.get("ui.font_size")))
        self.tfont = QSpinBox()
        self.tfont.setRange(8, 28)
        self.tfont.setValue(int(config.get("ui.terminal_font_size")))
        self.passing = QSpinBox()
        self.passing.setRange(50, 100)
        self.passing.setSuffix(" %")
        self.passing.setValue(int(config.get("assessment.passing_score")))
        self.exam_passing = QSpinBox()
        self.exam_passing.setRange(50, 100)
        self.exam_passing.setSuffix(" %")
        self.exam_passing.setValue(int(config.get("assessment.exam_passing_score")))
        self.network = QComboBox()
        self.network.addItems(["none", "pasta", "slirp4netns"])
        self.network.setCurrentText(config.get("lab.network") or "none")
        self.network.setToolTip("'none' isolates the laboratory from all networks (recommended). "
                                "Other modes give it internet access. Takes effect after a lab reset.")
        self.memory = QLineEdit(str(config.get("lab.memory")))
        lay.addRow("Theme", self.theme)
        lay.addRow("Text size", self.font)
        lay.addRow("Terminal text size", self.tfont)
        lay.addRow("Lesson pass mark", self.passing)
        lay.addRow("Examination pass mark", self.exam_passing)
        lay.addRow("Laboratory network", self.network)
        lay.addRow("Laboratory memory limit", self.memory)
        for key, w in (("assessment.passing_score", self.passing), ("assessment.exam_passing_score", self.exam_passing),
                       ("lab.network", self.network), ("lab.memory", self.memory)):
            if key in config.locked:
                w.setEnabled(False)
                w.setToolTip("Locked by your instructor (/etc/linux-tutor/config.json)")
        note = QLabel("Pass marks are normally set by an instructor. Network and memory changes apply "
                      "when the laboratory is next reset.")
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        lay.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def _save(self):
        values = {"ui.theme": self.theme.currentText(), "ui.font_size": self.font.value(),
                  "ui.terminal_font_size": self.tfont.value(),
                  "assessment.passing_score": self.passing.value(),
                  "assessment.exam_passing_score": self.exam_passing.value(),
                  "lab.network": self.network.currentText(), "lab.memory": self.memory.text().strip() or "1g"}
        for k, v in values.items():
            if k not in self.config.locked and self.config.get(k) != v:
                self.config.set(k, v)
        self.accept()


# ---------------------------------------------------------------------- glossary
class GlossaryDialog(QDialog):
    def __init__(self, glossary: dict[str, str], term: str = "", parent=None):
        super().__init__(parent)
        self.glossary = glossary
        self.setWindowTitle("Glossary of Linux terms")
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(term)
        self.search.setPlaceholderText("Search terms...")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumWidth(220)
        self.list.currentTextChanged.connect(self._show)
        self.text = QTextBrowser()
        row.addWidget(self.list)
        row.addWidget(self.text, 1)
        lay.addLayout(row, 1)
        self._filter(term)

    def _filter(self, text: str):
        self.list.clear()
        t = text.lower().strip()
        for term in sorted(self.glossary, key=str.lower):
            if not t or t in term.lower() or t in self.glossary[term].lower():
                self.list.addItem(term)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _show(self, term: str):
        if term in self.glossary:
            self.text.setHtml(f"<h2>{html.escape(term)}</h2><p>{html.escape(self.glossary[term])}</p>")


# ---------------------------------------------------------------------- laboratory
class LabDialog(QDialog):
    """Laboratory status, image build/import/export and health check."""

    def __init__(self, config, lab, parent=None, auto_build: bool = False):
        super().__init__(parent)
        self.config, self.lab = config, lab
        self.setWindowTitle("Laboratory")
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        self.status = QLabel("Checking...")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.build_btn = QPushButton("Build image")
        self.build_btn.setToolTip("Build the laboratory image (needs internet access, several minutes)")
        self.build_btn.clicked.connect(self._build)
        self.import_btn = QPushButton("Import image...")
        self.import_btn.setToolTip("Load a laboratory image archive (offline installation)")
        self.import_btn.clicked.connect(self._import)
        self.export_btn = QPushButton("Export image...")
        self.export_btn.clicked.connect(self._export)
        self.health_btn = QPushButton("Test laboratory")
        self.health_btn.clicked.connect(self._health)
        for b in (self.build_btn, self.import_btn, self.export_btn, self.health_btn):
            row.addWidget(b)
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self._refresh()
        if auto_build:
            self._build()

    def _say(self, msg: str):
        self.log.appendPlainText(msg)

    def _busy(self, busy: bool):
        for b in (self.build_btn, self.import_btn, self.export_btn, self.health_btn):
            b.setEnabled(not busy)

    def _refresh(self):
        def show(st):
            lines = [f"<b>Container engine:</b> {'Podman ' + st.engine_version if st.engine_available else 'not available'}",
                     f"<b>Laboratory image:</b> {self.config.get('lab.image')}:{LAB_IMAGE_VERSION} - "
                     f"{'installed' if st.image_present else 'NOT installed'}",
                     f"<b>Your laboratory:</b> {'running' if st.running else 'created, stopped' if st.container_exists else 'not created yet'}",
                     f"<b>Network:</b> {self.config.get('lab.network')}"]
            if st.problems:
                lines.append("<b>Attention:</b> " + " ".join(html.escape(p) for p in st.problems))
            self.status.setText("<br>".join(lines))
        run_task(self.lab.status, on_done=show, on_error=lambda e: self.status.setText(f"Error: {e}"))

    def _build(self):
        from ..lab.podman import build_image
        self._busy(True)
        run_task(build_image, self.config, on_progress=self._say,
                 on_done=lambda _: (self._busy(False), self._refresh(), self._say("Done.")),
                 on_error=lambda e: (self._busy(False), self._say(f"FAILED: {e}")))

    def _import(self):
        from ..lab.podman import import_image
        fn, _ = QFileDialog.getOpenFileName(self, "Import laboratory image", str(Path.home()),
                                            "Image archives (*.tar *.tar.gz *.oci *.tar.xz);;All files (*)")
        if not fn:
            return
        self._busy(True)
        self._say(f"Importing {fn} ...")
        run_task(import_image, self.config, Path(fn),
                 on_done=lambda _: (self._busy(False), self._refresh(), self._say("Image imported.")),
                 on_error=lambda e: (self._busy(False), self._say(f"FAILED: {e}")))

    def _export(self):
        from ..lab.podman import export_image
        fn, _ = QFileDialog.getSaveFileName(self, "Export laboratory image",
                                            str(Path.home() / f"linux-tutor-lab-{LAB_IMAGE_VERSION}.tar"))
        if not fn:
            return
        self._busy(True)
        self._say(f"Exporting to {fn} ...")
        run_task(export_image, self.config, Path(fn),
                 on_done=lambda _: (self._busy(False), self._say("Exported.")),
                 on_error=lambda e: (self._busy(False), self._say(f"FAILED: {e}")))

    def _health(self):
        self._busy(True)
        self._say("Starting and testing the laboratory...")

        def work(progress=None):
            self.lab.ensure_running(progress)
            return self.lab.health_check()

        def done(problems):
            self._busy(False)
            self._refresh()
            self._say("Laboratory test passed - everything works." if not problems else
                      "Problems found:\n  " + "\n  ".join(problems))
        run_task(work, on_progress=self._say, on_done=done,
                 on_error=lambda e: (self._busy(False), self._say(f"FAILED: {e}")))


def about_text() -> str:
    return (f"<h2>{APP_NAME} {__version__}</h2>"
            "<p>An interactive, hands-on Linux learning and assessment environment, inspired by the "
            "DOS tutors of the 1980s and 1990s.</p>"
            "<p>Lessons and lectures, a real Bash shell in an isolated Podman laboratory, "
            "outcome-based marking, progressive hints, assessments and examinations.</p>"
            f"<p>Student data: {html.escape(str(paths.user_data_dir()))}<br>"
            f"Configuration: {html.escape(str(paths.config_dir()))}<br>"
            f"Curriculum: {html.escape(str(paths.curriculum_dir()))}</p>"
            "")

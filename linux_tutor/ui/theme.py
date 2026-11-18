"""Light and dark themes.  The dark theme nods to classic DOS tutors: deep blue and cyan."""
from __future__ import annotations

from .qt import QColor, QFont, QPalette
from .qt import QApplication

THEMES = {
    "dark": {
        "window": "#14202e", "base": "#0f1823", "alt": "#1a2838", "text": "#e3e8ee",
        "muted": "#93a4b8", "accent": "#4fc3f7", "accent2": "#ffd166", "button": "#1f3247",
        "border": "#2c4058", "highlight": "#1f6fa8", "good": "#6fdc8c", "warn": "#ffb454",
        "bad": "#ff6b6b", "note_bg": "#16324a", "tip_bg": "#163a2a", "warn_bg": "#4a2a16",
        "code_bg": "#0a1119", "code_fg": "#9fe3ff", "title_bg": "#0b3a66",
    },
    "light": {
        "window": "#f3f5f8", "base": "#ffffff", "alt": "#eef2f7", "text": "#1d2733",
        "muted": "#5d6b7a", "accent": "#0b63b6", "accent2": "#a35a00", "button": "#e4eaf1",
        "border": "#c7d1dc", "highlight": "#2f7fd1", "good": "#1b7f3b", "warn": "#9a5b00",
        "bad": "#b3261e", "note_bg": "#e6f0fb", "tip_bg": "#e7f6ec", "warn_bg": "#fdf0e3",
        "code_bg": "#f2f4f7", "code_fg": "#0b3a66", "title_bg": "#0b63b6",
    },
}


def colors(name: str) -> dict:
    return THEMES.get(name, THEMES["dark"])


def apply_theme(app: QApplication, name: str, font_size: int) -> None:
    c = colors(name)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(c["window"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(c["base"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(c["alt"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(c["button"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["highlight"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["alt"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["muted"]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    app.setPalette(pal)
    f = app.font()
    f.setPointSize(font_size)
    app.setFont(f)
    app.setStyleSheet(f"""
        QToolTip {{ border: 1px solid {c['border']}; padding: 4px; }}
        QSplitter::handle {{ background: {c['border']}; }}
        QSplitter::handle:horizontal {{ width: 4px; }}
        QSplitter::handle:vertical {{ height: 4px; }}
        QPushButton {{ padding: 5px 12px; border: 1px solid {c['border']}; border-radius: 4px;
                       background: {c['button']}; }}
        QPushButton:hover {{ border-color: {c['accent']}; }}
        QPushButton:disabled {{ color: {c['muted']}; }}
        QPushButton[primary="true"] {{ background: {c['highlight']}; color: white; border-color: {c['highlight']};
                                       font-weight: bold; }}
        QLabel[role="title"] {{ font-size: {font_size + 6}pt; font-weight: bold; color: {c['accent']}; }}
        QLabel[role="subtitle"] {{ font-size: {font_size + 2}pt; font-weight: bold; }}
        QLabel[role="muted"] {{ color: {c['muted']}; }}
        QLabel[role="banner"] {{ background: {c['title_bg']}; color: white; padding: 6px 10px;
                                 font-weight: bold; border-radius: 3px; }}
        QLabel[role="practice"] {{ background: {c['accent2']}; color: #1a1a1a; padding: 6px 10px;
                                   font-weight: bold; border-radius: 3px; }}
        QTreeWidget, QListWidget, QTextBrowser, QPlainTextEdit, QLineEdit {{
            border: 1px solid {c['border']}; border-radius: 3px; }}
        QTreeWidget::item {{ padding: 3px 0; }}
        QProgressBar {{ border: 1px solid {c['border']}; border-radius: 3px; text-align: center;
                        background: {c['base']}; }}
        QProgressBar::chunk {{ background: {c['highlight']}; }}
        QTabBar::tab {{ padding: 5px 12px; }}
        QGroupBox {{ border: 1px solid {c['border']}; border-radius: 4px; margin-top: 10px; padding-top: 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {c['accent']}; }}
    """)


def content_css(name: str, font_size: int) -> str:
    """CSS for rendered lecture HTML (QTextBrowser supports a CSS subset)."""
    c = colors(name)
    return f"""
    body {{ font-size: {font_size + 1}pt; color: {c['text']}; }}
    h1 {{ color: {c['accent']}; font-size: {font_size + 8}pt; }}
    h2 {{ color: {c['accent']}; font-size: {font_size + 4}pt; margin-top: 14px; }}
    h3 {{ color: {c['accent2']}; font-size: {font_size + 2}pt; }}
    code {{ font-family: monospace; color: {c['code_fg']}; background-color: {c['code_bg']}; }}
    pre {{ font-family: monospace; background-color: {c['code_bg']}; color: {c['code_fg']};
           padding: 8px; margin: 6px 0px; }}
    a {{ color: {c['accent']}; }}
    td {{ padding: 4px; }}
    th {{ padding: 4px; text-align: left; color: {c['accent2']}; }}
    .muted {{ color: {c['muted']}; }}
    .good {{ color: {c['good']}; font-weight: bold; }}
    .bad {{ color: {c['bad']}; font-weight: bold; }}
    .warn {{ color: {c['warn']}; font-weight: bold; }}
    """

"""A VT100/xterm terminal emulator widget (pyte + Qt painting).

Features: 256-colour and true-colour SGR, bold/italic/underline/reverse, cursor,
application-cursor keys, alternate screen (for less, vim, top, htop), scrollback
(mouse wheel / Shift+PgUp/PgDn), mouse selection with copy (Ctrl+Shift+C) and paste
(Ctrl+Shift+V, middle click), bracketed paste, window resizing.
"""
from __future__ import annotations

import pyte
from .qt import QClipboard, QEvent, QRect, QSocketNotifier, Qt, QTimer, Signal
from .qt import (QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QKeyEvent,
                           QPainter)
from .qt import QWidget

from ..terminal.pty_session import PtySession

PRIVATE = 5  # pyte stores DEC private modes shifted left by 5 bits
DECCKM = 1 << PRIVATE
BRACKETED_PASTE = 2004 << PRIVATE
ALT_SCREENS = {47 << PRIVATE, 1047 << PRIVATE, 1049 << PRIVATE}

ANSI_DARK = {
    "black": "#1c1c1c", "red": "#e05f5f", "green": "#87d75f", "brown": "#d7af5f",
    "blue": "#5f87d7", "magenta": "#af87d7", "cyan": "#5fafd7", "white": "#d0d0d0",
    "brightblack": "#6c6c6c", "brightred": "#ff8787", "brightgreen": "#afff87",
    "brightbrown": "#ffd787", "brightblue": "#87afff", "brightmagenta": "#d7afff",
    "brightcyan": "#87d7ff", "brightwhite": "#ffffff",
}
ANSI_LIGHT = {
    "black": "#000000", "red": "#b00000", "green": "#006e00", "brown": "#8a6200",
    "blue": "#0033aa", "magenta": "#8a008a", "cyan": "#007a8a", "white": "#9a9a9a",
    "brightblack": "#555555", "brightred": "#d70000", "brightgreen": "#008700",
    "brightbrown": "#af8700", "brightblue": "#005fd7", "brightmagenta": "#af00af",
    "brightcyan": "#0087af", "brightwhite": "#444444",
}


class _Screen(pyte.HistoryScreen):
    """pyte screen with process replies and a simple alternate screen buffer."""

    def __init__(self, cols, rows, reply):
        super().__init__(cols, rows, history=5000, ratio=0.5)
        self._reply = reply
        self._saved = None
        self.title = ""

    def write_process_input(self, data):
        self._reply(data.encode())

    def set_title(self, param):
        self.title = param

    def set_mode(self, *modes, **kwargs):
        if kwargs.get("private") and any((m << PRIVATE) in ALT_SCREENS for m in modes) and self._saved is None:
            self._saved = ({y: dict(line) for y, line in self.buffer.items()}, self.cursor.x, self.cursor.y)
            super().set_mode(*modes, **kwargs)
            self.erase_in_display(2)
            return
        super().set_mode(*modes, **kwargs)

    def reset_mode(self, *modes, **kwargs):
        super().reset_mode(*modes, **kwargs)
        if kwargs.get("private") and any((m << PRIVATE) in ALT_SCREENS for m in modes) and self._saved:
            buf, x, y = self._saved
            self._saved = None
            self.buffer.clear()
            for row, line in buf.items():
                if row < self.lines:
                    self.buffer[row].update(line)
            self.cursor.x, self.cursor.y = min(x, self.columns - 1), min(y, self.lines - 1)
            self.dirty.update(range(self.lines))


class TerminalWidget(QWidget):
    finished = Signal()
    titleChanged = Signal(str)

    def __init__(self, parent=None, font_family: str = "Monospace", font_size: int = 11, dark: bool = True):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.session: PtySession | None = None
        self.notifier: QSocketNotifier | None = None
        self.cols, self.rows = 80, 24
        self.screen = _Screen(self.cols, self.rows, self._send)
        self.stream = pyte.ByteStream(self.screen)
        self._sel_start = self._sel_end = None
        self._cursor_on = True
        self._blink = QTimer(self)
        self._blink.setInterval(600)
        self._blink.timeout.connect(self._toggle_cursor)
        self._blink.start()
        self.set_theme(dark)
        self.set_font(font_family, font_size)

    # ------------------------------------------------------------------ appearance
    def set_font(self, family: str, size: int) -> None:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont) if family in ("", "Monospace") else QFont(family)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        font.setPointSize(size)
        self.term_font = font
        self.bold_font = QFont(font)
        self.bold_font.setBold(True)
        fm = QFontMetricsF(font)
        self.cw = fm.horizontalAdvance("M")
        self.ch = fm.height()
        self.ascent = fm.ascent()
        self._resize_screen()
        self.update()

    def set_theme(self, dark: bool) -> None:
        self.dark = dark
        self.palette_map = ANSI_DARK if dark else ANSI_LIGHT
        self.fg_default = QColor("#d8d8d8" if dark else "#1a1a1a")
        self.bg_default = QColor("#101418" if dark else "#fbfbf7")
        self.update()

    def _color(self, name: str, default: QColor, bold: bool = False) -> QColor:
        if name == "default":
            return default
        if bold and not name.startswith("bright") and name in self.palette_map:
            name = "bright" + name
        if name in self.palette_map:
            return QColor(self.palette_map[name])
        if len(name) == 6:
            return QColor("#" + name)
        return default

    # ------------------------------------------------------------------ session
    def start(self, argv: list[str]) -> None:
        self.stop()
        self.screen.reset()
        self.session = PtySession(argv, self.cols, self.rows)
        self.notifier = QSocketNotifier(self.session.fd, QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._on_readable)

    def stop(self) -> None:
        if self.notifier:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.session:
            self.session.close()
            self.session = None

    def running(self) -> bool:
        return bool(self.session and self.session.alive())

    def feed_text(self, text: str) -> None:
        """Display a local message (not sent to the shell)."""
        self.stream.feed(text.replace("\n", "\r\n").encode())
        self.update()

    def _on_readable(self, *_):
        if not self.session:
            return
        data = self.session.read()
        if data is None:
            self.stop()
            self.feed_text("\n[session ended - press Enter or use Lab > New terminal to reconnect]\n")
            self.finished.emit()
            return
        if data:
            if self.screen.history.position < self.screen.history.size:
                self._scroll_to_bottom()
            self.stream.feed(data)
            if self.screen.title:
                self.titleChanged.emit(self.screen.title)
            self._cursor_on = True
            self.update()

    def _send(self, data: bytes) -> None:
        if self.session:
            self.session.write(data)

    def send_text(self, text: str, execute: bool = False) -> None:
        """Type text into the shell (used by 'Try it' buttons)."""
        data = text.encode()
        if BRACKETED_PASTE in self.screen.mode and "\n" in text:
            data = b"\x1b[200~" + data + b"\x1b[201~"
        self._send(data + (b"\r" if execute else b""))
        self.setFocus()

    # ------------------------------------------------------------------ geometry
    def _resize_screen(self) -> None:
        cols = max(20, int((self.width() - 8) // self.cw)) if self.cw else 80
        rows = max(5, int((self.height() - 8) // self.ch)) if self.ch else 24
        if (cols, rows) != (self.cols, self.rows):
            self.cols, self.rows = cols, rows
            self.screen.resize(rows, cols)
            if self.session:
                self.session.resize(cols, rows)

    def resizeEvent(self, ev):
        self._resize_screen()
        super().resizeEvent(ev)

    # ------------------------------------------------------------------ painting
    def _toggle_cursor(self):
        if self.hasFocus():
            self._cursor_on = not self._cursor_on
            self.update(self._cursor_rect())

    def _cursor_rect(self) -> QRect:
        c = self.screen.cursor
        return QRect(int(4 + c.x * self.cw), int(4 + c.y * self.ch), int(self.cw) + 2, int(self.ch) + 2)

    def _selected(self, x: int, y: int) -> bool:
        if self._sel_start is None or self._sel_end is None:
            return False
        a, b = sorted([self._sel_start, self._sel_end], key=lambda p: (p[1], p[0]))
        return (a[1], a[0]) <= (y, x) <= (b[1], b[0])

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self.bg_default)
        p.setFont(self.term_font)
        scr = self.screen
        sel_bg = QColor("#3a5f8a" if self.dark else "#b5d3f5")
        for y in range(scr.lines):
            line = scr.buffer[y]
            ty = 4 + y * self.ch
            x = 0
            while x < scr.columns:
                char = line[x]
                fg = self._color(char.fg, self.fg_default, char.bold)
                bg = self._color(char.bg, self.bg_default)
                if char.reverse:
                    fg, bg = bg, fg
                if self._selected(x, y):
                    bg = sel_bg
                # gather a run of cells with identical attributes
                run = [char.data]
                x2 = x + 1
                while x2 < scr.columns:
                    c2 = line[x2]
                    if (c2.fg, c2.bg, c2.bold, c2.italics, c2.underscore, c2.reverse) != \
                            (char.fg, char.bg, char.bold, char.italics, char.underscore, char.reverse) or \
                            self._selected(x2, y) != self._selected(x, y):
                        break
                    run.append(c2.data or "")
                    x2 += 1
                rect = QRect(int(4 + x * self.cw), int(ty), int((x2 - x) * self.cw + 1), int(self.ch) + 1)
                if bg != self.bg_default:
                    p.fillRect(rect, bg)
                text = "".join(run)
                if text.strip():
                    f = self.bold_font if char.bold else self.term_font
                    f.setItalic(bool(char.italics))
                    f.setUnderline(bool(char.underscore))
                    p.setFont(f)
                    p.setPen(fg)
                    # draw cell by cell to keep the grid exact for any font
                    for i, ch in enumerate(run):
                        if ch and ch != " ":
                            p.drawText(int(4 + (x + i) * self.cw), int(ty + self.ascent), ch)
                x = x2
        # cursor
        if not scr.cursor.hidden and self.screen.history.position >= self.screen.history.size:
            r = self._cursor_rect().adjusted(0, 0, -2, -2)
            cur_col = QColor("#f0c674" if self.dark else "#1f5fbf")
            if self.hasFocus() and self._cursor_on:
                p.fillRect(r, cur_col)
                ch = scr.buffer[scr.cursor.y][scr.cursor.x].data
                if ch.strip():
                    p.setPen(self.bg_default)
                    p.setFont(self.term_font)
                    p.drawText(r.x(), int(r.y() + self.ascent), ch)
            elif not self.hasFocus():
                p.setPen(cur_col)
                p.drawRect(r)
        p.end()

    # ------------------------------------------------------------------ keyboard
    def event(self, ev):
        # Keep Tab / Shift+Tab inside the terminal (tab completion) instead of moving focus.
        if ev.type() == QEvent.Type.KeyPress and ev.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.keyPressEvent(ev)
            return True
        return super().event(ev)

    def keyPressEvent(self, ev: QKeyEvent):
        key, mods, text = ev.key(), ev.modifiers(), ev.text()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        if ctrl and shift and key == Qt.Key.Key_C:
            self.copy_selection(); return
        if ctrl and shift and key == Qt.Key.Key_V:
            self.paste(); return
        if shift and key == Qt.Key.Key_PageUp:
            self.screen.prev_page(); self.update(); return
        if shift and key == Qt.Key.Key_PageDown:
            self.screen.next_page(); self.update(); return

        if not self.session:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.finished.emit()
            return

        app_cursor = DECCKM in self.screen.mode
        arrows = {Qt.Key.Key_Up: "A", Qt.Key.Key_Down: "B", Qt.Key.Key_Right: "C", Qt.Key.Key_Left: "D",
                  Qt.Key.Key_Home: "H", Qt.Key.Key_End: "F"}
        special = {
            Qt.Key.Key_Return: b"\r", Qt.Key.Key_Enter: b"\r", Qt.Key.Key_Backspace: b"\x7f",
            Qt.Key.Key_Tab: b"\t", Qt.Key.Key_Backtab: b"\x1b[Z", Qt.Key.Key_Escape: b"\x1b",
            Qt.Key.Key_Insert: b"\x1b[2~", Qt.Key.Key_Delete: b"\x1b[3~",
            Qt.Key.Key_PageUp: b"\x1b[5~", Qt.Key.Key_PageDown: b"\x1b[6~",
            Qt.Key.Key_F1: b"\x1bOP", Qt.Key.Key_F2: b"\x1bOQ", Qt.Key.Key_F3: b"\x1bOR", Qt.Key.Key_F4: b"\x1bOS",
            Qt.Key.Key_F5: b"\x1b[15~", Qt.Key.Key_F6: b"\x1b[17~", Qt.Key.Key_F7: b"\x1b[18~",
            Qt.Key.Key_F8: b"\x1b[19~", Qt.Key.Key_F9: b"\x1b[20~", Qt.Key.Key_F10: b"\x1b[21~",
            Qt.Key.Key_F11: b"\x1b[23~", Qt.Key.Key_F12: b"\x1b[24~",
        }
        data = b""
        if key in arrows:
            mod = 1 + (1 if shift else 0) + (2 if alt else 0) + (4 if ctrl else 0)
            if mod > 1:
                data = f"\x1b[1;{mod}{arrows[key]}".encode()
            else:
                data = (b"\x1bO" if app_cursor else b"\x1b[") + arrows[key].encode()
        elif key in special:
            data = special[key]
        elif ctrl and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            data = bytes([key - Qt.Key.Key_A + 1])
        elif ctrl and key in (Qt.Key.Key_BracketLeft, Qt.Key.Key_Backslash, Qt.Key.Key_BracketRight):
            data = bytes([{Qt.Key.Key_BracketLeft: 27, Qt.Key.Key_Backslash: 28, Qt.Key.Key_BracketRight: 29}[key]])
        elif ctrl and key == Qt.Key.Key_Space:
            data = b"\x00"
        elif text:
            data = text.encode()
        if data:
            if alt and key not in arrows:
                data = b"\x1b" + data
            self._scroll_to_bottom()
            self._sel_start = self._sel_end = None
            self._send(data)

    def inputMethodEvent(self, ev):
        if ev.commitString():
            self._send(ev.commitString().encode())

    def _scroll_to_bottom(self):
        while self.screen.history.position < self.screen.history.size:
            before = self.screen.history.position
            self.screen.next_page()
            if self.screen.history.position == before:
                break
        self.update()

    def wheelEvent(self, ev):
        if ev.angleDelta().y() > 0:
            self.screen.prev_page()
        else:
            self.screen.next_page()
        self.update()

    # ------------------------------------------------------------------ selection / clipboard
    def _cell_at(self, pos):
        x = int((pos.x() - 4) // self.cw)
        y = int((pos.y() - 4) // self.ch)
        return max(0, min(self.cols - 1, x)), max(0, min(self.rows - 1, y))

    def mousePressEvent(self, ev):
        self.setFocus()
        if ev.button() == Qt.MouseButton.LeftButton:
            self._sel_start = self._sel_end = self._cell_at(ev.position())
            self.update()
        elif ev.button() == Qt.MouseButton.MiddleButton:
            text = QGuiApplication.clipboard().text(QClipboard.Mode.Selection)
            if text:
                self.send_text(text)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.MouseButton.LeftButton and self._sel_start is not None:
            self._sel_end = self._cell_at(ev.position())
            self.update()

    def mouseReleaseEvent(self, ev):
        if self._sel_start == self._sel_end:
            self._sel_start = self._sel_end = None
        else:
            text = self.selected_text()
            cb = QGuiApplication.clipboard()
            if cb.supportsSelection():
                cb.setText(text, QClipboard.Mode.Selection)
        self.update()

    def selected_text(self) -> str:
        if self._sel_start is None or self._sel_end is None:
            return ""
        a, b = sorted([self._sel_start, self._sel_end], key=lambda p: (p[1], p[0]))
        lines = []
        for y in range(a[1], b[1] + 1):
            x0 = a[0] if y == a[1] else 0
            x1 = b[0] if y == b[1] else self.cols - 1
            row = self.screen.buffer[y]
            lines.append("".join(row[x].data for x in range(x0, x1 + 1)).rstrip())
        return "\n".join(lines)

    def copy_selection(self):
        text = self.selected_text()
        if text:
            QGuiApplication.clipboard().setText(text)

    def paste(self):
        text = QGuiApplication.clipboard().text()
        if text:
            self.send_text(text)

    def screen_text(self) -> str:
        return "\n".join(self.screen.display)

    def closeEvent(self, ev):
        self.stop()
        super().closeEvent(ev)

"""Visual theme editor tab (vendor theme-editor equivalent).

Canvas = 240x240 theme rendered 2x. Click selects, drag moves.
Property panel edits the selected widget. Emits send_requested(jpeg).
"""

import io
import json
import time
import uuid
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

import sensors
import theme as theme_mod

SCALE = 2
CANVAS = 240 * SCALE


def live_values() -> dict:
    import psutil
    s = sensors.snapshot()
    s["cpu_load"] = psutil.cpu_percent(interval=None)
    s["time_str"] = time.strftime("%H:%M")
    return s


WIDGET_TYPES = [
    ("CPU temp", "cpu_temp", 88),
    ("GPU temp", "gpu_temp", 26),
    ("CPU load", "cpu_load", 26),
    ("Clock", "time", 56),
    ("Text", "text", 28),
    ("Bar", "bar", 14),
]


class ThemeEditor(QWidget):
    send_requested = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.theme = theme_mod.default_theme()
        self.selected = None
        self._drag = None
        self._rects = []

        root = QHBoxLayout(self)

        left = QVBoxLayout()
        self.canvas = QLabel()
        self.canvas.setFixedSize(CANVAS, CANVAS)
        self.canvas.setStyleSheet("background: black; border-radius: 8px;")
        self.canvas.mousePressEvent = self._press
        self.canvas.mouseMoveEvent = self._move
        left.addWidget(self.canvas)
        add_row = QHBoxLayout()
        for label, wtype, size in WIDGET_TYPES:
            b = QPushButton("+" + label)
            b.clicked.connect(
                lambda _=False, t=wtype, s=size: self.add_widget(t, s))
            add_row.addWidget(b)
        left.addLayout(add_row)
        mon_row = QHBoxLayout()
        self.use_monitor = QCheckBox("Use theme for monitoring")
        mon_row.addWidget(self.use_monitor)
        mon_row.addStretch(1)
        left.addLayout(mon_row)
        root.addLayout(left, 1)

        props = QVBoxLayout()
        props.addWidget(QLabel("Properties"))
        self.p_text = QLineEdit()
        self.p_text.setPlaceholderText("text (Text widgets)")
        self.p_text.editingFinished.connect(self._apply_props)
        props.addWidget(self.p_text)
        for name, lo in (("X", 0), ("Y", 0), ("Size", 1), ("Width", 1)):
            row = QHBoxLayout()
            row.addWidget(QLabel(name + ":"))
            sb = QSpinBox()
            sb.setRange(lo, 240)
            sb.valueChanged.connect(self._apply_props)
            setattr(self, "p_" + name.lower(), sb)
            row.addWidget(sb)
            props.addLayout(row)
        self.p_color_btn = QPushButton("Color…")
        self.p_color_btn.clicked.connect(self._pick_color)
        props.addWidget(self.p_color_btn)
        self.p_color = [255, 255, 255]
        delete = QPushButton("Delete widget")
        delete.clicked.connect(self.delete_selected)
        props.addWidget(delete)
        bg_btn = QPushButton("Background image…")
        bg_btn.clicked.connect(self._pick_bg)
        props.addWidget(bg_btn)
        bg_clear = QPushButton("Background black")
        bg_clear.clicked.connect(self._clear_bg)
        props.addWidget(bg_clear)
        send = QPushButton("Send theme to display")
        send.setProperty("class", "primary")
        send.clicked.connect(
            lambda: self.send_requested.emit(
                theme_mod.to_jpeg(self.theme, live_values())))
        props.addWidget(send)
        row = QHBoxLayout()
        save = QPushButton("Save…")
        save.clicked.connect(self.save_theme)
        load = QPushButton("Load…")
        load.clicked.connect(self.load_theme)
        row.addWidget(save)
        row.addWidget(load)
        props.addLayout(row)
        props.addStretch(1)
        root.addLayout(props)

        self._refresh_timer = None
        from PySide6.QtCore import QTimer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.redraw)
        self._refresh_timer.start(1000)
        self.redraw()

    # ------------------------------------------------------------- editing
    def add_widget(self, wtype, size):
        self.theme["widgets"].append({
            "id": uuid.uuid4().hex[:8], "type": wtype, "x": 120, "y": 120,
            "size": size, "color": [255, 255, 255],
            "text": "Text" if wtype == "text" else "",
            "w": 200, "source": "cpu_temp",
        })
        self.selected = self.theme["widgets"][-1]["id"]
        self._sync_props()
        self.redraw()

    def _widget(self, wid):
        for wdg in self.theme["widgets"]:
            if wdg["id"] == wid:
                return wdg
        return None

    def set_theme(self, theme: dict):
        """Replace current theme (validated) — used at startup restore."""
        if not isinstance(theme.get("widgets"), list):
            raise ValueError("bad theme")
        self.theme = theme
        self.selected = None
        self._sync_props()
        self.redraw()

    def delete_selected(self):
        self.theme["widgets"] = [w for w in self.theme["widgets"]
                                 if w["id"] != self.selected]
        self.selected = None
        self.redraw()

    def _press(self, ev):
        x, y = ev.position().x() // SCALE, ev.position().y() // SCALE
        self.selected = None
        for wid, rx, ry, rw, rh in reversed(self._rects):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.selected = wid
                self._drag = (x - self._widget(wid)["x"],
                              y - self._widget(wid)["y"])
                break
        self._sync_props()
        self.redraw()

    def _move(self, ev):
        if self.selected is None or self._drag is None:
            return
        if not (ev.buttons() & Qt.LeftButton):
            self._drag = None
            return
        wdg = self._widget(self.selected)
        if wdg is None:
            return
        wdg["x"] = int(ev.position().x() // SCALE - self._drag[0])
        wdg["y"] = int(ev.position().y() // SCALE - self._drag[1])
        self._sync_props()
        self.redraw()

    def _sync_props(self):
        wdg = self._widget(self.selected)
        if wdg is None:
            return
        # Block valueChanged while syncing: otherwise programmatic setValue
        # would push partial state back through _apply_props.
        for sb in (self.p_x, self.p_y, self.p_size, self.p_width):
            sb.blockSignals(True)
        try:
            self.p_text.setText(wdg.get("text", ""))
            self.p_x.setValue(int(wdg.get("x", 0)))
            self.p_y.setValue(int(wdg.get("y", 0)))
            self.p_size.setValue(max(1, int(wdg.get("size", 28))))
            self.p_width.setValue(max(1, int(wdg.get("w", 200))))
        finally:
            for sb in (self.p_x, self.p_y, self.p_size, self.p_width):
                sb.blockSignals(False)
        self.p_color = list(wdg.get("color", [255, 255, 255]))

    def _apply_props(self):
        wdg = self._widget(self.selected)
        if wdg is None:
            return
        wdg["text"] = self.p_text.text()
        wdg["x"] = self.p_x.value()
        wdg["y"] = self.p_y.value()
        wdg["size"] = self.p_size.value()
        wdg["w"] = self.p_width.value()
        wdg["color"] = list(self.p_color)
        self.redraw()

    def _pick_color(self):
        wdg = self._widget(self.selected)
        start = QColor(*self.p_color)
        c = QColorDialog.getColor(start, self, "Widget color")
        if c.isValid():
            self.p_color = [c.red(), c.green(), c.blue()]
            if wdg is not None:
                wdg["color"] = list(self.p_color)
            self.redraw()

    def _pick_bg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Background", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.theme["background"] = {"type": "image", "path": path}
            self.redraw()

    def _clear_bg(self):
        self.theme["background"] = {"type": "color", "color": [0, 0, 0]}
        self.redraw()

    def save_theme(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save theme", "theme.json", "Theme (*.json)")
        if path:
            Path(path).write_text(json.dumps(self.theme, indent=1,
                                             ensure_ascii=False))

    def load_theme(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load theme", str(Path.home()), "Theme (*.json)")
        if path:
            try:
                self.theme = json.loads(Path(path).read_text())
                self.selected = None
                self.redraw()
            except (OSError, ValueError):
                pass

    # ------------------------------------------------------------- display
    def redraw(self):
        img, self._rects = theme_mod.render(self.theme, live_values())
        if self.selected:
            from PIL import ImageDraw
            d = ImageDraw.Draw(img)
            for wid, rx, ry, rw, rh in self._rects:
                if wid == self.selected:
                    d.rectangle([rx - 2, ry - 2, rx + rw + 2, ry + rh + 2],
                                outline=(255, 80, 64), width=2)
        big = img.resize((CANVAS, CANVAS), Image.NEAREST)
        buf = io.BytesIO()
        big.save(buf, "PNG")
        pix = QPixmap()
        pix.loadFromData(buf.getvalue())
        # img here is the composed (unrotated) frame = what the pump shows,
        # so display as-is (device bytes stay pre-rotated in to_jpeg).
        self.canvas.setPixmap(pix)

    def monitor_jpeg(self):
        return theme_mod.to_jpeg(self.theme, live_values())

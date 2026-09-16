#!/usr/bin/env python3
"""ID-COOLING FX240 LCD control GUI (Linux, PySide6, dark theme).

Tabs: Temperature (live monitoring) / Image (static) / GIF (animation) /
Settings (brightness, display on). Preview shows exactly what is sent:
240x240 JPEG frames over DRA (see docs/PROTOCOL.md).
"""

import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QPushButton, QSlider, QSpinBox, QSystemTrayIcon, QTabWidget,
    QVBoxLayout, QWidget,
)

import image_pipe
import sensors
from editor import ThemeEditor
from hotspotek import Pump

CONFIG = Path(__file__).parent / "config.json"
APP_FILE = Path(__file__).resolve()
AUTOSTART_FILE = (Path.home() / ".config" / "autostart" / "fx240-lcd.desktop")


def autostart_enabled() -> bool:
    return AUTOSTART_FILE.exists()


def set_autostart(on: bool):
    if on:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=FX240 LCD\n"
            "Comment=ID-COOLING FX240 pump display monitor\n"
            f"Exec=/usr/bin/python3 {APP_FILE}\n"
            f"Path={APP_FILE.parent}\n"
            "Terminal=false\n"
            "Categories=Utility;\n"
            "X-GNOME-Autostart-enabled=true\n")
    else:
        try:
            AUTOSTART_FILE.unlink()
        except OSError:
            pass

ACCENT = "#ff5040"
BG = "#141419"
PANEL = "#1e1e26"
BORDER = "#2e2e3a"
TEXT = "#e8e8ee"
DIM = "#9a9aa8"

QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font-size: 14px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px;
    background: {PANEL}; padding: 12px; }}
QTabBar::tab {{ background: transparent; color: {DIM}; padding: 8px 18px;
    margin-right: 4px; border-top-left-radius: 8px;
    border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ color: {TEXT}; background: {PANEL};
    border: 1px solid {BORDER}; border-bottom: none; }}
QPushButton {{ background: {BORDER}; border: none; border-radius: 8px;
    padding: 9px 16px; }}
QPushButton:hover {{ background: #3a3a4a; }}
QPushButton:checked {{ background: {ACCENT}; color: white; font-weight: bold; }}
QPushButton.primary {{ background: {ACCENT}; color: white; font-weight: bold; }}
QPushButton.primary:hover {{ background: #ff6a58; }}
QLabel.card {{ background: {BG}; border: 1px solid {BORDER};
    border-radius: 10px; padding: 12px; }}
QLabel.big {{ font-size: 30px; font-weight: bold; }}
QSlider::groove:horizontal {{ height: 6px; background: {BORDER};
    border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 18px; margin: -6px 0; border-radius: 9px;
    background: {ACCENT}; }}
QSpinBox {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 4px 8px; }}
QStatusBar {{ color: {DIM}; }}
"""


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {"brightness": 100, "interval": 2.0}


def device_present() -> bool:
    try:
        Pump().close()
        return True
    except Exception:  # noqa: BLE001 — missing device / permissions
        return False


def tray_icon() -> QPixmap:
    """64px icon: dark rounded square, red ring, white FX."""
    img = Image.new("RGBA", (64, 64), (20, 20, 25, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], outline=(255, 80, 64), width=6)
    d.text((32, 34), "FX", fill=(255, 255, 255), anchor="mm")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    pix = QPixmap()
    pix.loadFromData(buf.getvalue())
    return pix


class SendThread(QThread):
    """Serialize device access off the GUI thread."""
    done = Signal(str)
    preview = Signal(bytes)  # JPEG bytes just sent

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs  # ("frame", jpeg) | ("bright", v) | ("on",)

    def run(self):
        try:
            with Pump() as pump:
                for kind, payload in self.jobs:
                    if kind == "frame":
                        pump.send_frame(payload)
                        self.preview.emit(payload)
                    elif kind == "bright":
                        pump.set_brightness(payload)
                    elif kind == "on":
                        pump.display_on()
        except Exception as e:  # noqa: BLE001 — report to status bar
            self.done.emit(f"error: {e}")
        else:
            self.done.emit("sent ok")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowTitle("FX240 LCD")
        self.resize(620, 460)
        self.sender = None
        self.tray = None
        self.mon_timer = QTimer(self)
        self.mon_timer.timeout.connect(self.tick_monitor)
        self.tick_preview = QTimer(self)  # live sensor readout, no sending
        self.tick_preview.timeout.connect(self.refresh_temp_label)
        self.tick_preview.start(1000)

        root = QHBoxLayout()
        root.setSpacing(14)
        root.setContentsMargins(14, 14, 14, 14)

        left = QVBoxLayout()
        left.setSpacing(10)
        self.preview_lbl = QLabel()
        self.preview_lbl.setFixedSize(264, 264)
        self.preview_lbl.setStyleSheet(
            f"background: black; border: 2px solid {BORDER};"
            "border-radius: 12px;")
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        left.addWidget(self.preview_lbl)
        self.status_dot = QLabel()
        self.status_dot.setAlignment(Qt.AlignCenter)
        left.addWidget(self.status_dot)
        left.addStretch(1)
        self.refresh_device_status()
        root.addLayout(left)

        tabs = QTabWidget()
        tabs.addTab(self.temp_tab(), "🌡 Temperature")
        tabs.addTab(self.image_tab(), "🖼 Image")
        tabs.addTab(self.gif_tab(), "🎞 GIF")
        self.theme_editor = ThemeEditor()
        if isinstance(self.cfg.get("theme"), dict):
            try:
                self.theme_editor.set_theme(self.cfg["theme"])
            except (ValueError, KeyError, TypeError):
                pass
        self.theme_editor.use_monitor.setChecked(
            bool(self.cfg.get("theme_monitor", False)))
        self.theme_editor.send_requested.connect(
            lambda jpeg: self.send([("on", None), ("frame", jpeg)]))
        tabs.addTab(self.theme_editor, "🎨 Themes")
        tabs.addTab(self.settings_tab(), "⚙ Settings")
        root.addWidget(tabs, 1)

        wrap = QWidget()
        wrap.setLayout(root)
        self.setCentralWidget(wrap)
        self.statusBar().showMessage("ready")
        self._quitting = False
        self.setup_tray()
        # Monitoring starts automatically on launch (sends current card/theme).
        self.mon_btn.setChecked(True)

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(tray_icon(), self)
        menu = QMenu()
        show_act = QAction("Show / Hide", self)
        show_act.triggered.connect(self.toggle_visible)
        menu.addAction(show_act)
        send_act = QAction("Send once", self)
        send_act.triggered.connect(self.tick_monitor)
        menu.addAction(send_act)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.quit_app)
        menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.toggle_visible()
            if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def toggle_visible(self):
        self.setVisible(not self.isVisible())
        if self.isVisible():
            self.raise_()
            self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self.close()

    # ------------------------------------------------------------- helpers
    def refresh_device_status(self):
        ok = device_present()
        dot = "🟢" if ok else "🔴"
        txt = "pump connected" if ok else "pump not found"
        self.status_dot.setText(f"{dot} {txt}")

    def show_preview(self, jpeg: bytes):
        # Device bytes are pre-rotated 180° for the panel; rotate back so
        # the preview matches the composed image (and the pump screen).
        pix = QPixmap()
        pix.loadFromData(jpeg)
        pix = pix.transformed(QTransform().rotate(180))
        self.preview_lbl.setPixmap(
            pix.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def send(self, jobs):
        if self.sender and self.sender.isRunning():
            self.statusBar().showMessage("busy, wait…")
            return
        self.refresh_device_status()
        self.sender = SendThread(jobs)
        self.sender.done.connect(self.statusBar().showMessage)
        self.sender.preview.connect(self.show_preview)
        self.sender.start()

    # ----------------------------------------------------------------- tabs
    def temp_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.temp_lbl = QLabel("CPU -- / GPU --")
        self.temp_lbl.setProperty("class", "card big")
        self.temp_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.temp_lbl)
        row = QHBoxLayout()
        row.addWidget(QLabel("Interval, s:"))
        self.interval = QSpinBox()
        self.interval.setRange(1, 10)
        self.interval.setValue(int(self.cfg.get("interval", 2)))
        row.addWidget(self.interval)
        row.addStretch(1)
        lay.addLayout(row)
        self.mon_btn = QPushButton("▶ Start monitoring")
        self.mon_btn.setProperty("class", "primary")
        self.mon_btn.setCheckable(True)
        self.mon_btn.toggled.connect(self.toggle_monitor)
        lay.addWidget(self.mon_btn)
        once = QPushButton("Send once")
        once.clicked.connect(self.tick_monitor)
        lay.addWidget(once)
        lay.addStretch(1)
        self.refresh_temp_label()
        return w

    def refresh_temp_label(self):
        s = sensors.snapshot()
        fmt = lambda v: f"{v:.0f}°" if v is not None else "--"  # noqa: E731
        self.temp_lbl.setText(f"CPU {fmt(s['cpu_c'])}  ·  GPU {fmt(s['gpu_c'])}")
        if self.tray:
            self.tray.setToolTip(
                f"FX240 LCD — CPU {fmt(s['cpu_c'])} · GPU {fmt(s['gpu_c'])}")

    def toggle_monitor(self, on):
        self.mon_btn.setText("⏹ Stop monitoring" if on
                             else "▶ Start monitoring")
        if on:
            self.tick_monitor()
            self.mon_timer.start(self.interval.value() * 1000)
        else:
            self.mon_timer.stop()

    def tick_monitor(self):
        if self.theme_editor.use_monitor.isChecked():
            self.send([("frame", self.theme_editor.monitor_jpeg())])
            return
        s = sensors.snapshot()
        self.refresh_temp_label()
        if s["cpu_c"] is None:
            self.statusBar().showMessage("no CPU sensor")
            return
        self.send([("frame", image_pipe.temp_card(s["cpu_c"], s["gpu_c"]))])

    def image_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.img_path = QLabel("No file chosen")
        self.img_path.setProperty("class", "card")
        self.img_path.setWordWrap(True)
        lay.addWidget(self.img_path)
        pick = QPushButton("Choose image…")
        pick.clicked.connect(self.choose_image)
        lay.addWidget(pick)
        send = QPushButton("Send to display")
        send.setProperty("class", "primary")
        send.clicked.connect(self.send_image)
        lay.addWidget(send)
        lay.addStretch(1)
        self._img_jpeg = None
        return w

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Image", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        self.img_path.setText(Path(path).name)
        self._img_jpeg = image_pipe.from_file(path)
        self.show_preview(self._img_jpeg)

    def send_image(self):
        if not self._img_jpeg:
            self.statusBar().showMessage("choose an image first")
            return
        self.send([("on", None), ("frame", self._img_jpeg)])

    def gif_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.gif_path = QLabel("No file chosen")
        self.gif_path.setProperty("class", "card")
        self.gif_path.setWordWrap(True)
        lay.addWidget(self.gif_path)
        pick = QPushButton("Choose GIF…")
        pick.clicked.connect(self.choose_gif)
        lay.addWidget(pick)
        row = QHBoxLayout()
        row.addWidget(QLabel("FPS:"))
        self.fps = QSpinBox()
        self.fps.setRange(1, 19)
        self.fps.setValue(10)
        row.addWidget(self.fps)
        row.addStretch(1)
        lay.addLayout(row)
        play = QPushButton("Play once on display")
        play.setProperty("class", "primary")
        play.clicked.connect(self.play_gif)
        lay.addWidget(play)
        lay.addStretch(1)
        self._gif_frames = []
        return w

    def choose_gif(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "GIF", str(Path.home()), "GIF (*.gif)")
        if not path:
            return
        self.gif_path.setText(Path(path).name)
        self._gif_frames = image_pipe.gif_frames(path)
        self.statusBar().showMessage(f"{len(self._gif_frames)} frames")
        if self._gif_frames:
            self.show_preview(self._gif_frames[0])

    def play_gif(self):
        if not self._gif_frames:
            self.statusBar().showMessage("choose a GIF first")
            return
        self.send([("on", None)] +
                  [("frame", f) for f in self._gif_frames])

    def settings_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Brightness (vendor default 100):"))
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(0, 100)
        self.bright.setValue(int(self.cfg.get("brightness", 100)))
        lay.addWidget(self.bright)
        apply_b = QPushButton("Apply brightness")
        apply_b.clicked.connect(
            lambda: self.send([("bright", self.bright.value())]))
        lay.addWidget(apply_b)
        on = QPushButton("Display on")
        on.clicked.connect(lambda: self.send([("on", None)]))
        lay.addWidget(on)
        self.autostart_box = QCheckBox("Start with system (autostart)")
        self.autostart_box.setChecked(autostart_enabled())
        self.autostart_box.toggled.connect(self.toggle_autostart)
        lay.addWidget(self.autostart_box)
        lay.addStretch(1)
        return w

    def toggle_autostart(self, on):
        try:
            set_autostart(on)
            self.statusBar().showMessage(
                "autostart enabled" if on else "autostart disabled")
        except OSError as e:
            self.statusBar().showMessage(f"autostart failed: {e}")
            self.autostart_box.blockSignals(True)
            self.autostart_box.setChecked(not on)
            self.autostart_box.blockSignals(False)

    def closeEvent(self, event):
        if not self._quitting and self.tray and self.tray.isVisible():
            event.ignore()  # close button minimizes to tray instead
            self.hide()
            self.tray.showMessage(
                "FX240 LCD", "Minimized to tray — monitoring continues.")
            return
        self.mon_timer.stop()
        self.tick_preview.stop()
        self.theme_editor._refresh_timer.stop()
        if self.sender and self.sender.isRunning():
            self.sender.wait(3000)
        self.cfg["brightness"] = self.bright.value()
        self.cfg["interval"] = self.interval.value()
        self.cfg["theme"] = self.theme_editor.theme
        self.cfg["theme_monitor"] = self.theme_editor.use_monitor.isChecked()
        try:
            CONFIG.write_text(json.dumps(self.cfg, indent=1))
        except OSError:
            pass
        super().closeEvent(event)


def main():
    import argparse
    import fcntl
    ap = argparse.ArgumentParser()
    ap.add_argument("--minimized", action="store_true",
                    help="start hidden in tray (for autostart)")
    args = ap.parse_args()

    lock_path = Path.home() / ".cache" / "fx240-lcd.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("FX240 LCD is already running.")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray keeps running with no window
    app.setStyleSheet(QSS)
    win = MainWindow()
    if args.minimized:
        win.hide()
    else:
        win.show()
    ret = app.exec()
    try:
        lock_path.unlink()
    except OSError:
        pass
    sys.exit(ret)


if __name__ == "__main__":
    main()

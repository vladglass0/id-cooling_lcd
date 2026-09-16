# AGENTS.md — id-cooling_lcd

## Goal
Python + PySide6 GUI for ID-COOLING FX240 LCD on Linux: temps as digits,
custom 240x240 images/GIF, monitoring render. Port, don't reinvent — the
vendor stack is rebranded Mirabox/HotSpot StreamDock, use it as reference.

## Hardware (verified via lsusb + hidraw, 2026-09-16)
- Pump LCD = `2000:3000 HOTSPOTEKUSB HID DEMO`, serial `4250D2781D4D`.
  NOT `1A86:E317` (RustCooling's VID:PID doesn't exist here — other HW rev).
- Linux node `/dev/hidraw8` (`6-10`, internal header). Output 1024 B /
  Input 512 B (+1 ReportID byte on wire = 1025/513). Usage page `0xFFA0`.
- Profile `RLCD_1_5`, 240x240. Sensors present: `k10temp` + `amdgpu`.

## Protocol (from temp/ RE + MIT donors)
- `temp/` = official FX LCD Series Software binaries, READ-ONLY RE reference.
  NEVER commit `temp/`, NEVER copy vendor code into the repo.
- Transport: `CRT\0\0` packets (`DIS` on, `LIG` brightness) + `DRA`
  frame upload: announce (`SIZE u16BE = len(JPEG)+32`, target `0xB1`)
  → raw 1024 B chunks → draws immediately, no refresh needed.
  See `docs/PROTOCOL.md` (reversed 2026-09-16, 31/31 frames carved).
  Firmware version = safe read-only `GET_REPORT(Input, id 0, 512)`
  → `V26_FX_LCD_1.48_02.007`.
- Donors: `rigor789/mirabox-streamdock-node` (packet source of truth),
  `skyf/lightslinger` (1025/513 sizes, 10s heartbeat, software-mode),
  `applearon/libtransport-decomp` (`packets.hpp` vocabulary).
- Unknown until probed live: RLCD_1_5 screen target-ID, JPEG-vs-raw,
  handshake bytes. Workflow: safe read-only probes first (`probe_safe.py`,
  no writes ever), usbmon capture second, image upload only after calibration.

## Safety rules
- No writes to the pump without explicit user approval per new command class.
  Never touch `settingDevicePowerOnLogo` (flash write) casually.
- `hidraw` nodes are root-only by default; use `99-fx-lcd.rules` (udev),
  never run the app as root.
- Layout: `app.py` (GUI) / `hotspotek.py` (transport) / `rlcd15.py`
  (pump profile, pure builders) / `sensors.py` / `image_pipe.py` /
  `theme.py` (theme model + PIL render) / `editor.py` (visual theme editor)
  (+ udev + `tools/usbpcap_parse.py`). `probe_safe.py` (read-only) and
  `send_calibration.py` (one-shot replay) are dev tools, not app code.
  Tests must run without hardware: `python3 tests/test_offline.py`.

## Repo hygiene
- `.gitignore`: `temp/`, `*.pcapng`, `__pycache__/`, `.venv/`, `config.json`.
- `test.txt` is scratch — do not commit.

# FX240 LCD — ID-COOLING FX240 pump display control on Linux

Python + PySide6 app for the **ID-COOLING FX240 LCD** pump:
live temperature monitoring, custom images and GIFs on the 240×240 screen,
a visual theme editor like the official software. The vendor app is
Windows-only; this is native Linux, no Wine.

## Hardware

- Pump display: `2000:3000 HOTSPOTEKUSB HID DEMO`, `/dev/hidraw*`,
  1.48" 240×240 screen, firmware `V26_FX_LCD_1.48_02.007`.
- Protocol reversed from a USB capture of the official app: `CRT\0\0` HID
  packets, frame upload via `DRA` (240×240 JPEG + 1024 B chunks).
  Details: [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Install

```bash
pip install hidapi Pillow psutil PySide6
sudo cp 99-fx-lcd.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

The udev rule grants pump access without root. Verify (read-only,
writes nothing to the device):

```bash
python3 probe_safe.py
```

## Run

```bash
python3 app.py              # window + monitoring autostart
python3 app.py --minimized  # quietly to tray (for autostart)
```

## Features

- **🌡 Temperature** — CPU/GPU card, 1–10 s interval, send once or on timer.
- **🖼 Image** — any picture (square-cropped to 240×240).
- **🎞 GIF** — up to 60 frames, FPS 1–19.
- **🎨 Themes** — theme editor: widgets (temps, CPU load, clock, text,
  progress bar), drag-and-drop, background image, JSON save/load.
  “Use theme for monitoring” makes the monitor send your theme.
- **⚙ Settings** — brightness, display on, autostart.
- Tray: closing minimizes, tooltip shows live temps. Single-instance lock.
- The pump panel is mounted rotated 180° — frames are pre-rotated
  automatically, preview matches the on-screen result.

## Autostart

- KDE/GNOME — checkbox in Settings (`.desktop` in `~/.config/autostart/`).
- Hyprland — line in `execs.lua`:
  ```lua
  hl.exec_cmd("/usr/bin/python3 /home/rtxbb/code/id-cooling_lcd/app.py --minimized")
  ```

## Files

| File | Purpose |
|---|---|
| `app.py` | GUI |
| `hotspotek.py` | HID transport |
| `rlcd15.py` | pump profile, packet builders (no hardware) |
| `sensors.py` | CPU/GPU sensors via hwmon |
| `image_pipe.py` | frame rendering → JPEG |
| `theme.py` / `editor.py` | themes: model+renderer / visual editor |
| `probe_safe.py` | safe probes (read-only) |
| `send_calibration.py` | one-shot calibration frame (capture replay) |
| `tools/usbpcap_parse.py` | USBPcap capture parser, frame carver |
| `docs/PROTOCOL.md` | protocol spec |

Hardware-free tests: `python3 tests/test_offline.py`

## ⚠️ Safety

- First write of a new command class only with explicit approval.
- Never touch `settingDevicePowerOnLogo` (pump flash write).
- `temp/` (vendor binaries) is a reversing reference only, never committed.

---

# FX240 LCD — управление дисплеем ID-COOLING FX240 под Linux

Python + PySide6 приложение для помпы **ID-COOLING FX240 LCD**:
живой мониторинг температур, свои картинки и GIF на экране 240×240,
визуальный редактор тем как в официальном софте. Официальный софт —
только под Windows; здесь — нативный Linux без Wine.

## Железо

- Дисплей помпы: `2000:3000 HOTSPOTEKUSB HID DEMO`, `/dev/hidraw*`,
  экран 1.48" 240×240, прошивка `V26_FX_LCD_1.48_02.007`.
- Протокол вскрыт из USB-дампа официального софта: HID-пакеты `CRT\0\0`,
  заливка кадра командой `DRA` (JPEG 240×240 + чанки по 1024 Б).
  Подробности — [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Установка

```bash
pip install hidapi Pillow psutil PySide6
sudo cp 99-fx-lcd.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Правило udev даёт доступ к помпе без root. Проверка
(только чтение, ничего не пишет в устройство):

```bash
python3 probe_safe.py
```

## Запуск

```bash
python3 app.py              # окно + автостарт мониторинга
python3 app.py --minimized  # тихо в трей (для автозапуска)
```

## Возможности

- **🌡 Temperature** — карточка CPU/GPU с интервалом 1–10 с, отправка разово или по таймеру.
- **🖼 Image** — любая картинка (кроп в квадрат 240×240).
- **🎞 GIF** — раскадровка до 60 кадров, FPS 1–19.
- **🎨 Themes** — редактор тем: виджеты (температуры, загрузка CPU, часы, текст, прогресс-бар), drag-and-drop, фон-картинка, сохранение в JSON. Галочка «Use theme for monitoring» — мониторинг шлёт твою тему.
- **⚙ Settings** — яркость, включение экрана, автозапуск.
- Трей: закрытие сворачивает, тултип показывает температуры. Защита от второго экземпляра.
- Панель помпы перевёрнута на 180° — кадры предповорачиваются автоматически, превью показывает как на экране.

## Автозапуск

- KDE/GNOME — галочка в Settings (`.desktop` в `~/.config/autostart/`).
- Hyprland — строка в `execs.lua`:
  ```lua
  hl.exec_cmd("/usr/bin/python3 /home/rtxbb/code/id-cooling_lcd/app.py --minimized")
  ```

## Файлы

| Файл | Назначение |
|---|---|
| `app.py` | GUI |
| `hotspotek.py` | HID-транспорт |
| `rlcd15.py` | профиль помпы, сборка пакетов (без железа) |
| `sensors.py` | CPU/GPU сенсоры через hwmon |
| `image_pipe.py` | рендер кадров → JPEG |
| `theme.py` / `editor.py` | темы: модель+рендер / визуальный редактор |
| `probe_safe.py` | безопасные пробы (только чтение) |
| `send_calibration.py` | разовый калибровочный кадр (реплей дампа) |
| `tools/usbpcap_parse.py` | разбор USBPcap-дампов, вырезание кадров |
| `docs/PROTOCOL.md` | спека протокола |

Тесты без железа: `python3 tests/test_offline.py`

## ⚠️ Безопасность

- Первая запись нового класса команд — только с явного разрешения.
- Не трогать `settingDevicePowerOnLogo` (запись во flash помпы).
- Каталог `temp/` (бинарники вендора) — только референс для реверса, в git не коммитится.

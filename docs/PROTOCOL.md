# RLCD_1_5 (ID-COOLING FX240 LCD, 2000:3000) — USB HID protocol

Reversed 2026-09-16 from `temp/id-cooling-pump.pcapng` (official Windows
software, USBPcap). Transport: HID interrupt, OUT 1024 B / IN 512 B
reports. No ReportID byte on the wire. Device sends no ACKs (fire-and-forget);
interrupt IN completions are empty.

## Session open (host → device)

1. Control GET firmware string → `V26_FX_LCD_1.48_02.007` (23 B, NUL-term).
   Same request the vendor DLL issues on open (`GET_REPORT Input id 0, 512`).
2. `CRT DIS` — display on. No handshake / mode-switch / heartbeat observed.
3. `CRT LIG 0x64` — brightness 100 (sent twice at startup by vendor app).

## Command reports (1024 B each, zero-padded)

```
DIS: 43 52 54 00 00  44 49 53  00 00 00 ...   # CRT DIS — show/display on
LIG: 43 52 54 00 00  4C 49 47  00 00 VV 00 ... # CRT LIG — brightness VV (0x64=100)
```

Related (same family, seen in DLL strings, NOT in capture — do not send blind):
`HAN` off, `CLE` clear, `STP` refresh. Capture shows DRA draws immediately
with no trailing STP.

## Frame upload (DRA) — verified, 31/31 frames carved

```
announce (1024 B):
  00..04  43 52 54 00 00        # CRT\0\0
  05..07  44 52 41              # DRA
  08..09  00 00                 # spacer
  10..11  SIZE u16 BE = len(JPEG) + 32   # 1559/1561 for ~1.5 KB frames
  12      B1                    # screen target-ID (RLCD_1_5 const, 0xB1)
  13      00                    # reserved
  14..31  00 x18                # padding
  32..1023 JPEG bytes [0:992]

continuation (1024 B each): raw JPEG bytes, last one ends with FF D9,
  remainder zero-padded.
```

Chunk count = 1 + ceil((SIZE - 32 - 992) / 1024). Vendor streams ~19 fps
(31 frames / 1.94 s, avg 53 ms apart) — pace output at ≥50 ms/frame.

## JPEG format (verified by decode)

240x240, RGB, baseline DCT, JFIF, high quality (DQT ~quality 90+).
Panel is mounted rotated 180° — vendor app rotates frames before upload
(live-verified 2026-09-16: red bar composed at top renders at top).
Animation = host-side render (vendor uses ffmpeg) + DRA per frame.
Solid black vs solid red differ by only 2 bytes on the wire.

## Carving a capture

`python3 tools/usbpcap_parse.py temp/id-cooling-pump.pcapng` replays the
packet list, carves DRA frames to `out_frames/`, checks SIZE fields and
zero padding. Needs only stdlib.

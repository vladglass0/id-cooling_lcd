"""Offline tests: packet layout + render pipeline. No hardware needed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import image_pipe
import rlcd15


def test_crt_layout():
    rep = rlcd15.cmd_dis()
    assert len(rep) == 1024
    assert rep[:8] == b"CRT\x00\x00DIS"
    assert set(rep[8:]) == {0}
    lig = rlcd15.cmd_brightness(100)
    assert lig[5:11] == b"LIG\x00\x00\x64"


def test_dra_roundtrip():
    jpeg = image_pipe.solid((255, 0, 0))
    assert jpeg[:2] == b"\xff\xd8" and jpeg[-2:] == b"\xff\xd9"
    reps = rlcd15.frame_reports(jpeg)
    ann = reps[0]
    assert ann[:8] == b"CRT\x00\x00DRA"
    size = int.from_bytes(ann[10:12], "big")
    assert size == len(jpeg) + 32, (size, len(jpeg))
    assert ann[12] == rlcd15.TARGET == 0xB1
    blob = ann[32:] + b"".join(reps[1:])
    assert blob.find(b"\xff\xd8") == 0
    eoi = blob.find(b"\xff\xd9")
    assert blob[:eoi + 2] == jpeg
    assert set(blob[eoi + 2:]) == {0}
    for r in reps:
        assert len(r) == 1024


def test_temp_card_and_sensors():
    import sensors
    snap = sensors.snapshot()
    assert "cpu_c" in snap and "gpu_c" in snap
    card = image_pipe.temp_card(snap["cpu_c"] or 0.0, snap["gpu_c"])
    assert card[:2] == b"\xff\xd8"
    from PIL import Image
    import io
    assert Image.open(io.BytesIO(card)).size == (240, 240)


def test_theme_render():
    import theme as theme_mod
    t = theme_mod.default_theme()
    vals = {"cpu_c": 41.0, "gpu_c": 38.0, "cpu_load": 12.0,
            "time_str": "16:20"}
    img, rects = theme_mod.render(t, vals)
    assert img.size == (240, 240)
    assert len(rects) == len(t["widgets"])
    jpeg = theme_mod.to_jpeg(t, vals)
    assert jpeg[:2] == b"\xff\xd8"
    reps = rlcd15.frame_reports(jpeg)
    assert reps[0][:8] == b"CRT\x00\x00DRA"


def test_theme_zero_size_regression():
    # Editor spinboxes / hand-edited JSON must never crash the renderer.
    import theme as theme_mod
    t = theme_mod.default_theme()
    t["widgets"].append({"id": "bad", "type": "text", "x": 0, "y": 0,
                         "size": 0, "w": 0, "color": [255, 255, 255],
                         "text": "x"})
    img, _ = theme_mod.render(t, {"cpu_c": 1.0})
    assert img.size == (240, 240)


if __name__ == "__main__":
    test_crt_layout()
    test_dra_roundtrip()
    test_temp_card_and_sensors()
    test_theme_render()
    test_theme_zero_size_regression()
    print("all offline tests passed")

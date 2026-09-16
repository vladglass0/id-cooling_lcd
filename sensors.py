"""Linux sensor readout: CPU (k10temp/coretemp) + AMD GPU, no root needed."""

from pathlib import Path


def _read(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _hwmon_by_name(*names: str) -> Path | None:
    for hw in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        try:
            if (hw / "name").read_text().strip() in names:
                return hw
        except OSError:
            continue
    return None


def cpu_temp() -> float | None:
    """Package temperature in C (first available tempN_input, millidegree)."""
    hw = _hwmon_by_name("k10temp", "coretemp", "zenpower")
    if hw is None:
        return None
    for cand in sorted(hw.glob("temp*_input")):
        raw = _read(cand)
        if raw:
            return raw / 1000.0
    return None


def gpu_temp() -> float | None:
    """AMD GPU edge temperature in C."""
    hw = _hwmon_by_name("amdgpu")
    if hw is None:
        return None
    raw = _read(hw / "temp1_input")
    return raw / 1000.0 if raw else None


def snapshot() -> dict:
    return {"cpu_c": cpu_temp(), "gpu_c": gpu_temp()}

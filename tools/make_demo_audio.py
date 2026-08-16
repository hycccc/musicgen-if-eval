#!/usr/bin/env python3
"""Synthesize the demo clips for the instruction-following eval workbench.

Every demo item is generated from a musical spec (key, mode, chord
progression in roman numerals, BPM), so the "ground truth" of each clip is
known by construction. Violations are introduced deliberately: a clip
rendered at the wrong tempo, in the wrong key, or with the wrong
progression becomes a controlled negative example for the workbench.

Usage:
    python3 tools/make_demo_audio.py          # writes audio/*.mp3
    python3 tools/make_demo_audio.py --embed  # also injects base64 into index.html
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SR = 22050
ROOT = Path(__file__).resolve().parent.parent

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]
ROMAN = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}


def parse_roman(symbol: str) -> tuple[int, bool]:
    """Return (scale degree, is_major_triad) for a roman-numeral symbol."""
    degree = ROMAN[symbol.lower().rstrip("°")]
    return degree, symbol[0].isupper()


def chord_midi(key: str, mode: str, symbol: str) -> list[int]:
    """MIDI notes (root, third, fifth) of a roman-numeral chord in a key."""
    tonic = NOTE_NAMES.index(key)
    scale = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    degree, is_major = parse_roman(symbol)
    root = 48 + tonic + scale[degree]
    third = root + (4 if is_major else 3)
    fifth = root + 7
    return [root, third, fifth, root + 12]


def midi_to_hz(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def synth_note(freq: float, dur: float, amp: float = 0.16) -> np.ndarray:
    """Small additive voice with exponential decay — piano-ish pluck."""
    t = np.arange(int(SR * dur)) / SR
    wave = np.zeros_like(t)
    for k, gain in [(1, 1.0), (2, 0.4), (3, 0.2), (4, 0.1)]:
        wave += gain * np.sin(2 * np.pi * freq * k * t)
    env = np.exp(-2.2 * t)
    return amp * wave * env


def kick(dur: float = 0.12) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    freq = 110 * np.exp(-18 * t) + 50
    return 0.5 * np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-14 * t)


def hat(dur: float = 0.03, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * dur)) / SR
    return 0.10 * rng.standard_normal(len(t)) * np.exp(-60 * t)


def render(key: str, mode: str, progression: list[str], bpm: float, bars: int = 4) -> np.ndarray:
    """Render `bars` bars: one chord per bar, four kick beats, offbeat hats."""
    beat = 60.0 / bpm
    bar = 4 * beat
    total = int(SR * bar * bars) + SR
    mix = np.zeros(total)

    for b in range(bars):
        chord = progression[b % len(progression)]
        start = int(SR * bar * b)
        for m in chord_midi(key, mode, chord):
            note = synth_note(midi_to_hz(m), bar)
            mix[start : start + len(note)] += note
        for q in range(4):
            k_at = start + int(SR * beat * q)
            k = kick()
            mix[k_at : k_at + len(k)] += k
            h_at = start + int(SR * beat * (q + 0.5))
            h = hat(seed=b * 4 + q)
            mix[h_at : h_at + len(h)] += h

    mix = mix[: int(SR * bar * bars)]
    return 0.85 * mix / np.max(np.abs(mix))


# ---------------------------------------------------------------------------
# Demo items. `spec` is what the prompt demands; `rendered` is what the audio
# actually contains. Where they differ, the item is a controlled violation.
# ---------------------------------------------------------------------------
ITEMS = [
    {
        "id": "if-001",
        "spec": dict(key="C", mode="major", progression=["I", "V", "vi", "IV"], bpm=120),
        "rendered": None,  # None = rendered exactly to spec
        "expected": "pass on all dimensions",
    },
    {
        "id": "if-002",
        "spec": dict(key="C", mode="major", progression=["I", "V", "vi", "IV"], bpm=120),
        "rendered": dict(key="C", mode="major", progression=["I", "V", "vi", "IV"], bpm=92),
        "expected": "tempo violation (rendered at 92 BPM)",
    },
    {
        "id": "if-003",
        "spec": dict(key="A", mode="minor", progression=["i", "VI", "III", "VII"], bpm=100),
        "rendered": None,
        "expected": "pass on all dimensions",
    },
    {
        "id": "if-004",
        "spec": dict(key="G", mode="major", progression=["I", "IV", "V", "I"], bpm=112),
        "rendered": dict(key="G#", mode="major", progression=["I", "IV", "V", "I"], bpm=112),
        "expected": "key violation (rendered a semitone up, in A♭)",
    },
    {
        "id": "if-005",
        "spec": dict(key="D", mode="major", progression=["I", "IV", "V", "I"], bpm=110),
        "rendered": dict(key="D", mode="major", progression=["I", "V", "vi", "IV"], bpm=110),
        "expected": "harmony violation (rendered I–V–vi–IV instead of I–IV–V–I)",
    },
    {
        "id": "if-006",
        "spec": dict(key="E", mode="minor", progression=["i", "VII", "VI", "VII"], bpm=140),
        "rendered": None,
        "expected": "pass on all dimensions",
    },
]


def encode_mp3(signal: np.ndarray, out_path: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        import wave

        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((signal * 32767).astype(np.int16).tobytes())
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-b:a", "64k", str(out_path)],
            check=True,
        )


def main() -> None:
    audio_dir = ROOT / "audio"
    audio_dir.mkdir(exist_ok=True)
    blobs: dict[str, str] = {}

    for item in ITEMS:
        actual = item["rendered"] or item["spec"]
        signal = render(**actual)
        path = audio_dir / f"{item['id']}.mp3"
        encode_mp3(signal, path)
        blobs[item["id"]] = base64.b64encode(path.read_bytes()).decode()
        print(f"{item['id']}: {path.stat().st_size/1024:.0f} KB — {item['expected']}")

    if "--embed" in sys.argv:
        index = ROOT / "index.html"
        html = index.read_text()
        payload = json.dumps(blobs)
        html = re.sub(
            r"const AUDIO_BLOBS = \{.*?\};",
            f"const AUDIO_BLOBS = {payload};",
            html,
            count=1,
            flags=re.S,
        )
        index.write_text(html)
        print(f"embedded {len(blobs)} clips into index.html")


if __name__ == "__main__":
    main()

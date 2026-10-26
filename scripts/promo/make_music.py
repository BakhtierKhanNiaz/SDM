"""SDM's promo music: a calm, original 35-second background track, made from plain waves.

    python scripts/promo/make_music.py OUT.wav [SECONDS]      (needs numpy)

Composed for SDM, so it carries no copyright beyond the project's own. Four chords (C, A
minor, F, G) at 100 beats a minute: soft pads, a bass, a plucked arpeggio, a light beat;
it fades in and out. Mixed under the voice by make_promo_audio.py.
"""

import sys
import wave

import numpy as np

RATE = 44100
BPM = 100
BEAT = 60 / BPM
# Each chord lasts one bar of four beats.
CHORDS = [
    (48, [60, 64, 67, 72]),  # C
    (45, [57, 60, 64, 69]),  # A minor
    (41, [53, 57, 60, 65]),  # F
    (43, [55, 59, 62, 67]),  # G
]


def freq(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def tone(note: int, seconds: float, shape: str = "sine", detune: float = 0.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    f = freq(note) * (1 + detune)
    if shape == "triangle":
        return 2 / np.pi * np.arcsin(np.sin(2 * np.pi * f * t))
    return np.sin(2 * np.pi * f * t)


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n)
    a, r = int(attack * RATE), int(release * RATE)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[-r:] *= np.linspace(1, 0, r)
    return env


def place(track: np.ndarray, sound: np.ndarray, start: float) -> None:
    i = int(start * RATE)
    end = min(len(track), i + len(sound))
    if i < end:
        track[i:end] += sound[: end - i]


def make(seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    left, right = np.zeros(n), np.zeros(n)
    bar = 4 * BEAT
    rng = np.random.default_rng(7)  # the same "random" hi-hats every time
    for index in range(int(seconds / bar) + 1):
        start = index * bar
        bass, notes = CHORDS[index % len(CHORDS)]
        # pads: two slightly detuned triangles per note, spread left and right
        for note in notes:
            for detune, side in ((-0.003, left), (0.003, right)):
                pad = tone(note, bar + 0.6, "triangle", detune) * envelope(
                    int((bar + 0.6) * RATE), 0.8, 1.0
                )
                place(side, pad * 0.045, start)
        # bass: one long note per bar
        low = tone(bass, bar, "sine") * envelope(int(bar * RATE), 0.02, 0.4)
        place(left, low * 0.16, start)
        place(right, low * 0.16, start)
        # plucked arpeggio in eighths, from the second bar
        if index >= 1:
            for step in range(8):
                note = notes[[0, 1, 2, 3, 2, 1, 2, 3][step]] + 12
                pluck = tone(note, 0.5, "sine") * np.exp(-np.arange(int(0.5 * RATE)) / RATE * 7)
                side = left if step % 2 == 0 else right
                place(side, pluck * 0.05, start + step * BEAT / 2)
        # beat from the third bar: soft kick on 1 and 3, hi-hat on the off-beats
        if index >= 2:
            for beat in range(4):
                if beat in (0, 2):
                    t = np.arange(int(0.35 * RATE)) / RATE
                    kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 9)
                    place(left, kick * 0.22, start + beat * BEAT)
                    place(right, kick * 0.22, start + beat * BEAT)
                hat = rng.normal(0, 1, int(0.06 * RATE)) * np.exp(
                    -np.arange(int(0.06 * RATE)) / RATE * 60
                )
                hat = np.diff(hat, prepend=0)  # brighter: keep the high part
                place(left, hat * 0.03, start + beat * BEAT + BEAT / 2)
                place(right, hat * 0.03, start + beat * BEAT + BEAT / 2)
    music = np.stack([left, right], axis=1)
    fade_in, fade_out = int(1.5 * RATE), int(3.0 * RATE)
    music[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    music[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return music / max(1e-9, np.abs(music).max()) * 0.8


def main() -> int:
    out = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 35.0
    pcm = (make(seconds) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    print(f"Made {out} ({seconds:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

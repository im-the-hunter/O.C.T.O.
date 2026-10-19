"""Sintetiza los SFX del HUD de J.A.R.V.I.S. (tonos generados, libres de derechos).

Uso:  python3 scripts/audio/generate_sounds.py
Salida: frontend/public/sounds/*.mp3   (requiere ffmpeg en el PATH)
"""
import os
import subprocess
import wave

import numpy as np
from scipy.signal import lfilter

SR = 44100
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "sounds")
OUT = os.path.abspath(OUT)
os.makedirs(OUT, exist_ok=True)


def save(name, samples):
    wav_path = f"/tmp/{name}.wav"
    mp3_path = os.path.join(OUT, f"{name}.mp3")
    x = np.clip(samples, -1, 1)
    pcm = (x * 32767).astype(np.int16)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, "-b:a", "128k", mp3_path],
        check=True,
    )
    print("OK", mp3_path)


def t(dur):
    return np.arange(int(SR * dur)) / SR


def env_ad(dur, a=0.01, r=0.3):
    n = int(SR * dur)
    attack = max(1, int(SR * a))
    e = np.ones(n)
    e[:attack] = np.linspace(0, 1, attack)
    rel = max(1, int(SR * r))
    e[-rel:] *= np.linspace(1, 0, rel)
    return e


# ---- ambient-hum.mp3: loop 4s, zumbido grave 55Hz + 110Hz con beat lento
tt = t(4)
hum = np.sin(2 * np.pi * 55 * tt) * 0.6 + np.sin(2 * np.pi * 110 * tt) * 0.25
hum += 0.15 * np.sin(2 * np.pi * 55.5 * tt)
hum *= 0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * tt)
f = int(SR * 0.05)
hum[:f] *= np.linspace(0, 1, f)
hum[-f:] *= np.linspace(1, 0, f)
save("ambient-hum", hum * 0.5)

# ---- activation-beep.mp3: dos tonos ascendentes suaves
seg1 = np.sin(2 * np.pi * np.linspace(660, 880, int(SR * 0.18)) * t(0.18))
seg2 = np.sin(2 * np.pi * np.linspace(880, 1320, int(SR * 0.35)) * t(0.35))
b = np.zeros(len(t(0.6)))
b[: len(seg1)] = seg1 * env_ad(0.18, 0.005, 0.05)
b[int(SR * 0.2): int(SR * 0.2) + len(seg2)] = seg2 * env_ad(0.35, 0.005, 0.2) * 0.8
save("activation-beep", b * 0.5)

# ---- thinking-sound.mp3: riser electronico 1.5s
tt = t(1.5)
sweep = np.sin(2 * np.pi * (200 + 300 * tt ** 2) * tt * 0.5)
noise = np.random.RandomState(7).randn(len(tt))
noise = lfilter([0.02], [1, -0.96], noise)
noise /= np.max(np.abs(noise))
th = 0.5 * sweep * env_ad(1.5, 1.2, 0.3) + 0.3 * noise * tt ** 2
save("thinking-sound", th * 0.4)

# ---- response-complete.mp3: acorde elegante en dos notas
tt = t(0.8)
ch = sum(np.sin(2 * np.pi * f_ * tt) * w for f_, w in [(659, 0.4), (988, 0.3), (1319, 0.3)])
tt2 = t(0.5)
ch2 = sum(np.sin(2 * np.pi * f_ * tt2) * w for f_, w in [(523, 0.4), (659, 0.3), (784, 0.3), (1047, 0.2)])
full = np.concatenate([ch * env_ad(0.8, 0.01, 0.4), ch2 * env_ad(0.5, 0.01, 0.45) * 0.8])
save("response-complete", full * 0.45)

# ---- button-click.mp3: click corto filtrado 0.06s
n = int(SR * 0.06)
rs = np.random.RandomState(3)
c = rs.randn(n)
c = lfilter([0.3], [1, -0.7], c)
c /= np.max(np.abs(c))
c *= np.exp(-np.arange(n) / (SR * 0.012))
c += 0.5 * np.sin(2 * np.pi * 1800 * np.arange(n) / SR) * np.exp(-np.arange(n) / (SR * 0.008))
save("button-click", c * 0.35)

# ---- error-sound.mp3: tono grave doble 0.7s
tt = t(0.7)
er = (np.sin(2 * np.pi * 160 * tt) + 0.6 * np.sin(2 * np.pi * 120 * tt)) * env_ad(0.7, 0.01, 0.3)
er += 0.03 * np.sign(np.sin(2 * np.pi * 160 * tt))
save("error-sound", er * 0.4)

# ---- hover.mp3: tick muy sutil 0.04s
n = int(SR * 0.04)
h = np.sin(2 * np.pi * 2400 * np.arange(n) / SR) * np.exp(-np.arange(n) / (SR * 0.006))
save("hover", h * 0.2)

# ---- message-in.mp3: blip 0.15s
tt = t(0.15)
m = np.sin(2 * np.pi * np.linspace(880, 1200, len(tt)) * tt) * env_ad(0.15, 0.005, 0.08)
save("message-in", m * 0.35)

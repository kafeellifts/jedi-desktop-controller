# 🖐 Jedi Desktop Controller

Control your entire desktop with hand gestures — no mouse needed.
Built with MediaPipe + OpenCV + PyAutoGUI.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.21-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

---

## Gestures

| Gesture | Hand | Action |
|---|---|---|
| ☝ Move index finger | Right | Move cursor |
| 🤌 Pinch once | Right | Left click (LMB) |
| 🤌🤌 Pinch twice fast | Right | Right click (RMB) |
| 🤘 Spiderman | Right | Scroll up |
| ✌ Peace | Right | Scroll down |
| 🖐 Open palm | Both | Mandala effect |
| ✊ Fist | Both | Fire ring effect |

---

## Setup

```bash
git clone https://github.com/kafeellifts/jedi-desktop-controller.git
cd jedi-desktop-controller
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Run

```bash
python hand_tracker.py
```

A camera picker popup will appear — select your webcam and click Start.

---

## How it works

- **MediaPipe Hands** detects 21 hand landmarks per hand at ~30 FPS
- **EMA smoother + dead-zone** removes jitter from natural hand tremor
- **Hysteresis thresholds** prevent click flickering at the pinch boundary
- **Gesture confirmation buffer** requires 3 consistent frames before firing
- **Click FSM** distinguishes single vs double pinch for LMB vs RMB

---

## Tuning

| Parameter | Location | Effect |
|---|---|---|
| `alpha=0.35` | `Smoother.__init__` | Higher = faster cursor, lower = smoother |
| `DEAD_PX = 4` | `Smoother` | Higher = less jitter, lower = more responsive |
| `CONFIRM_FRAMES = 3` | `GestureBuffer` | Higher = fewer false gestures |
| `DOUBLE_WIN = 0.40` | `ClickFSM` | Window in seconds for double-pinch RMB |
| `margin = 180` | `run()` | Size of the active mouse zone |

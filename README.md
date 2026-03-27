# 🖐 Jedi Desktop Controller

Control your entire desktop with hand gestures — no mouse needed.
Built with MediaPipe + OpenCV + PyAutoGUI.

![Python](https://img.shields.io/badge/Python-3.9--3.11-blue)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.x-green)
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

**Requirements:** Python 3.9–3.11 (MediaPipe does not support 3.12)

```bash
# Clone the repo
git clone https://github.com/kafeellifts/jedi-desktop-controller.git
cd jedi-desktop-controller

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Run

```bash
python hand_tracker.py
```

If your webcam isn't detected, run the camera test first to find the right index:

```bash
python test.py
```

Then change `camera_id` at the bottom of `hand_tracker.py` to match.

---

## How it works

- **MediaPipe Hands** detects 21 hand landmarks per hand at ~30 FPS
- **EMA smoother + dead-zone** removes jitter from natural hand tremor
- **Hysteresis thresholds** prevent click flickering at the pinch boundary
- **Gesture confirmation buffer** requires 3 consistent frames before firing
- **Click FSM** distinguishes single vs double pinch for LMB vs RMB

---

## Files

```
hand_tracker.py   — main controller
test.py           — camera index finder
requirements.txt  — dependencies
```

---

## Tuning

| Parameter | Location | Effect |
|---|---|---|
| `alpha=0.35` | `Smoother.__init__` | Higher = faster cursor, lower = smoother |
| `DEAD_PX = 4` | `Smoother` | Higher = less jitter, lower = more responsive |
| `CONFIRM_FRAMES = 3` | `GestureBuffer` | Higher = fewer false gestures |
| `DOUBLE_WIN = 0.40` | `ClickFSM` | Window in seconds for double-pinch RMB |
| `margin = 180` | `run()` | Size of the active mouse zone |

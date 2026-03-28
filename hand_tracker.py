"""
Jedi Desktop Controller
=======================
RIGHT hand (cyan)
  · Move index finger        →  mouse cursor
  · Pinch once               →  left click  (LMB)
  · Pinch twice fast         →  right click (RMB)
  · Spiderman                →  scroll up
  · Peace                    →  scroll down

BOTH hands
  · Open palm                →  mandala FX
  · Fist                     →  fire ring FX

Move mouse to TOP-LEFT corner to abort.
Press Q to quit.
"""

import cv2
import mediapipe as mp
import numpy as np
import math
from enum import Enum
from typing import Optional, Tuple
import time
import pyautogui
import collections
import threading
import tkinter as tk

# ── pyautogui ─────────────────────────────────────────────────────────────────
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0

# ── colours (BGR) ─────────────────────────────────────────────────────────────
RIGHT_SKEL   = (0,   220, 200)
RIGHT_ACCENT = (0,   255, 230)
LEFT_SKEL    = (20,  160, 255)
LEFT_ACCENT  = (30,  200, 255)
LMB_COLOR    = (0,    80, 255)
RMB_COLOR    = (0,    30, 200)
SCROLL_COLOR = (255, 180,   0)
FIST_COLOR   = (0,   120, 255)
PALM_COLOR   = (0,   215, 255)
ZONE_COLOR   = (160,   0, 220)


# ── gestures ──────────────────────────────────────────────────────────────────
class Gesture(Enum):
    OPEN_PALM = "open_palm"
    FIST      = "fist"
    PINCH     = "pinch"
    SPIDERMAN = "spiderman"
    PEACE     = "peace"


# ── EMA smoother + dead-zone ──────────────────────────────────────────────────
class Smoother:
    DEAD_PX = 4

    def __init__(self, alpha: float = 0.35):
        self.alpha = alpha
        self.sx: Optional[float] = None
        self.sy: Optional[float] = None

    def update(self, x: float, y: float) -> Tuple[float, float]:
        if self.sx is None:
            self.sx, self.sy = x, y
            return x, y
        self.sx += self.alpha * (x - self.sx)
        self.sy += self.alpha * (y - self.sy)
        return self.sx, self.sy

    def should_move(self, new_x: float, new_y: float) -> bool:
        if self.sx is None:
            return True
        return math.hypot(new_x - self.sx, new_y - self.sy) > self.DEAD_PX


# ── gesture confirmation buffer ───────────────────────────────────────────────
class GestureBuffer:
    CONFIRM_FRAMES = 3

    def __init__(self):
        self._buf: collections.deque = collections.deque(maxlen=self.CONFIRM_FRAMES)
        self.confirmed: Optional[Gesture] = None

    def update(self, raw: Optional[Gesture]) -> Optional[Gesture]:
        self._buf.append(raw)
        if len(self._buf) == self.CONFIRM_FRAMES and len(set(self._buf)) == 1:
            self.confirmed = self._buf[0]
        return self.confirmed


# ── click state machine ───────────────────────────────────────────────────────
class ClickFSM:
    ENTER_DIST = 0.040
    EXIT_DIST  = 0.060
    DOUBLE_WIN = 0.40
    MIN_HOLD   = 0.06

    STATE_IDLE     = "idle"
    STATE_PINCHING = "pinching"
    STATE_WAIT_2ND = "wait_2nd"
    STATE_FIRED    = "fired"

    def __init__(self):
        self._state     = self.STATE_IDLE
        self._enter_t   = 0.0
        self._release_t = 0.0

    def update(self, dist: float) -> Optional[str]:
        now   = time.perf_counter()
        pinch = dist < self.ENTER_DIST
        open_ = dist > self.EXIT_DIST
        action = None

        if self._state == self.STATE_IDLE:
            if pinch:
                self._state   = self.STATE_PINCHING
                self._enter_t = now

        elif self._state == self.STATE_PINCHING:
            if open_:
                if now - self._enter_t >= self.MIN_HOLD:
                    self._state     = self.STATE_WAIT_2ND
                    self._release_t = now
                else:
                    self._state = self.STATE_IDLE

        elif self._state == self.STATE_WAIT_2ND:
            if pinch:
                action      = "rmb"
                self._state = self.STATE_FIRED
            elif now - self._release_t > self.DOUBLE_WIN:
                action      = "lmb"
                self._state = self.STATE_IDLE

        elif self._state == self.STATE_FIRED:
            if open_:
                self._state = self.STATE_IDLE

        return action

    @property
    def is_pinching(self) -> bool:
        return self._state in (self.STATE_PINCHING,
                               self.STATE_WAIT_2ND,
                               self.STATE_FIRED)


# ── visual effects ────────────────────────────────────────────────────────────
class VisualEffect:

    @staticmethod
    def draw_magical_circle(frame: np.ndarray, center: Tuple[int, int],
                            radius: int, color: Tuple[int, int, int]) -> None:
        overlay = frame.copy()
        pulse   = int(math.sin(time.time() * 5) * 5)
        for i in range(3, 0, -1):
            r  = radius + i * 15 + pulse
            cv2.circle(overlay, center, r, color, i)
            sa = int(time.time() * 100 * i) % 360
            cv2.ellipse(overlay, center, (r+8, r+8), sa, 0, 180, color, 2)
        cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)

    @staticmethod
    def draw_mandala(frame: np.ndarray, center: Tuple[int, int],
                     size: int, color: Tuple[int, int, int]) -> None:
        overlay  = frame.copy()
        rotation = time.time() * 60
        for i in range(12):
            cv2.ellipse(overlay, center, (size, size//2),
                        i * 30 + rotation, 0, 360, color, 2)
        cv2.circle(overlay, center, size // 3, color, 3)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

    @staticmethod
    def draw_skeleton(frame: np.ndarray, hand_lm,
                      color: Tuple[int, int, int]) -> None:
        h, w = frame.shape[:2]
        lm   = hand_lm.landmark
        CONN = [
            (0,1),(1,2),(2,3),(3,4),
            (0,5),(5,6),(6,7),(7,8),
            (0,9),(9,10),(10,11),(11,12),
            (0,13),(13,14),(14,15),(15,16),
            (0,17),(17,18),(18,19),(19,20),
            (5,9),(9,13),(13,17),
        ]
        pts = [(int(p.x * w), int(p.y * h)) for p in lm]
        for a, b in CONN:
            cv2.line(frame, pts[a], pts[b], color, 2, cv2.LINE_AA)
        TIPS = {4, 8, 12, 16, 20}
        for i, pt in enumerate(pts):
            cv2.circle(frame, pt,
                       5 if i in TIPS else 3,
                       (255, 255, 255) if i in TIPS else color,
                       -1, cv2.LINE_AA)

    @staticmethod
    def draw_pinch_meter(frame: np.ndarray, tip: Tuple[int, int],
                         dist: float, enter: float, exit_: float,
                         is_pinching: bool) -> None:
        ratio = 1.0 - min(max((dist - enter) / (exit_ - enter), 0.0), 1.0)
        color = LMB_COLOR if is_pinching else (180, 180, 180)
        angle = int(ratio * 360)
        cv2.ellipse(frame, tip, (18, 18), -90, 0, angle, color, 3, cv2.LINE_AA)
        cv2.circle(frame, tip, 4, color, -1, cv2.LINE_AA)


# ── hand tracker ──────────────────────────────────────────────────────────────
class HandTracker:

    def __init__(self, camera_id: int = 0):
        self.camera_id = camera_id
        self.cap       = None
        self.hands = mp.solutions.hands.Hands(
            static_image_mode        = False,
            max_num_hands            = 2,
            model_complexity         = 0,
            min_detection_confidence = 0.65,
            min_tracking_confidence  = 0.60,
        )
        self.smoother      = Smoother(alpha=0.35)
        self.gesture_buf   = GestureBuffer()
        self.click_fsm     = ClickFSM()
        self.last_scroll_t = 0.0
        self._fps_buf      = collections.deque(maxlen=30)
        self._last_t       = time.perf_counter()

    def start_camera(self) -> bool:
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,  720)
        self.cap.set(cv2.CAP_PROP_FPS,            30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE,      1)
        return self.cap.isOpened()

    def _raw_gesture(self, lm, handedness: str) -> Optional[Gesture]:
        index_up  = lm[8].y  < lm[6].y
        middle_up = lm[12].y < lm[10].y
        ring_up   = lm[16].y < lm[14].y
        pinky_up  = lm[20].y < lm[18].y
        thumb_up  = (lm[4].x > lm[3].x) if handedness == "Right" \
                    else (lm[4].x < lm[3].x)
        dist = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y)

        if dist < ClickFSM.ENTER_DIST and not middle_up:
            return Gesture.PINCH
        if index_up and pinky_up and thumb_up and not middle_up and not ring_up:
            return Gesture.SPIDERMAN
        if index_up and middle_up and not ring_up and not pinky_up:
            return Gesture.PEACE
        if all([index_up, middle_up, ring_up, pinky_up]):
            return Gesture.OPEN_PALM
        if not any([index_up, middle_up, ring_up, pinky_up]):
            return Gesture.FIST
        return None

    def _draw_hud(self, frame: np.ndarray, cam_w: int, cam_h: int,
                  margin: int, fsm_state: str) -> None:
        now = time.perf_counter()
        self._fps_buf.append(1.0 / max(now - self._last_t, 1e-6))
        self._last_t = now
        fps = sum(self._fps_buf) / len(self._fps_buf)

        cv2.rectangle(frame, (margin, margin),
                      (cam_w-margin, cam_h-margin), ZONE_COLOR, 1, cv2.LINE_AA)
        cv2.putText(frame, "Mouse zone", (margin+6, margin-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, ZONE_COLOR, 1, cv2.LINE_AA)

        fps_col = (0, 220, 80) if fps >= 24 else (0, 130, 255)
        cv2.putText(frame, f"FPS {fps:.0f}", (cam_w-82, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, fps_col, 2, cv2.LINE_AA)

        state_labels = {
            ClickFSM.STATE_IDLE:     ("IDLE",     (100,100,100)),
            ClickFSM.STATE_PINCHING: ("PINCHING", LMB_COLOR),
            ClickFSM.STATE_WAIT_2ND: ("2nd?",     SCROLL_COLOR),
            ClickFSM.STATE_FIRED:    ("FIRED",     (0,220,80)),
        }
        s_text, s_col = state_labels.get(fsm_state, ("?", (200,200,200)))
        cv2.putText(frame, s_text, (cam_w-82, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, s_col, 1, cv2.LINE_AA)

        legend = [
            (RIGHT_ACCENT,  "Pinch x1       LMB"),
            (RMB_COLOR,     "Pinch x2       RMB"),
            (SCROLL_COLOR,  "Spiderman    scroll up"),
            (SCROLL_COLOR,  "Peace \u270c        scroll down"),
            (PALM_COLOR,    "Open palm    mandala FX"),
            (FIST_COLOR,    "Fist              fire ring FX"),
        ]
        lx = 10
        ly = cam_h - len(legend) * 18 - 28
        overlay = frame.copy()
        cv2.rectangle(overlay, (lx-4, ly-16), (230, cam_h-4), (0,0,0), -1)
        cv2.addWeighted(overlay, 0.50, frame, 0.50, 0, frame)
        cv2.rectangle(frame, (lx-4, ly-16), (230, cam_h-4), (55,55,55), 1)

        cv2.circle(frame, (lx+5, ly-6), 4, RIGHT_SKEL, -1, cv2.LINE_AA)
        cv2.putText(frame, "Right", (lx+14, ly-2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, RIGHT_SKEL, 1, cv2.LINE_AA)
        cv2.circle(frame, (lx+75, ly-6), 4, LEFT_SKEL, -1, cv2.LINE_AA)
        cv2.putText(frame, "Left", (lx+84, ly-2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, LEFT_SKEL, 1, cv2.LINE_AA)

        for i, (col, text) in enumerate(legend):
            y = ly + i * 18 + 12
            cv2.circle(frame, (lx+5, y-3), 4, col, -1, cv2.LINE_AA)
            cv2.putText(frame, text, (lx+16, y+1),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200,200,200), 1, cv2.LINE_AA)

        cv2.putText(frame, "Q = quit", (cam_w-72, cam_h-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (90,90,90), 1, cv2.LINE_AA)

    @staticmethod
    def _draw_label(frame: np.ndarray, text: str, idx: int,
                    color: Tuple[int, int, int]) -> None:
        y = 38 + idx * 32
        cv2.putText(frame, text, (13, y+1),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0,0,0), 4, cv2.LINE_AA)
        cv2.putText(frame, text, (13, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA)

    def run(self) -> None:
        if not self.start_camera():
            print("ERROR: Camera not found.")
            return

        cam_w  = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        cam_h  = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        scr_w, scr_h = pyautogui.size()
        margin = 180

        while True:
            ok, frame = self.cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = self.hands.process(rgb)
            rgb.flags.writeable = True

            fsm_state = self.click_fsm._state

            if results.multi_hand_landmarks:
                for idx, hand_lm in enumerate(results.multi_hand_landmarks):
                    lm         = hand_lm.landmark
                    handedness = results.multi_handedness[idx].classification[0].label
                    is_right   = (handedness == "Right")
                    skel       = RIGHT_SKEL   if is_right else LEFT_SKEL
                    accent     = RIGHT_ACCENT if is_right else LEFT_ACCENT

                    VisualEffect.draw_skeleton(frame, hand_lm, skel)
                    raw_g   = self._raw_gesture(lm, handedness)
                    gesture = self.gesture_buf.update(raw_g)

                    if is_right:
                        pinch_dist = math.hypot(lm[4].x - lm[8].x,
                                                lm[4].y - lm[8].y)
                        tip_px = (int(lm[8].x * cam_w), int(lm[8].y * cam_h))
                        VisualEffect.draw_pinch_meter(
                            frame, tip_px, pinch_dist,
                            ClickFSM.ENTER_DIST, ClickFSM.EXIT_DIST,
                            self.click_fsm.is_pinching)

                        click_action = self.click_fsm.update(pinch_dist)
                        fsm_state    = self.click_fsm._state

                        if click_action == "lmb":
                            pyautogui.click(button="left")
                            cv2.circle(frame, tip_px, 22, LMB_COLOR, -1, cv2.LINE_AA)
                            cv2.putText(frame, "LMB", (tip_px[0]-15, tip_px[1]-26),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                        (255,255,255), 2, cv2.LINE_AA)

                        elif click_action == "rmb":
                            pyautogui.click(button="right")
                            cv2.circle(frame, tip_px, 22, RMB_COLOR, -1, cv2.LINE_AA)
                            cv2.putText(frame, "RMB", (tip_px[0]-15, tip_px[1]-26),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                        (255,255,255), 2, cv2.LINE_AA)

                        raw_x  = np.interp(lm[8].x * cam_w,
                                           [margin, cam_w-margin], [0, scr_w])
                        raw_y  = np.interp(lm[8].y * cam_h,
                                           [margin, cam_h-margin], [0, scr_h])
                        should = self.smoother.should_move(raw_x, raw_y)
                        sx, sy = self.smoother.update(raw_x, raw_y)
                        if not self.click_fsm.is_pinching and should:
                            pyautogui.moveTo(sx, sy)

                        if gesture == Gesture.SPIDERMAN:
                            if time.perf_counter() - self.last_scroll_t > 0.12:
                                pyautogui.scroll(15)
                                self.last_scroll_t = time.perf_counter()
                        elif gesture == Gesture.PEACE:
                            if time.perf_counter() - self.last_scroll_t > 0.12:
                                pyautogui.scroll(-15)
                                self.last_scroll_t = time.perf_counter()

                    palm = (int(lm[0].x * cam_w), int(lm[0].y * cam_h))
                    if gesture == Gesture.OPEN_PALM:
                        VisualEffect.draw_mandala(frame, palm, 140, PALM_COLOR)
                    elif gesture == Gesture.FIST:
                        VisualEffect.draw_magical_circle(frame, palm, 60, accent)

                    if gesture and gesture != Gesture.PINCH:
                        self._draw_label(frame,
                                         f"{gesture.value}  [{handedness}]",
                                         idx, accent)

            self._draw_hud(frame, cam_w, cam_h, margin, fsm_state)
            cv2.imshow("Jedi Desktop Controller", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        self.cap.release()
        cv2.destroyAllWindows()


# ── camera picker popup ───────────────────────────────────────────────────────
def pick_camera() -> int:
    print("Scanning cameras...")
    found = []  # list of (index, name)

    try:
        from pygrabber.dshow_graph import FilterGraph
        device_names = FilterGraph().get_input_devices()
    except Exception:
        device_names = []

    for i in range(6):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        ok = [False]
        def try_read(c=cap, r=ok):
            ret, frame = c.read()
            if ret and frame is not None:
                r[0] = True
        t = threading.Thread(target=try_read)
        t.start()
        t.join(timeout=1.5)
        cap.release()
        if ok[0]:
            name = device_names[i] if i < len(device_names) else f"Camera {i}"
            found.append((i, name))
            print(f"  Found: {name} (index {i})")

    if not found:
        print("No cameras found, defaulting to 0")
        return 0

    if len(found) == 1:
        print(f"Using: {found[0][1]}")
        return found[0][0]

    # Show picker
    root = tk.Tk()
    selected = tk.IntVar(value=found[0][0])
    root.title("Jedi Controller")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    w = 360
    h = 120 + len(found) * 36
    x = (root.winfo_screenwidth()  - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.configure(bg="#1a1a1a")

    tk.Label(root, text="Jedi Desktop Controller",
             font=("Segoe UI", 13, "bold"),
             bg="#1a1a1a", fg="white").pack(pady=(18, 4))
    tk.Label(root, text="Select your webcam:",
             font=("Segoe UI", 10),
             bg="#1a1a1a", fg="#aaaaaa").pack(pady=(0, 10))

    for idx, name in found:
        tk.Radiobutton(root, text=name,
                       variable=selected, value=idx,
                       font=("Segoe UI", 10),
                       bg="#1a1a1a", fg="white",
                       selectcolor="#333333",
                       activebackground="#1a1a1a",
                       activeforeground="white").pack(anchor="w", padx=40)

    tk.Button(root, text="  Start  ",
              command=root.destroy,
              font=("Segoe UI", 10, "bold"),
              bg="#00dcc8", fg="#000000",
              relief="flat", cursor="hand2",
              padx=16, pady=6).pack(pady=18)

    root.mainloop()
    return selected.get()


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    HandTracker(camera_id=pick_camera()).run()

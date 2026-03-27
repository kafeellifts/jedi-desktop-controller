"""
Jedi Desktop Controller
=======================
RIGHT hand (cyan)
  · Move index finger        →  mouse cursor
  · Pinch  (single)          →  LEFT click  (LMB)
  · Pinch  (double, <0.4s)   →  RIGHT click (RMB)
  · Spiderman                →  scroll up
  · Peace ✌                  →  scroll down

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

# ── pyautogui tuning ──────────────────────────────────────────────────────────
pyautogui.FAILSAFE = True   # top-left corner = emergency abort
pyautogui.PAUSE    = 0      # remove hidden 0.1 s sleep after every call

# ── colours (BGR) ─────────────────────────────────────────────────────────────
RIGHT_SKEL   = (0,   220, 200)   # cyan-teal
RIGHT_ACCENT = (0,   255, 230)
LEFT_SKEL    = (20,  160, 255)   # orange-amber
LEFT_ACCENT  = (30,  200, 255)

LMB_COLOR    = (0,   80,  255)   # blue  – left click
RMB_COLOR    = (0,   30,  200)   # dark blue-purple – right click
SCROLL_COLOR = (255, 180,   0)   # amber
FIST_COLOR   = (0,   120, 255)
PALM_COLOR   = (0,   215, 255)
ZONE_COLOR   = (160,   0, 220)   # purple


# ── gestures ──────────────────────────────────────────────────────────────────
class Gesture(Enum):
    OPEN_PALM = "open_palm"
    FIST      = "fist"
    PINCH     = "pinch"
    SPIDERMAN = "spiderman"
    PEACE     = "peace"


# ══════════════════════════════════════════════════════════════════════════════
#  EMA + dead-zone smoother
#  Dead-zone: if the cursor hasn't moved more than DEAD_PX pixels from where
#  it already is, don't move at all.  This eliminates the micro-jitter at rest
#  while keeping full responsiveness during intentional movement.
# ══════════════════════════════════════════════════════════════════════════════
class Smoother:
    DEAD_PX = 4          # pixels — tune up if still jittery, down if sluggish

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
        """Return False when the smoothed position is within the dead-zone."""
        if self.sx is None:
            return True
        return math.hypot(new_x - self.sx, new_y - self.sy) > self.DEAD_PX


# ══════════════════════════════════════════════════════════════════════════════
#  Gesture confirmation buffer
#  A gesture must appear in CONFIRM_FRAMES consecutive frames before it is
#  accepted.  This eliminates single-frame flickers (e.g. landmark jitter
#  briefly crossing the pinch threshold).
# ══════════════════════════════════════════════════════════════════════════════
class GestureBuffer:
    CONFIRM_FRAMES = 3    # frames a gesture must hold to be "confirmed"

    def __init__(self):
        self._buf: collections.deque = collections.deque(maxlen=self.CONFIRM_FRAMES)
        self.confirmed: Optional[Gesture] = None

    def update(self, raw: Optional[Gesture]) -> Optional[Gesture]:
        self._buf.append(raw)
        if len(self._buf) == self.CONFIRM_FRAMES and \
                len(set(self._buf)) == 1:          # all frames agree
            self.confirmed = self._buf[0]
        return self.confirmed


# ══════════════════════════════════════════════════════════════════════════════
#  Click state machine
#  Replaces the simple cooldown timer.
#
#  States
#  ------
#  IDLE        – no pinch in progress
#  PINCHING    – pinch is held; waiting to see if a second pinch follows
#  WAIT_2ND    – first pinch released; window open for a second pinch → RMB
#  FIRED       – click action was already sent; ignore until pinch released
#
#  Hysteresis
#  ----------
#  ENTER threshold  <  EXIT threshold
#  Once pinch is detected (dist < ENTER) it stays "active" until the fingers
#  are clearly open (dist > EXIT).  This stops the detection bouncing on/off
#  when the distance wobbles right at the threshold.
# ══════════════════════════════════════════════════════════════════════════════
class ClickFSM:
    ENTER_DIST   = 0.040   # normalised units – pinch activates
    EXIT_DIST    = 0.060   # normalised units – pinch releases (wider = hysteresis gap)
    DOUBLE_WIN   = 0.40    # seconds – window for second pinch → RMB
    MIN_HOLD     = 0.06    # seconds – minimum hold before pinch counts (noise filter)

    STATE_IDLE     = "idle"
    STATE_PINCHING = "pinching"
    STATE_WAIT_2ND = "wait_2nd"
    STATE_FIRED    = "fired"

    def __init__(self):
        self._state      = self.STATE_IDLE
        self._enter_t    = 0.0   # when we entered PINCHING
        self._release_t  = 0.0   # when first pinch was released
        self._action: Optional[str] = None   # "lmb" or "rmb" ready to fire

    # Returns "lmb", "rmb", or None
    def update(self, dist: float) -> Optional[str]:
        now    = time.perf_counter()
        pinch  = dist < self.ENTER_DIST
        open_  = dist > self.EXIT_DIST
        action = None

        if self._state == self.STATE_IDLE:
            if pinch:
                self._state   = self.STATE_PINCHING
                self._enter_t = now

        elif self._state == self.STATE_PINCHING:
            if open_:
                held = now - self._enter_t
                if held >= self.MIN_HOLD:
                    # First release — open window for a second pinch
                    self._state     = self.STATE_WAIT_2ND
                    self._release_t = now
                else:
                    # Too short – noise, ignore
                    self._state = self.STATE_IDLE

        elif self._state == self.STATE_WAIT_2ND:
            if pinch:
                # Second pinch within window → RMB
                action      = "rmb"
                self._state = self.STATE_FIRED
            elif now - self._release_t > self.DOUBLE_WIN:
                # Window expired with no second pinch → LMB
                action      = "lmb"
                self._state = self.STATE_IDLE

        elif self._state == self.STATE_FIRED:
            if open_:
                self._state = self.STATE_IDLE

        return action

    @property
    def is_pinching(self) -> bool:
        return self._state in (self.STATE_PINCHING, self.STATE_FIRED,
                               self.STATE_WAIT_2ND)


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

    # Pinch arc indicator — shows how close to pinch threshold you are
    @staticmethod
    def draw_pinch_meter(frame: np.ndarray, tip: Tuple[int, int],
                         dist: float,
                         enter: float, exit_: float,
                         is_pinching: bool) -> None:
        ratio = 1.0 - min(max((dist - enter) / (exit_ - enter), 0.0), 1.0)
        color = LMB_COLOR if is_pinching else (180, 180, 180)
        r     = 18
        angle = int(ratio * 360)
        cv2.ellipse(frame, tip, (r, r), -90, 0, angle, color, 3, cv2.LINE_AA)
        cv2.circle(frame, tip, 4, color, -1, cv2.LINE_AA)


# ── main tracker ─────────────────────────────────────────────────────────────
class HandTracker:

    def __init__(self, camera_id: int = 0):
        self.camera_id = camera_id
        self.cap       = None

        self.hands = mp.solutions.hands.Hands(
            static_image_mode        = False,
            max_num_hands            = 2,
            model_complexity         = 0,        # fast lightweight model
            min_detection_confidence = 0.65,
            min_tracking_confidence  = 0.60,
        )

        self.smoother    = Smoother(alpha=0.35)
        self.gesture_buf = GestureBuffer()
        self.click_fsm   = ClickFSM()

        self.last_scroll_t = 0.0
        self._fps_buf      = collections.deque(maxlen=30)
        self._last_t       = time.perf_counter()

    # ── camera ────────────────────────────────────────────────────────────────
    def start_camera(self) -> bool:
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,  720)
        self.cap.set(cv2.CAP_PROP_FPS,            30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE,      1)   # always grab latest frame
        return self.cap.isOpened()

    # ── raw gesture from landmarks ────────────────────────────────────────────
    def _raw_gesture(self, lm, handedness: str) -> Optional[Gesture]:
        index_up  = lm[8].y  < lm[6].y
        middle_up = lm[12].y < lm[10].y
        ring_up   = lm[16].y < lm[14].y
        pinky_up  = lm[20].y < lm[18].y
        thumb_up  = (lm[4].x > lm[3].x) if handedness == "Right" \
                    else (lm[4].x < lm[3].x)

        dist = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y)

        # Pinch detection is handled separately via ClickFSM;
        # still return PINCH so the buffer & visual indicator work
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

    # ── HUD ───────────────────────────────────────────────────────────────────
    def _draw_hud(self, frame: np.ndarray, cam_w: int, cam_h: int,
                  margin: int, fsm_state: str) -> None:
        now = time.perf_counter()
        self._fps_buf.append(1.0 / max(now - self._last_t, 1e-6))
        self._last_t = now
        fps = sum(self._fps_buf) / len(self._fps_buf)

        # Mouse zone
        cv2.rectangle(frame, (margin, margin),
                      (cam_w - margin, cam_h - margin),
                      ZONE_COLOR, 1, cv2.LINE_AA)
        cv2.putText(frame, "Mouse zone",
                    (margin + 6, margin - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, ZONE_COLOR, 1, cv2.LINE_AA)

        # FPS
        fps_col = (0, 220, 80) if fps >= 24 else (0, 130, 255)
        cv2.putText(frame, f"FPS {fps:.0f}", (cam_w - 82, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, fps_col, 2, cv2.LINE_AA)

        # Click state indicator (top-right, below FPS)
        state_labels = {
            ClickFSM.STATE_IDLE:     ("IDLE",     (100, 100, 100)),
            ClickFSM.STATE_PINCHING: ("PINCHING", LMB_COLOR),
            ClickFSM.STATE_WAIT_2ND: ("2nd?",     SCROLL_COLOR),
            ClickFSM.STATE_FIRED:    ("FIRED",     (0, 220, 80)),
        }
        s_text, s_col = state_labels.get(fsm_state, ("?", (200,200,200)))
        cv2.putText(frame, s_text, (cam_w - 82, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, s_col, 1, cv2.LINE_AA)

        # Legend
        legend = [
            (RIGHT_ACCENT,  "Pinch x1        LMB (left click)"),
            (RMB_COLOR,     "Pinch x2        RMB (right click)"),
            (SCROLL_COLOR,  "Spiderman     scroll up"),
            (SCROLL_COLOR,  "Peace \u270c         scroll down"),
            (PALM_COLOR,    "Open palm     mandala FX"),
            (FIST_COLOR,    "Fist               fire ring FX"),
        ]
        lx = 10
        ly = cam_h - len(legend) * 18 - 28

        overlay = frame.copy()
        cv2.rectangle(overlay, (lx-4, ly-16), (288, cam_h-4), (0,0,0), -1)
        cv2.addWeighted(overlay, 0.50, frame, 0.50, 0, frame)
        cv2.rectangle(frame,    (lx-4, ly-16), (288, cam_h-4), (55,55,55), 1)

        # Hand colour key row
        cv2.circle(frame, (lx+5, ly-6), 4, RIGHT_SKEL, -1, cv2.LINE_AA)
        cv2.putText(frame, "Right hand", (lx+14, ly-2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, RIGHT_SKEL, 1, cv2.LINE_AA)
        cv2.circle(frame, (lx+110, ly-6), 4, LEFT_SKEL, -1, cv2.LINE_AA)
        cv2.putText(frame, "Left hand",  (lx+120, ly-2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, LEFT_SKEL,  1, cv2.LINE_AA)

        for i, (col, text) in enumerate(legend):
            y = ly + i * 18 + 12
            cv2.circle(frame, (lx+5, y-3), 4, col, -1, cv2.LINE_AA)
            cv2.putText(frame, text, (lx+16, y+1),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200,200,200),
                        1, cv2.LINE_AA)

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

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        if not self.start_camera():
            print("ERROR: Camera not found. Run test.py to find the right index.")
            return

        cam_w  = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        cam_h  = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        scr_w, scr_h = pyautogui.size()
        margin = 180

        print("\n" + "═"*54)
        print("  Jedi Desktop Controller — running")
        print("═"*54)
        print(f"  Camera : {cam_w}×{cam_h}  index={self.camera_id}")
        print(f"  Screen : {scr_w}×{scr_h}")
        print()
        print("  RIGHT hand  (cyan skeleton)")
        print("    move index     →  cursor")
        print("    pinch once     →  LMB  (left click)")
        print("    pinch twice    →  RMB  (right click)")
        print("    spiderman      →  scroll up")
        print("    peace ✌        →  scroll down")
        print()
        print("  BOTH hands")
        print("    open palm      →  mandala FX")
        print("    fist           →  fire ring FX")
        print()
        print("  TOP-LEFT corner = emergency abort")
        print("  Q = quit")
        print("═"*54 + "\n")

        while True:
            ok, frame = self.cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = self.hands.process(rgb)
            rgb.flags.writeable = True

            fsm_state = self.click_fsm._state   # for HUD display

            if results.multi_hand_landmarks:
                for idx, hand_lm in enumerate(results.multi_hand_landmarks):
                    lm         = hand_lm.landmark
                    handedness = results.multi_handedness[idx].classification[0].label
                    is_right   = (handedness == "Right")

                    skel  = RIGHT_SKEL   if is_right else LEFT_SKEL
                    accent= RIGHT_ACCENT if is_right else LEFT_ACCENT

                    VisualEffect.draw_skeleton(frame, hand_lm, skel)

                    raw_g   = self._raw_gesture(lm, handedness)
                    gesture = self.gesture_buf.update(raw_g)   # confirmed gesture

                    # ── right-hand mouse control ───────────────────────────
                    if is_right:
                        pinch_dist = math.hypot(lm[4].x - lm[8].x,
                                                lm[4].y - lm[8].y)

                        # Pinch meter arc around index fingertip
                        tip_px = (int(lm[8].x * cam_w), int(lm[8].y * cam_h))
                        VisualEffect.draw_pinch_meter(
                            frame, tip_px, pinch_dist,
                            ClickFSM.ENTER_DIST, ClickFSM.EXIT_DIST,
                            self.click_fsm.is_pinching)

                        # Feed FSM
                        click_action = self.click_fsm.update(pinch_dist)
                        fsm_state    = self.click_fsm._state

                        if click_action == "lmb":
                            pyautogui.click(button="left")
                            self._draw_label(frame, "LMB  click", idx, LMB_COLOR)
                            cv2.circle(frame, tip_px, 22, LMB_COLOR, -1, cv2.LINE_AA)
                            cv2.putText(frame, "LMB", (tip_px[0]-15, tip_px[1]-26),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                        (255,255,255), 2, cv2.LINE_AA)

                        elif click_action == "rmb":
                            pyautogui.click(button="right")
                            self._draw_label(frame, "RMB  click", idx, RMB_COLOR)
                            cv2.circle(frame, tip_px, 22, RMB_COLOR, -1, cv2.LINE_AA)
                            cv2.putText(frame, "RMB", (tip_px[0]-15, tip_px[1]-26),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                        (255,255,255), 2, cv2.LINE_AA)

                        # Always update smoother so it tracks hand position
                        # even during pinch — avoids snap-jump on release
                        raw_x = np.interp(lm[8].x * cam_w,
                                          [margin, cam_w-margin], [0, scr_w])
                        raw_y = np.interp(lm[8].y * cam_h,
                                          [margin, cam_h-margin], [0, scr_h])
                        # Check dead-zone BEFORE update (compare raw target vs
                        # current smoothed position, not smoothed vs itself)
                        should = self.smoother.should_move(raw_x, raw_y)
                        sx, sy = self.smoother.update(raw_x, raw_y)
                        # Only move the real cursor when not pinching
                        if not self.click_fsm.is_pinching and should:
                            pyautogui.moveTo(sx, sy)

                        # Scroll (confirmed gesture, not raw)
                        if gesture == Gesture.SPIDERMAN:
                            if time.perf_counter() - self.last_scroll_t > 0.12:
                                pyautogui.scroll(15)
                                self.last_scroll_t = time.perf_counter()

                        elif gesture == Gesture.PEACE:
                            if time.perf_counter() - self.last_scroll_t > 0.12:
                                pyautogui.scroll(-15)
                                self.last_scroll_t = time.perf_counter()

                    # ── visual effects (both hands) ────────────────────────
                    palm = (int(lm[0].x * cam_w), int(lm[0].y * cam_h))
                    if gesture == Gesture.OPEN_PALM:
                        VisualEffect.draw_mandala(frame, palm, 140, PALM_COLOR)
                    elif gesture == Gesture.FIST:
                        VisualEffect.draw_magical_circle(frame, palm, 60, accent)

                    # Gesture label (only non-pinch, pinch shown via circle)
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
        print("Tracker stopped.")


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Change camera_id if your webcam is not at index 0 (run test.py to find it)
    HandTracker(camera_id=2).run()

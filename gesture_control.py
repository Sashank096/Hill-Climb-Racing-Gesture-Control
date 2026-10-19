"""
Hill Climb Racing - Hand Gesture Control (with custom background)
-----------------------------------------------------------------
Open palm (5 fingers)   -> GAS   (holds RIGHT arrow)
Closed fist (0 fingers) -> BRAKE (holds LEFT arrow)
Anything else           -> release both keys

Keys in the camera window:
  q = quit
  b = background ON/OFF

Put your background photo in this folder and name it: background.jpg
"""

import math
import os
import time
from collections import Counter, deque

import cv2
import mediapipe as mp
import numpy as np
from pynput.keyboard import Controller, Key

# ---------------- Settings ----------------
CAMERA_INDEX = 0              # change to 1 if the wrong camera opens
GAS_KEY = Key.right           # BlueStacks maps Gas -> Right arrow
BRAKE_KEY = Key.left          # BlueStacks maps Brake -> Left arrow
SMOOTHING_FRAMES = 5          # majority vote over last N frames
START_DELAY = 5               # seconds to click on the BlueStacks window
BACKGROUND_PATH = "background.jpg"   # your background photo
# ------------------------------------------

keyboard = Controller()
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
mp_seg = mp.solutions.selfie_segmentation

TIPS = [8, 12, 16, 20]        # index, middle, ring, pinky fingertips
PIPS = [6, 10, 14, 18]        # joint below each fingertip


def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def count_fingers(lm):
    """Return number of raised fingers (0-5) from 21 hand landmarks."""
    count = 0
    for tip, pip in zip(TIPS, PIPS):
        if lm[tip].y < lm[pip].y:
            count += 1
    if dist(lm[4], lm[17]) > dist(lm[3], lm[17]):   # thumb
        count += 1
    return count


class KeyState:
    """Remembers which key is held so we only press/release on changes."""

    def __init__(self):
        self.held = None

    def set(self, key):
        if key == self.held:
            return
        if self.held is not None:
            keyboard.release(self.held)
        if key is not None:
            keyboard.press(key)
        self.held = key

    def release_all(self):
        self.set(None)


def load_background():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, BACKGROUND_PATH)
    img = cv2.imread(path)
    if img is None:
        print(f"Background '{BACKGROUND_PATH}' not found in this folder. "
              "Running with normal camera background.")
    else:
        print("Background loaded. Press 'b' to turn it on/off.")
    return img


def apply_background(frame, mask_result, bg_resized):
    """Keep the person, replace everything else with the background image."""
    mask = mask_result.segmentation_mask
    mask = cv2.GaussianBlur(mask, (7, 7), 0)               # soft edges
    condition = np.stack((mask,) * 3, axis=-1) > 0.55
    return np.where(condition, frame, bg_resized)


def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("Could not open camera. Try changing CAMERA_INDEX.")
        return

    bg_original = load_background()
    bg_resized = None
    bg_on = bg_original is not None

    print(f"Starting in {START_DELAY}s - click on the BlueStacks game window now!")
    time.sleep(START_DELAY)

    keys = KeyState()
    history = deque(maxlen=SMOOTHING_FRAMES)

    with mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    ) as hands, mp_seg.SelfieSegmentation(model_selection=1) as seg:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)                      # mirror view
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Hand detection runs on the original frame
            result = hands.process(rgb)

            # Background replacement
            if bg_on:
                h, w = frame.shape[:2]
                if bg_resized is None or bg_resized.shape[:2] != (h, w):
                    bg_resized = cv2.resize(bg_original, (w, h))
                seg_result = seg.process(rgb)
                frame = apply_background(frame, seg_result, bg_resized).astype(np.uint8)

            fingers = None
            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)
                fingers = count_fingers(hand.landmark)

            history.append(fingers)
            stable = Counter(history).most_common(1)[0][0]

            if stable == 5:
                keys.set(GAS_KEY)
                action = "GAS"
            elif stable == 0:
                keys.set(BRAKE_KEY)
                action = "BRAKE"
            else:
                keys.release_all()
                action = "NEUTRAL"

            cv2.putText(frame, f"Fingers: {stable if stable is not None else '-'}",
                        (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, action, (10, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
            cv2.imshow("Camera Feed", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("b") and bg_original is not None:
                bg_on = not bg_on

    keys.release_all()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

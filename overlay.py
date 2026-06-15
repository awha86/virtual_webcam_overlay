"""
Virtual Webcam Overlay
Adds dynamic text overlay to your webcam and exposes it as a virtual camera.
Update overlay text live via HTTP POST.

Usage:
    python overlay.py
    python overlay.py --port 5123 --cam 0 --width 1280 --height 720 --fps 30

Update overlay:
    curl -X POST http://localhost:5123/overlay -H "Content-Type: application/json" \
         -d '{"text": "Hello Teams!"}'
"""

import argparse
import threading
import time

import cv2
import numpy as np
import pyvirtualcam
import uvicorn
from fastapi import FastAPI
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared state (thread-safe)
# ---------------------------------------------------------------------------

class OverlayState:
    def __init__(self):
        self._lock = threading.Lock()
        self._text = "Hello, Teams!"
        self._position = "bottom"

    @property
    def text(self):
        with self._lock:
            return self._text

    @text.setter
    def text(self, value: str):
        with self._lock:
            self._text = value

    @property
    def position(self):
        with self._lock:
            return self._position

    @position.setter
    def position(self, value: str):
        with self._lock:
            self._position = value


state = OverlayState()


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

api = FastAPI(title="Webcam Overlay API")


class OverlayUpdate(BaseModel):
    text: str
    position: str = "bottom"  # "top" or "bottom"


@api.post("/overlay")
def update_overlay(body: OverlayUpdate):
    state.text = body.text
    state.position = body.position
    return {"status": "ok", "text": body.text, "position": body.position}


@api.get("/overlay")
def get_overlay():
    return {"text": state.text, "position": state.position}


def _run_api(port: int):
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Overlay rendering
# ---------------------------------------------------------------------------

# Cache the font so we don't reload it every frame
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _font_cache:
        for path in [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/consola.ttf",
        ]:
            try:
                _font_cache[size] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        else:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def render_overlay(frame_bgr: np.ndarray, text: str, position: str) -> np.ndarray:
    """Composit text bar onto a BGR OpenCV frame. Returns BGR."""
    if not text:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    font_size = max(24, h // 25)
    font = _get_font(font_size)

    # Convert to PIL RGBA
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb).convert("RGBA")

    # Measure text
    dummy = ImageDraw.Draw(img)
    bbox = dummy.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    padding = 16
    bar_h = text_h + padding * 2

    # Semi-transparent black bar with white text
    bar = Image.new("RGBA", (w, bar_h), (0, 0, 0, 160))
    bar_draw = ImageDraw.Draw(bar)
    text_x = (w - text_w) // 2
    text_y = padding - bbox[1]
    bar_draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 240))

    # Paste bar onto frame
    bar_y = 0 if position == "top" else h - bar_h
    img.paste(bar, (0, bar_y), bar)

    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# Main camera loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Virtual Webcam Overlay")
    parser.add_argument("--port", type=int, default=5123, help="API port (default 5123)")
    parser.add_argument("--cam", type=int, default=0, help="Webcam device index (default 0)")
    parser.add_argument("--width", type=int, default=1280, help="Requested width")
    parser.add_argument("--height", type=int, default=720, help="Requested height")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS (default 30)")
    parser.add_argument("--preview", action="store_true", help="Show local preview window")
    args = parser.parse_args()

    # Start HTTP API in background thread
    api_thread = threading.Thread(target=_run_api, args=(args.port,), daemon=True)
    api_thread.start()
    print(f"[API]  http://localhost:{args.port}")
    print(f"       POST /overlay  {{\"text\": \"...\", \"position\": \"top|bottom\"}}")
    print(f"       GET  /overlay  → current state")

    # Open physical webcam
    cap = cv2.VideoCapture(args.cam, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    if not cap.isOpened():
        print(f"[ERROR] Webcam index {args.cam} could not be opened.")
        return

    ret, probe = cap.read()
    if not ret:
        print("[ERROR] Could not read a frame from webcam.")
        cap.release()
        return

    actual_h, actual_w = probe.shape[:2]
    print(f"[CAM]  Webcam opened: {actual_w}×{actual_h}")

    # Open virtual camera (Unity Capture)
    try:
        vcam = pyvirtualcam.Camera(
            width=actual_w,
            height=actual_h,
            fps=args.fps,
            backend="unitycapture",
        )
    except RuntimeError as exc:
        print(f"[ERROR] Virtual camera failed: {exc}")
        print("        → Er Unity Capture-driveren installeret? Se README.md")
        cap.release()
        return

    print(f"[VCAM] Device: {vcam.device}")
    print(f"[RUN]  Kører – tryk Ctrl+C for at stoppe\n")

    target_dt = 1.0 / args.fps

    try:
        while True:
            t0 = time.perf_counter()

            ret, frame = cap.read()
            if not ret:
                continue

            if frame.shape[1] != actual_w or frame.shape[0] != actual_h:
                frame = cv2.resize(frame, (actual_w, actual_h))

            # Composit overlay
            frame = render_overlay(frame, state.text, state.position)

            # Send to virtual camera (expects RGB)
            vcam.send(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            if args.preview:
                cv2.imshow("Webcam Overlay Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            # Throttle
            sleep = target_dt - (time.perf_counter() - t0)
            if sleep > 0:
                time.sleep(sleep)

    except KeyboardInterrupt:
        print("\n[INFO] Lukker ned...")
    finally:
        cap.release()
        vcam.close()
        if args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

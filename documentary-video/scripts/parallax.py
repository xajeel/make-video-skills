"""Free 2.5D "3D camera move" from one still image (runs on CPU, ~30 s per 7 s of 1080p).

Depth Anything V2 Small (ONNX) estimates how far away each part of the picture is, then the frame is
warped so near things move more than far things: a camera push-in and/or slide with real parallax.
Only the camera moves - people, water and clouds stay still (use Flow clips for real motion).

Needs the venv + model from setup_3d.sh. assemble.py calls this for ~30% of the non-Flow scenes.

  python parallax.py <image> <out.mp4> [--secs 6.5 | --frames N] [--move push_slide|push|slide_right|slide_left]
                     [--size 1920x1080] [--fps 30] [--crf 19] [--preset medium] [--depth-out depth.png]
"""
import argparse, os, pathlib, subprocess
import numpy as np, cv2, onnxruntime as ort

HOME = pathlib.Path(os.environ.get("DOCVID_HOME", pathlib.Path.home() / ".local/share/documentary-video"))
MODEL = HOME / "models" / "depth_anything_v2_small.onnx"
MOVES = ["push_slide", "push", "slide_right", "slide_left"]
STRENGTH = {"push_slide": 1.7, "push": 1.7, "slide_right": 1.6, "slide_left": 1.6}   # tuned on 6.5 s scenes
MARGIN = 1.12   # canvas is 12% larger than the frame so the move never shows an edge


def depth_map(rgb, model=MODEL):
    """rgb float32 HxWx3 in 0..1 -> depth 0..1 (bigger = closer)."""
    ih, iw = 518, int(round(518 * rgb.shape[1] / rgb.shape[0] / 14)) * 14
    x = cv2.resize(rgb, (iw, ih), interpolation=cv2.INTER_CUBIC)
    x = ((x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]).transpose(2, 0, 1)[None].astype(np.float32)
    sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    d = sess.run(None, {sess.get_inputs()[0].name: x})[0].squeeze()
    d = (d - np.percentile(d, 2)) / (np.percentile(d, 98) - np.percentile(d, 2) + 1e-6)
    return np.clip(d, 0, 1).astype(np.float32)


def render(image, out, frames, move="push_slide", W=1920, H=1080, fps=30, crf=19, preset="medium", depth_out=None):
    src = cv2.imread(str(image))[:, :, ::-1].astype(np.float32) / 255
    # crop the source to the output aspect first (Flow images are 1376x768, not exactly 16:9)
    ih, iw = src.shape[:2]; ar = W / H
    if iw / ih > ar: c = int(round(ih * ar)); src = src[:, (iw - c) // 2:(iw - c) // 2 + c]
    else: c = int(round(iw / ar)); src = src[(ih - c) // 2:(ih - c) // 2 + c]
    d = depth_map(src)
    cw, ch = int(W * MARGIN), int(H * MARGIN)
    img = cv2.resize(src, (cw, ch), interpolation=cv2.INTER_LANCZOS4)
    dep = cv2.resize(d, (cw, ch), interpolation=cv2.INTER_CUBIC)
    # grow near objects a little and soften the map, so foreground edges move as one piece (less tearing)
    dep = cv2.GaussianBlur(cv2.dilate(dep, np.ones((9, 9), np.uint8)), (0, 0), 6)
    if depth_out: cv2.imwrite(str(depth_out), (dep * 255).astype(np.uint8))

    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = cw / 2, ch / 2
    gx, gy = xs - W / 2, ys - H / 2
    D = cv2.remap(dep, gx + cx, gy + cy, cv2.INTER_LINEAR)
    s = STRENGTH[move]
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                           "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for i in range(frames):
        t = i / max(frames - 1, 1)
        e = float(0.75 * t + 0.25 * (0.5 - 0.5 * np.cos(np.pi * t)))   # mostly steady: visible from the first second
        if move == "push":
            zoom = 1 + s * e * (0.035 + 0.06 * D)
            sx, sy = gx / zoom, gy / zoom - s * e * 10 * D
        elif move == "push_slide":
            zoom = 1 + s * e * (0.03 + 0.05 * D)
            sx, sy = gx / zoom + s * (e - 0.5) * (25 + 60 * D), gy / zoom - s * e * 8 * D
        else:
            dirn = 1 if move == "slide_right" else -1
            zoom = 1 + 0.03 * s
            sx, sy = gx / zoom + dirn * s * (e - 0.5) * (30 + 70 * D), gy / zoom
        frame = cv2.remap(img, (sx + cx).astype(np.float32), (sy + cy).astype(np.float32), cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REFLECT)
        ff.stdin.write((np.clip(frame, 0, 1) * 255).astype(np.uint8).tobytes())
    ff.stdin.close(); ff.wait()
    if ff.returncode: raise SystemExit(f"ffmpeg failed for {image}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("out")
    ap.add_argument("--secs", type=float, default=6.5); ap.add_argument("--frames", type=int)
    ap.add_argument("--move", default="push_slide", choices=MOVES)
    ap.add_argument("--size", default="1920x1080"); ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crf", type=int, default=19); ap.add_argument("--preset", default="medium")
    ap.add_argument("--depth-out")
    a = ap.parse_args()
    W, H = map(int, a.size.split("x"))
    render(a.image, a.out, a.frames or int(round(a.secs * a.fps)), a.move, W, H, a.fps, a.crf, a.preset, a.depth_out)
    print(a.out)

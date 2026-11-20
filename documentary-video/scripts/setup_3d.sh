#!/bin/sh
# One-time setup for the free 3D camera move (parallax.py): a small venv + the Depth Anything V2 Small ONNX model (~99 MB).
# Everything goes to ~/.local/share/documentary-video (override with DOCVID_HOME). Safe to re-run.
set -e
HOME_DIR="${DOCVID_HOME:-$HOME/.local/share/documentary-video}"
VENV="$HOME_DIR/depthenv"; MODEL="$HOME_DIR/models/depth_anything_v2_small.onnx"
mkdir -p "$HOME_DIR/models"
[ -x "$VENV/bin/python" ] || uv venv -q "$VENV"
uv pip install -q --python "$VENV/bin/python" onnxruntime opencv-python-headless numpy huggingface_hub
if [ ! -s "$MODEL" ]; then
  "$VENV/bin/python" -I -c "
from huggingface_hub import hf_hub_download; import shutil
p = hf_hub_download('onnx-community/depth-anything-v2-small', 'onnx/model.onnx')
shutil.copy(p, '$MODEL')"
fi
"$VENV/bin/python" -I -c "import onnxruntime, cv2, numpy" && echo "3D move ready: $VENV, $MODEL"

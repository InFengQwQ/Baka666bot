"""Character matting with the isnet-anime graph through onnxruntime."""

import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter

MODEL = Path(__file__).resolve().parent / "assets" / "isnet-anime.onnx"

_session: ort.InferenceSession | None = None
_lock = threading.Lock()


def _session_lazy() -> ort.InferenceSession:
    global _session
    with _lock:
        if _session is None:
            if not MODEL.is_file():
                raise FileNotFoundError(f"{MODEL.name} is missing; run scripts/fetch-assets.py")
            options = ort.SessionOptions()
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _session = ort.InferenceSession(
                str(MODEL), sess_options=options, providers=["CPUExecutionProvider"]
            )
    return _session


def cutout(image: Image.Image) -> Image.Image:
    """Return the image with an alpha mask; the model graph is fixed at its own input size."""
    session = _session_lazy()
    model_input = session.get_inputs()[0]
    width, height = model_input.shape[3], model_input.shape[2]

    rgb = image.convert("RGB").resize((width, height), Image.LANCZOS)
    tensor = np.asarray(rgb, dtype=np.float32) / 255.0 - 0.5
    tensor = np.transpose(tensor, (2, 0, 1))[None]

    prediction = np.squeeze(session.run(None, {model_input.name: tensor})[0])
    mask = Image.fromarray((prediction * 255).astype(np.uint8), "L")
    mask = mask.resize(image.size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.0))

    result = image.convert("RGBA")
    result.putalpha(mask)
    return result

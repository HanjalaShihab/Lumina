from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as ort
from PIL import Image


@dataclass(frozen=True)
class OnnxSRConfig:
    # Placeholder: we will use a built-in SR ONNX model from a URL at runtime.
    # The project currently has no ONNX model file committed.
    model_url: str
    model_filename: str
    input_size: tuple[int, int] | None = None  # (w, h) optional


# NOTE: Real SR ONNX model selection will be wired in once we choose a model.
# For now, we keep this module scaffolded.
DEFAULT_CONFIG = OnnxSRConfig(
    model_url="",
    model_filename="",
    input_size=None,
)


class OnnxSR:
    def __init__(self, config: OnnxSRConfig):
        self.config = config
        self.session: Optional[ort.InferenceSession] = None

    def _ensure_session(self) -> None:
        if self.session is not None:
            return
        if not self.config.model_filename:
            raise RuntimeError(
                "ONNX SR model_filename is not set. "
                "Configure an ONNX model in enhancer/ai_engine.py before using."
            )
        model_path = Path("media/models") / self.config.model_filename
        if not model_path.exists():
            raise RuntimeError(f"ONNX model not found: {model_path}")

        providers = ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(model_path), providers=providers)

    @staticmethod
    def _preprocess(pil: Image.Image) -> np.ndarray:
        pil = pil.convert("RGB")
        arr = np.asarray(pil).astype(np.float32)
        # Normalize to [0,1]
        arr = arr / 255.0
        # NHWC -> NCHW
        arr = np.transpose(arr, (2, 0, 1))[None, ...]
        return arr

    @staticmethod
    def _postprocess(pred: np.ndarray, out_w: int, out_h: int) -> Image.Image:
        # Expect pred in NCHW or NHWC depending on model.
        if pred.ndim == 4:
            # Try NCHW
            if pred.shape[1] in (1, 3):
                img = pred[0]
                img = np.transpose(img, (1, 2, 0))
            else:
                # Assume NHWC
                img = pred[0]
        else:
            img = pred

        img = np.clip(img, 0.0, 1.0)
        img = (img * 255.0).astype(np.uint8)
        out = Image.fromarray(img)
        if out.size != (out_w, out_h):
            out = out.resize((out_w, out_h), resample=Image.BICUBIC)
        return out

    def enhance(self, image: Image.Image, scale: int = 2) -> Image.Image:
        self._ensure_session()
        assert self.session is not None

        in_w, in_h = image.size
        out_w, out_h = in_w * scale, in_h * scale

        x = self._preprocess(image)
        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: x})
        pred = outputs[0]
        return self._postprocess(pred, out_w=out_w, out_h=out_h)


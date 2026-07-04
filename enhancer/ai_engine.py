from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from django.core.files.storage import default_storage
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .onnx_sr import OnnxSR, OnnxSRConfig


MODEL_NAME = "Lumina Precision Enhance v2"
MODEL_DIR = Path("media/models")

# Lazily created singleton for ONNX super-resolution.
_ONNX_SR: OnnxSR | None = None


def _get_onnx_sr() -> OnnxSR | None:
    global _ONNX_SR
    if _ONNX_SR is not None:
        return _ONNX_SR

    model_file = _find_onnx_model()
    if model_file is None:
        return None

    config = OnnxSRConfig(
        model_url="",
        model_filename=model_file.name,
        input_size=None,
    )
    try:
        _ONNX_SR = OnnxSR(config)
    except Exception:
        _ONNX_SR = None
    return _ONNX_SR


def _find_onnx_model() -> Path | None:
    models_path = Path(default_storage.path(MODEL_DIR))
    if not models_path.exists():
        return None
    models = sorted(models_path.glob("*.onnx"))
    return models[0] if models else None



def enhance_image(job, mode="ai"):
    source_path = Path(job.original.path)
    output_name = f"{source_path.stem}-{mode}-{uuid4().hex[:8]}.jpg"
    output_path = Path("uploads/enhanced") / output_name
    absolute_output = Path(default_storage.path(output_path))
    absolute_output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if mode == "manual":
            enhanced, metrics = _manual_enhance(image, job)
        elif mode == "ai":
            enhanced, metrics = _ai_model_enhance(image, job)
        else:
            enhanced, metrics = _precision_enhance(image)
        enhanced.save(absolute_output, "JPEG", quality=97, optimize=True, progressive=True)

    job.enhanced.name = output_path.as_posix()
    job.notes = _describe_enhancement(mode, job, metrics)
    job.save()
    return job



def _ai_model_enhance(image, job):
    """Real AI path.

    Currently this repo has no committed ONNX model weights. We therefore:
    - attempt to load an ONNX SR model from `media/models/` if present
    - if not present, fall back to the classical pipeline

    This makes "AI mode" behave as real model inference when weights are available,
    while still keeping the app functional.
    """

    onnx_sr = _get_onnx_sr()
    if onnx_sr is None:
        enhanced, metrics = _precision_upscale_enhance(image, scale=2)
        metrics["ai_backend"] = "precision-upscale fallback"
        metrics["scale"] = 2
        return enhanced, metrics

    # Best-effort scale selection.
    scale = 2
    enhanced = onnx_sr.enhance(image, scale=scale)
    metrics = {
        "brightness": float(np.asarray(enhanced).mean()),
        "contrast": float(np.asarray(enhanced).std()),
        "shadow": 0.0,
        "highlight": 0.0,
        "ai_backend": "onnx_sr",
        "scale": scale,
    }
    return enhanced, metrics


def _precision_upscale_enhance(image, scale=2):
    width, height = image.size
    upscaled = image.resize((width * scale, height * scale), resample=Image.Resampling.LANCZOS)
    enhanced, metrics = _precision_enhance(upscaled)
    return enhanced, metrics


def _precision_enhance(image):
    rgb = np.asarray(image).astype(np.float32)
    metrics = _measure(rgb)


    balanced = _gray_world_white_balance(rgb)
    recovered = _recover_tone(balanced)
    local = _adaptive_luma_contrast(recovered)
    vibrant = _smart_vibrance(local)
    cleaned = _denoise(vibrant)
    sharpened = _edge_aware_sharpen(cleaned)
    final = _protect_extremes(sharpened, rgb)

    return Image.fromarray(_to_uint8(final)), metrics


def _manual_enhance(image, job):
    image = ImageEnhance.Brightness(image).enhance(job.brightness)
    image = ImageEnhance.Contrast(image).enhance(job.contrast)
    image = ImageEnhance.Color(image).enhance(job.saturation)
    image = ImageEnhance.Sharpness(image).enhance(job.sharpness)
    image = image.filter(ImageFilter.UnsharpMask(radius=1.35, percent=115, threshold=3))
    return image, _measure(np.asarray(image).astype(np.float32))


def _gray_world_white_balance(rgb):
    channel_means = rgb.reshape(-1, 3).mean(axis=0)
    neutral = channel_means.mean()
    gains = neutral / np.maximum(channel_means, 1.0)
    gains = np.clip(gains, 0.82, 1.22)
    return np.clip(rgb * gains, 0, 255)


def _recover_tone(rgb):
    low = np.percentile(rgb, 0.7, axis=(0, 1))
    high = np.percentile(rgb, 99.3, axis=(0, 1))
    stretched = (rgb - low) * (255.0 / np.maximum(high - low, 1.0))
    stretched = np.clip(stretched, 0, 255)

    luma = _luma(stretched)
    shadows = np.clip((92 - luma) / 92, 0, 1)[..., None]
    highlights = np.clip((luma - 188) / 67, 0, 1)[..., None]
    shadow_lift = stretched + (255 - stretched) * shadows * 0.16
    highlight_guard = shadow_lift * (1 - highlights * 0.10)
    return np.clip(highlight_guard, 0, 255)


def _adaptive_luma_contrast(rgb):
    lab = cv2.cvtColor(_to_uint8(rgb), cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.15, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    merged = cv2.merge((l_channel, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB).astype(np.float32)


def _smart_vibrance(rgb):
    hsv = cv2.cvtColor(_to_uint8(rgb), cv2.COLOR_RGB2HSV).astype(np.float32)
    saturation = hsv[..., 1]
    value = hsv[..., 2]
    saturation_boost = 1.0 + (1 - saturation / 255.0) * 0.22
    value_guard = 1.0 - np.clip((value - 220) / 35, 0, 0.38)
    hsv[..., 1] = np.clip(saturation * saturation_boost * value_guard, 0, 255)
    return cv2.cvtColor(_to_uint8(hsv), cv2.COLOR_HSV2RGB).astype(np.float32)


def _denoise(rgb):
    bgr = cv2.cvtColor(_to_uint8(rgb), cv2.COLOR_RGB2BGR)
    denoised = cv2.fastNlMeansDenoisingColored(bgr, None, 3, 3, 7, 21)
    return cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB).astype(np.float32)


def _edge_aware_sharpen(rgb):
    base = cv2.bilateralFilter(_to_uint8(rgb), 7, 36, 36).astype(np.float32)
    detail = rgb - base
    luma = _luma(rgb)
    edge_strength = cv2.Laplacian(_to_uint8(luma), cv2.CV_32F)
    edge_mask = np.clip(np.abs(edge_strength) / 32.0, 0, 1)[..., None]
    sharpened = rgb + detail * (0.95 * edge_mask + 0.20)
    return np.clip(sharpened, 0, 255)


def _protect_extremes(enhanced, original):
    original_luma = _luma(original)
    bright_mask = np.clip((original_luma - 232) / 23, 0, 1)[..., None]
    dark_mask = np.clip((18 - original_luma) / 18, 0, 1)[..., None]
    protected = enhanced * (1 - bright_mask * 0.35) + original * (bright_mask * 0.35)
    protected = protected * (1 - dark_mask * 0.25) + original * (dark_mask * 0.25)
    return np.clip(protected, 0, 255)


def _measure(rgb):
    luma = _luma(rgb)
    return {
        "brightness": float(luma.mean()),
        "contrast": float(luma.std()),
        "shadow": float(np.percentile(luma, 5)),
        "highlight": float(np.percentile(luma, 95)),
    }


def _describe_enhancement(mode, job, metrics):
    if mode == "manual":
        return (
            f"Manual mode used brightness {job.brightness:.2f}, contrast {job.contrast:.2f}, "
            f"sharpness {job.sharpness:.2f}, saturation {job.saturation:.2f}."
        )
    backend = metrics.get("ai_backend", "classical precision")
    scale = metrics.get("scale")
    scale_text = f" Output scale {scale}x." if scale else ""
    return (
        f"{MODEL_NAME} used {backend}. It applied white balance, percentile tone mapping, "
        f"local contrast, shadow/highlight recovery, denoise, vibrance, and edge-aware sharpening."
        f"{scale_text} Input brightness {metrics['brightness']:.0f}, contrast {metrics['contrast']:.0f}."
    )


def _luma(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _to_uint8(array):
    return np.clip(array, 0, 255).astype(np.uint8)

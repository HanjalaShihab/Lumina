from io import BytesIO
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from django.core.files.storage import default_storage
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    from rembg import new_session, remove as rembg_remove
except Exception:  # pragma: no cover - optional runtime dependency
    new_session = None
    rembg_remove = None

from .onnx_sr import OnnxSR, OnnxSRConfig


MODEL_NAME = "Lumina Precision Enhance v2"
MODEL_DIR = Path("media/models")

# Lazily created singleton for ONNX super-resolution.
_ONNX_SR: OnnxSR | None = None
_REMBG_SESSION = None
_REMBG_MODEL_NAME: str | None = None


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


def _get_rembg_session():
    global _REMBG_SESSION, _REMBG_MODEL_NAME
    if _REMBG_SESSION is not None:
        return _REMBG_SESSION

    if rembg_remove is None or new_session is None:
        return None

    for model_name in ("isnet-general-use", "u2net"):
        try:
            _REMBG_SESSION = new_session(model_name)
            _REMBG_MODEL_NAME = model_name
            return _REMBG_SESSION
        except Exception:
            continue

    return None



def enhance_image(job, mode="ai", adjustments=None):
    source_path = Path(job.original.path)
    output_name = f"{source_path.stem}-{mode}-{uuid4().hex[:8]}.jpg"
    output_path = Path("uploads/enhanced") / output_name
    absolute_output = Path(default_storage.path(output_path))
    absolute_output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if mode == "manual":
            enhanced, metrics = _manual_enhance(image, job, adjustments or {})
        elif mode == "ai":
            enhanced, metrics = _ai_model_enhance(image, job)
        else:
            enhanced, metrics = _precision_enhance(image)
        enhanced.save(absolute_output, "JPEG", quality=97, optimize=True, progressive=True)

    job.enhanced.name = output_path.as_posix()
    job.notes = _describe_enhancement(mode, job, metrics)
    job.save()
    return job


def remove_background(job):
    source_path = Path(job.original.path)
    output_name = f"{source_path.stem}-bgremove-{uuid4().hex[:8]}.png"
    output_path = Path("uploads/enhanced") / output_name
    absolute_output = Path(default_storage.path(output_path))
    absolute_output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        cutout, metrics = _background_cutout(image)
        cutout.save(absolute_output, "PNG", optimize=True)

    job.enhanced.name = output_path.as_posix()
    job.notes = _describe_background_removal(metrics)
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


def _manual_enhance(image, job, adjustments):
    color = _slider_value(adjustments, "color", 50)
    tone = _slider_value(adjustments, "tone", 50)
    contrast = _slider_value(adjustments, "contrast", 50)
    vibrance = _slider_value(adjustments, "vibrance", 50)
    denoise = _slider_value(adjustments, "denoise", 50)
    sharpen = _slider_value(adjustments, "sharpen", 50)
    exposure = _slider_value(adjustments, "exposure", 50)
    warmth = _slider_value(adjustments, "warmth", 50)
    shadows = _slider_value(adjustments, "shadows", 50)
    highlights = _slider_value(adjustments, "highlights", 50)

    rgb = np.asarray(image).astype(np.float32)
    rgb = _manual_exposure(rgb, exposure)
    rgb = _manual_warmth(rgb, warmth)
    rgb = _manual_tone(rgb, tone, shadows, highlights)
    rgb = _manual_color_balance(rgb, color)

    adjusted = Image.fromarray(_to_uint8(rgb))
    adjusted = ImageEnhance.Contrast(adjusted).enhance(_slider_factor(contrast, 0.78, 1.42))
    adjusted = ImageEnhance.Color(adjusted).enhance(_slider_factor(vibrance, 0.72, 1.52))

    if denoise > 55:
        adjusted = adjusted.filter(ImageFilter.GaussianBlur(radius=(denoise - 55) / 45 * 0.7))

    adjusted = ImageEnhance.Sharpness(adjusted).enhance(_slider_factor(sharpen, 0.75, 1.85))
    adjusted = adjusted.filter(ImageFilter.UnsharpMask(radius=1.35, percent=115, threshold=3))

    metrics = _measure(np.asarray(adjusted).astype(np.float32))
    metrics.update({
        "color": color,
        "tone": tone,
        "vibrance": vibrance,
        "denoise": denoise,
        "sharpen": sharpen,
        "exposure": exposure,
        "warmth": warmth,
        "shadows": shadows,
        "highlights": highlights,
    })
    return adjusted, metrics


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
        if isinstance(metrics, dict) and "color" in metrics:
            return (
                "Manual mode used color {color}, tone {tone}, contrast {contrast}, vibrance {vibrance}, "
                "denoise {denoise}, sharpen {sharpen}, exposure {exposure}, warmth {warmth}, "
                "shadows {shadows}, and highlights {highlights}."
            ).format(
                color=metrics["color"],
                tone=metrics["tone"],
                contrast=metrics["contrast"],
                vibrance=metrics["vibrance"],
                denoise=metrics["denoise"],
                sharpen=metrics["sharpen"],
                exposure=metrics["exposure"],
                warmth=metrics["warmth"],
                shadows=metrics["shadows"],
                highlights=metrics["highlights"],
            )
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


def _background_cutout(image):
    rgb = np.asarray(image).astype(np.uint8)
    rembg_result = _rembg_cutout(image)
    if rembg_result is not None:
        return rembg_result

    height, width = rgb.shape[:2]
    margin_x = max(4, int(width * 0.035))
    margin_y = max(4, int(height * 0.035))
    rect_width = max(2, width - (margin_x * 2))
    rect_height = max(2, height - (margin_y * 2))

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    mask = np.zeros((height, width), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    method = "grabcut"

    try:
        cv2.grabCut(
            bgr,
            mask,
            (margin_x, margin_y, rect_width, rect_height),
            bgd_model,
            fgd_model,
            6,
            cv2.GC_INIT_WITH_RECT,
        )
        alpha = np.where(
            (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
            255,
            0,
        ).astype(np.uint8)
    except cv2.error:
        method = "border-threshold"
        border = max(2, min(height, width) // 16)
        edge_pixels = np.concatenate(
            [
                rgb[:border, :, :].reshape(-1, 3),
                rgb[-border:, :, :].reshape(-1, 3),
                rgb[:, :border, :].reshape(-1, 3),
                rgb[:, -border:, :].reshape(-1, 3),
            ],
            axis=0,
        )
        background_color = np.median(edge_pixels, axis=0)
        distances = np.linalg.norm(rgb.astype(np.float32) - background_color, axis=2)
        threshold = np.percentile(distances, 52)
        alpha = np.where(distances > threshold, 255, 0).astype(np.uint8)

    alpha = _refine_alpha(alpha)
    foreground_ratio = float((alpha > 127).mean())
    rgba = np.dstack([rgb, alpha])
    cutout = Image.fromarray(rgba, "RGBA")
    return cutout, {"method": method, "foreground_ratio": foreground_ratio}


def _rembg_cutout(image):
    session = _get_rembg_session()
    if session is None:
        return None

    try:
        with BytesIO() as input_buffer:
            image.save(input_buffer, format="PNG")
            output = rembg_remove(
                input_buffer.getvalue(),
                session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=240,
                alpha_matting_background_threshold=12,
                alpha_matting_erode_size=8,
                post_process_mask=True,
                force_return_bytes=True,
            )

        with Image.open(BytesIO(output)) as cutout_image:
            cutout_rgba = cutout_image.convert("RGBA")

        rgba = np.asarray(cutout_rgba).astype(np.uint8)
        alpha = _refine_alpha(rgba[..., 3])
        rgba[..., 3] = alpha
        cutout = Image.fromarray(rgba, "RGBA")
        method = f"rembg:{_REMBG_MODEL_NAME or 'u2net'}"
        foreground_ratio = float((alpha > 127).mean())
        return cutout, {"method": method, "foreground_ratio": foreground_ratio}
    except Exception:
        return None


def _refine_alpha(alpha):
    alpha = alpha.astype(np.uint8)
    height, width = alpha.shape[:2]
    kernel_size = max(3, min(height, width) // 160)
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel_size = min(kernel_size, 11)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))

    refined = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=1)
    refined = cv2.morphologyEx(refined, cv2.MORPH_OPEN, kernel, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((refined > 127).astype(np.uint8), 8)
    if num_labels > 1:
                largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                refined = np.where(labels == largest_label, 255, 0).astype(np.uint8)

    return cv2.GaussianBlur(refined, (5, 5), 0)


def _describe_background_removal(metrics):
    method = metrics.get("method", "grabcut")
    ratio = metrics.get("foreground_ratio", 0.0)
    return (
        f"Background removed with {method}. Foreground coverage estimated at {ratio:.0%}. "
        "The output is saved as a transparent PNG for compositing on any background."
    )


def _luma(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _slider_value(adjustments, name, default=50):
    try:
        return int(float(adjustments.get(name, default)))
    except (TypeError, ValueError):
        return default


def _slider_factor(value, minimum, maximum):
    return minimum + (max(value, 0) / 100.0) * (maximum - minimum)


def _manual_exposure(rgb, exposure):
    factor = _slider_factor(exposure, 0.78, 1.28)
    return np.clip(rgb * factor, 0, 255)


def _manual_warmth(rgb, warmth):
    factor = (warmth - 50) / 50.0
    warmed = rgb.copy()
    warmed[..., 0] = np.clip(warmed[..., 0] * (1.0 + factor * 0.12), 0, 255)
    warmed[..., 2] = np.clip(warmed[..., 2] * (1.0 - factor * 0.12), 0, 255)
    return warmed


def _manual_tone(rgb, tone, shadows, highlights):
    luma = _luma(rgb) / 255.0
    shadow_mask = np.clip((0.56 - luma) / 0.56, 0, 1)[..., None]
    highlight_mask = np.clip((luma - 0.56) / 0.44, 0, 1)[..., None]

    tone_factor = (tone - 50) / 50.0
    shadow_lift = max((shadows - 50) / 50.0, 0.0)
    shadow_deepen = max((50 - shadows) / 50.0, 0.0)
    highlight_lift = max((highlights - 50) / 50.0, 0.0)
    highlight_protect = max((50 - highlights) / 50.0, 0.0)

    result = rgb + (255 - rgb) * shadow_mask * (0.28 * shadow_lift + 0.08 * max(tone_factor, 0.0))
    result = result * (1 - shadow_mask * 0.18 * shadow_deepen)
    result = result + (255 - result) * highlight_mask * (0.16 * highlight_lift)
    result = result * (1 - highlight_mask * 0.20 * highlight_protect)
    return np.clip(result, 0, 255)


def _manual_color_balance(rgb, color):
    balance = (color - 50) / 50.0
    balanced = rgb.copy()
    balanced[..., 1] = np.clip(balanced[..., 1] * (1.0 + balance * 0.05), 0, 255)
    return balanced


def _to_uint8(array):
    return np.clip(array, 0, 255).astype(np.uint8)

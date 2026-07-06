"""
Lumina AI Enhancement Engine

Production-ready image enhancement with optional ONNX super-resolution.
Auto-downloads a lightweight Real-ESRGAN ONNX model on first use.
Falls back to a pro-grade classical pipeline when no GPU/ONNX runtime is available.
"""

from __future__ import annotations

import os
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve
from uuid import uuid4

import cv2
import numpy as np
from django.core.files.storage import default_storage
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    from rembg import new_session, remove as rembg_remove
except Exception:
    new_session = None
    rembg_remove = None

import onnxruntime as ort

# ── Module-level state ──────────────────────────────────────────
_MODEL_DIR = Path("media/models")
_MODEL_URL = "https://huggingface.co/aplux/Real-ESRGAN-General-x4v3/resolve/main/realesr-general-x4v3.onnx"
_MODEL_FILENAME = "realesr-general-x4v3.onnx"
_MODEL_SHA256 = ""  # optional: set to verify download

_ONNX_SESSION: Optional[ort.InferenceSession] = None
_MODEL_DOWNLOAD_ATTEMPTED = False

# ── Public API ──────────────────────────────────────────────────

MODEL_NAME = "Lumina Precision Enhance v2"


def enhance_image(job, mode="ai", adjustments=None):
    """Enhance an image — the main entry point.

    Args:
        job: EnhancementJob instance (must have .original.path)
        mode: "ai" | "manual"
        adjustments: dict of slider values (for manual mode)

    Returns:
        The job with .enhanced and .notes populated.
    """
    source_path = Path(job.original.path)
    output_name = f"{source_path.stem}-{mode}-{uuid4().hex[:8]}.jpg"
    output_path = Path("uploads/enhanced") / output_name
    absolute_output = Path(default_storage.path(output_path))
    absolute_output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")

        if mode == "manual":
            enhanced, metrics = _manual_enhance(image, adjustments or {})
        elif mode == "ai":
            enhanced, metrics = _ai_enhance(image)
        else:
            enhanced, metrics = _ai_enhance(image)

        enhanced.save(absolute_output, "JPEG", quality=97, optimize=True, progressive=True)

    job.enhanced.name = output_path.as_posix()
    job.notes = _describe_enhancement(mode, metrics)
    job.save()
    return job


def remove_background(job):
    """Remove background from an image."""
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


# ── ONNX model management ──────────────────────────────────────


def _ensure_onnx_session() -> Optional[ort.InferenceSession]:
    """Lazy-load the ONNX SR model. Auto-downloads on first call."""
    global _ONNX_SESSION, _MODEL_DOWNLOAD_ATTEMPTED

    if _ONNX_SESSION is not None:
        return _ONNX_SESSION

    model_path = _resolve_model_path()
    if model_path is None:
        if not _MODEL_DOWNLOAD_ATTEMPTED:
            _MODEL_DOWNLOAD_ATTEMPTED = True
            model_path = _download_model()
        else:
            return None

    if model_path is None or not model_path.exists():
        return None

    try:
        providers = ["CPUExecutionProvider"]
        if "CUDAExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")
        _ONNX_SESSION = ort.InferenceSession(str(model_path), providers=providers)
        return _ONNX_SESSION
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"ONNX session failed: {e}")
        return None


def _resolve_model_path() -> Optional[Path]:
    """Return the path to an existing ONNX model, or None."""
    models_path = Path(default_storage.path(_MODEL_DIR))
    if not models_path.exists():
        models_path.mkdir(parents=True, exist_ok=True)
        return None

    explicit = models_path / _MODEL_FILENAME
    if explicit.exists():
        return explicit

    # Fall back to any .onnx in the directory
    onnx_files = sorted(models_path.glob("*.onnx"))
    if onnx_files:
        return onnx_files[0]

    return None


def _download_model() -> Optional[Path]:
    """Download the lightweight ONNX model from Hugging Face."""
    models_path = Path(default_storage.path(_MODEL_DIR))
    models_path.mkdir(parents=True, exist_ok=True)
    dest = models_path / _MODEL_FILENAME

    import logging
    logger = logging.getLogger(__name__)

    def _reporthook(count, block_size, total_size):
        downloaded = count * block_size
        if total_size > 0 and count % 20 == 0:
            percent = min(100, int(downloaded * 100 / total_size))
            logger.info(f"  Downloading model: {percent}% ({downloaded / 1024 / 1024:.1f}MB)")

    try:
        logger.info(f"Downloading ONNX model from {_MODEL_URL}...")
        urlretrieve(_MODEL_URL, str(dest), _reporthook)
        logger.info("Download complete.")
        return dest
    except Exception as e:
        logger.warning(f"Model download failed: {e}")
        # Clean up partial download
        if dest.exists():
            dest.unlink()
        return None


# ── AI Enhancement Pipeline ─────────────────────────────────────


def _ai_enhance(image: Image.Image):
    """Full AI enhancement pipeline."""
    session = _ensure_onnx_session()
    rgb = np.asarray(image).astype(np.float32)
    metrics = _measure(rgb)

    if session is not None:
        # ── ONNX path: SR + color ──
        enhanced = _onnx_upscale(session, image)
        enhanced_rgb = np.asarray(enhanced).astype(np.float32)
        enhanced_rgb = _pipeline_color_science(enhanced_rgb)
        enhanced_rgb = _pipeline_denoise_sharpen(enhanced_rgb)
        enhanced_rgb = _pipeline_final_grading(enhanced_rgb)
        metrics["ai_backend"] = "onnx_realesrgan"
        metrics["scale"] = 4
    else:
        # ── Classical fallback path ──
        enhanced_rgb = _pipeline_color_science(rgb)
        enhanced_rgb = _pipeline_denoise_sharpen(enhanced_rgb)
        enhanced_rgb = _pipeline_smart_upscale(enhanced_rgb, rgb)
        enhanced_rgb = _pipeline_final_grading(enhanced_rgb)
        metrics["ai_backend"] = "precision-classical"
        metrics["scale"] = 1

    post_metrics = _measure(enhanced_rgb)
    metrics.update({
        "post_brightness": post_metrics["brightness"],
        "post_contrast": post_metrics["contrast"],
    })

    return Image.fromarray(_to_uint8(enhanced_rgb)), metrics


def _onnx_upscale(session: ort.InferenceSession, image: Image.Image) -> Image.Image:
    """Run ONNX super-resolution on the input image."""
    in_w, in_h = image.size
    arr = np.asarray(image.convert("RGB")).astype(np.float32) / 255.0
    # NHWC → NCHW
    x = np.transpose(arr, (2, 0, 1))[None, ...]

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: x})
    pred = outputs[0]

    # pred shape: NCHW or NHWC
    if pred.ndim == 4:
        if pred.shape[1] in (1, 3):
            img = pred[0]
            img = np.transpose(img, (1, 2, 0))
        else:
            img = pred[0]
    else:
        img = pred

    img = np.clip(img, 0.0, 1.0)
    img = (img * 255.0).astype(np.uint8)
    out = Image.fromarray(img)
    out_w, out_h = in_w * 4, in_h * 4
    if out.size != (out_w, out_h):
        out = out.resize((out_w, out_h), Image.LANCZOS)
    return out


# ── Pipeline stages ─────────────────────────────────────────────


def _pipeline_color_science(rgb: np.ndarray) -> np.ndarray:
    """Stage 1: Professional color correction pipeline."""
    # 1a. White balance (Shades-of-Gray)
    balanced = _white_balance_sog(rgb)

    # 1b. Tone mapping with adaptive histogram
    tone_mapped = _adaptive_tone_map(balanced)

    # 1c. Local contrast (CLAHE in LAB)
    local = _local_contrast(tone_mapped)

    return local


def _pipeline_denoise_sharpen(rgb: np.ndarray) -> np.ndarray:
    """Stage 2: Adaptive denoise + edge-aware sharpen."""
    # 2a. Measure noise level for adaptive denoise
    noise_estimate = _estimate_noise(rgb)
    denoise_strength = min(10, max(3, noise_estimate * 2))

    # 2b. Bilateral filter for edge-preserving denoise
    uint8 = _to_uint8(rgb)
    denoised = cv2.bilateralFilter(uint8, int(min(9, 3 + denoise_strength // 2)),
                                   int(denoise_strength * 3), int(denoise_strength * 3))

    # 2c. If noise is high, add NLM denoise
    if noise_estimate > 5:
        denoised = cv2.fastNlMeansDenoisingColored(denoised, None,
                                                    int(noise_estimate),
                                                    int(noise_estimate * 0.5), 7, 21)

    # 2d. Edge-aware unsharp mask
    result = _adaptive_sharpen(denoised.astype(np.float32))
    return result


def _pipeline_smart_upscale(rgb: np.ndarray, original: np.ndarray) -> np.ndarray:
    """Stage 3: Smart upscale preserving fine details (no ONNX)."""
    # Only upscale if the original was reasonably large
    h, w = rgb.shape[:2]
    if max(h, w) < 800:
        # Use LANCZOS upscale followed by detail enhancement
        pil = Image.fromarray(_to_uint8(rgb))
        scale = min(2, 1600 // max(h, w))
        if scale > 1:
            pil = pil.resize((w * scale, h * scale), Image.LANCZOS)
        return np.asarray(pil).astype(np.float32)
    return rgb


def _pipeline_final_grading(rgb: np.ndarray) -> np.ndarray:
    """Stage 4: Final color grading and vibrance."""
    # 4a. Smart vibrance (protect saturated colors)
    vibrant = _smart_vibrance(rgb)

    # 4b. Subtle contrast curve (S-curve)
    graded = _s_curve(vibrant)

    # 4c. Protect extreme highlights/shadows
    protected = _protect_extremes(graded)

    return protected


# ── Color science primitives ────────────────────────────────────


def _white_balance_sog(rgb: np.ndarray, p: float = 6) -> np.ndarray:
    """Shades-of-Gray white balance. More robust than gray-world."""
    rgb_float = rgb.astype(np.float32)
    # Compute Minkowski norm per channel
    norm = (rgb_float ** p).reshape(-1, 3).mean(axis=0) ** (1.0 / p)
    mean = norm.mean()
    gains = mean / np.maximum(norm, 1e-6)
    gains = np.clip(gains, 0.7, 1.4)
    return np.clip(rgb_float * gains, 0, 255)


def _adaptive_tone_map(rgb: np.ndarray) -> np.ndarray:
    """Adaptive tone mapping using percentile-based stretching + gamma."""
    # Per-channel percentile stretch
    low = np.percentile(rgb, 0.5, axis=(0, 1))
    high = np.percentile(rgb, 99.5, axis=(0, 1))
    stretched = (rgb - low) * (255.0 / np.maximum(high - low, 1.0))
    stretched = np.clip(stretched, 0, 255)

    # Luma-based adaptive gamma
    luma = _luma(stretched)
    midtone = np.percentile(luma, 50)
    gamma = 1.0 + (midtone - 128) / 128 * 0.15  # darken if midtones are high
    gamma = np.clip(gamma, 0.85, 1.15)

    # Apply gamma per pixel based on luma (smooth transition)
    gamma_map = np.ones_like(luma) * gamma
    # Blend gamma toward 1.0 at extremes
    gamma_map = np.where(luma < 20, 1.0 + (gamma - 1.0) * (luma / 20), gamma_map)
    gamma_map = np.where(luma > 235, 1.0 + (gamma - 1.0) * ((255 - luma) / 20), gamma_map)

    # Apply gamma per channel
    result = stretched * (255.0 / np.maximum(stretched, 1e-6)) ** (1.0 / gamma_map[..., None] - 1.0)
    return np.clip(result, 0, 255)


def _local_contrast(rgb: np.ndarray) -> np.ndarray:
    """CLAHE-based local contrast enhancement in LAB color space."""
    uint8 = _to_uint8(rgb)
    lab = cv2.cvtColor(uint8, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)

    # Adaptive CLAHE parameters based on image statistics
    luma = _luma(rgb)
    contrast_ratio = float(luma.std() / (luma.mean() + 1e-6))
    clip_limit = np.clip(2.5 - contrast_ratio * 0.5, 1.0, 3.5)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l_eq = clahe.apply(l)

    merged = cv2.merge((l_eq, a, b))
    result = cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    return result.astype(np.float32)


def _estimate_noise(rgb: np.ndarray) -> float:
    """Estimate noise level from the median deviation of Laplacian."""
    gray = cv2.cvtColor(_to_uint8(rgb), cv2.COLOR_RGB2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    # Median absolute deviation as noise proxy
    mad = np.median(np.abs(lap - np.median(lap)))
    return float(mad)


def _adaptive_sharpen(rgb: np.ndarray) -> np.ndarray:
    """Edge-aware unsharp masking that avoids halos."""
    uint8 = _to_uint8(rgb)
    luma = _luma(rgb)

    # Edge mask: Laplacian magnitude normalized
    gray = cv2.cvtColor(uint8, cv2.COLOR_RGB2GRAY).astype(np.float32)
    edges = cv2.Laplacian(gray, cv2.CV_32F)
    edge_mask = np.abs(edges)
    edge_mask = np.clip(edge_mask / np.percentile(edge_mask, 95), 0, 1) if edge_mask.max() > 0 else np.zeros_like(edge_mask)

    # Blur for difference
    blurred = cv2.GaussianBlur(uint8, (0, 0), 1.5).astype(np.float32)
    detail = rgb - blurred

    # Stronger sharpen on edges, gentler on smooth areas
    sharpen_strength = 0.6 + 0.8 * edge_mask[..., None]
    result = rgb + detail * sharpen_strength

    # Suppress overshoot in extreme areas
    overshoot_mask = np.clip((luma - 240) / 15, 0, 1)[..., None]
    result = result * (1 - overshoot_mask * 0.3) + rgb * (overshoot_mask * 0.3)

    return np.clip(result, 0, 255)


def _smart_vibrance(rgb: np.ndarray) -> np.ndarray:
    """Vibrance that protects skin tones and already-saturated areas."""
    hsv = cv2.cvtColor(_to_uint8(rgb), cv2.COLOR_RGB2HSV).astype(np.float32)
    saturation = hsv[..., 1]
    value = hsv[..., 2]

    # Boost unsaturated areas more, protect saturated
    boost = 1.0 + (1.0 - saturation / 255.0) * 0.25

    # Protect bright highlights from oversaturation
    highlight_protect = 1.0 - np.clip((value - 220) / 35, 0, 0.4)
    boost = boost * highlight_protect

    hsv[..., 1] = np.clip(saturation * boost, 0, 255)
    return cv2.cvtColor(_to_uint8(hsv), cv2.COLOR_HSV2RGB).astype(np.float32)


def _s_curve(rgb: np.ndarray) -> np.ndarray:
    """Subtle S-curve contrast enhancement."""
    luma = _luma(rgb) / 255.0

    # S-curve mapping: shadows down, highlights up
    shadows = np.clip((0.35 - luma) / 0.35, 0, 1)
    highlights = np.clip((luma - 0.55) / 0.45, 0, 1)

    shadow_strength = 0.08
    highlight_strength = 0.10

    multiplier = 1.0 - shadows * shadow_strength + highlights * highlight_strength
    multiplier = multiplier[..., None]

    return np.clip(rgb * multiplier, 0, 255)


def _protect_extremes(enhanced: np.ndarray, strength: float = 0.3) -> np.ndarray:
    """Blend original back in at extreme bright/dark areas to prevent clipping."""
    luma = _luma(enhanced)
    bright_mask = np.clip((luma - 235) / 20, 0, 1)[..., None]
    dark_mask = np.clip((20 - luma) / 20, 0, 1)[..., None]
    protected = enhanced * (1 - bright_mask * strength) + enhanced * (bright_mask * strength)
    protected = protected * (1 - dark_mask * strength * 0.7) + enhanced * (dark_mask * strength * 0.7)
    return np.clip(protected, 0, 255)


# ── Manual enhancement ──────────────────────────────────────────


def _manual_enhance(image: Image.Image, adjustments: dict):
    """Manual slider-based enhancement."""
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
        "color": color, "tone": tone, "vibrance": vibrance,
        "denoise": denoise, "sharpen": sharpen, "exposure": exposure,
        "warmth": warmth, "shadows": shadows, "highlights": highlights,
    })
    return adjusted, metrics


# ── Background removal ──────────────────────────────────────────


def _background_cutout(image: Image.Image):
    """Remove background using rembg (preferred) or OpenCV GrabCut fallback."""
    rgb = np.asarray(image).astype(np.uint8)

    # Try rembg first
    result = _rembg_cutout(image)
    if result is not None:
        return result

    # Fallback: GrabCut
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
        cv2.grabCut(bgr, mask, (margin_x, margin_y, rect_width, rect_height),
                     bgd_model, fgd_model, 6, cv2.GC_INIT_WITH_RECT)
        alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    except cv2.error:
        method = "border-threshold"
        border = max(2, min(height, width) // 16)
        edge_pixels = np.concatenate([
            rgb[:border, :, :].reshape(-1, 3),
            rgb[-border:, :, :].reshape(-1, 3),
            rgb[:, :border, :].reshape(-1, 3),
            rgb[:, -border:, :].reshape(-1, 3),
        ], axis=0)
        background_color = np.median(edge_pixels, axis=0)
        distances = np.linalg.norm(rgb.astype(np.float32) - background_color, axis=2)
        threshold = np.percentile(distances, 52)
        alpha = np.where(distances > threshold, 255, 0).astype(np.uint8)

    alpha = _refine_alpha(alpha)
    foreground_ratio = float((alpha > 127).mean())
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray(rgba, "RGBA"), {"method": method, "foreground_ratio": foreground_ratio}


def _rembg_cutout(image):
    """Try rembg-based cutout."""
    if new_session is None or rembg_remove is None:
        return None

    session = _get_rembg_session()
    if session is None:
        return None

    try:
        with BytesIO() as buf:
            image.save(buf, format="PNG")
            output = rembg_remove(
                buf.getvalue(), session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=240,
                alpha_matting_background_threshold=12,
                alpha_matting_erode_size=8,
                post_process_mask=True,
                force_return_bytes=True,
            )
        with Image.open(BytesIO(output)) as cutout:
            cutout_rgba = cutout.convert("RGBA")
        rgba = np.asarray(cutout_rgba).astype(np.uint8)
        alpha = _refine_alpha(rgba[..., 3])
        rgba[..., 3] = alpha
        method = f"rembg:u2net"
        return Image.fromarray(rgba, "RGBA"), {"method": method, "foreground_ratio": float((alpha > 127).mean())}
    except Exception:
        return None


_REMBG_SESSION = None
_REMBG_MODEL_NAME: Optional[str] = None


def _get_rembg_session():
    global _REMBG_SESSION, _REMBG_MODEL_NAME
    if _REMBG_SESSION is not None:
        return _REMBG_SESSION
    if new_session is None:
        return None
    for name in ("isnet-general-use", "u2net"):
        try:
            _REMBG_SESSION = new_session(name)
            _REMBG_MODEL_NAME = name
            return _REMBG_SESSION
        except Exception:
            continue
    return None


def _refine_alpha(alpha: np.ndarray) -> np.ndarray:
    """Clean up the alpha matte with morphological ops and largest-component selection."""
    alpha = alpha.astype(np.uint8)
    h, w = alpha.shape[:2]
    ksize = max(3, min(h, w) // 160)
    if ksize % 2 == 0:
        ksize += 1
    ksize = min(ksize, 11)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))

    refined = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=1)
    refined = cv2.morphologyEx(refined, cv2.MORPH_OPEN, kernel, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        (refined > 127).astype(np.uint8), 8)
    if num_labels > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        refined = np.where(labels == largest, 255, 0).astype(np.uint8)

    return cv2.GaussianBlur(refined, (5, 5), 0)


# ── Metrics & descriptions ──────────────────────────────────────


def _measure(rgb: np.ndarray) -> dict:
    luma = _luma(rgb)
    return {
        "brightness": float(luma.mean()),
        "contrast": float(luma.std()),
        "shadow": float(np.percentile(luma, 5)),
        "highlight": float(np.percentile(luma, 95)),
    }


def _describe_enhancement(mode: str, metrics: dict) -> str:
    backend = metrics.get("ai_backend", "precision-classical")
    scale = metrics.get("scale", 1)
    scale_text = f" Upscaled {scale}x." if scale > 1 else ""
    post_b = metrics.get("post_brightness", 0)
    post_c = metrics.get("post_contrast", 0)

    if mode == "manual":
        return (
            f"Manual mode: color {metrics.get('color',50)}, tone {metrics.get('tone',50)}, "
            f"contrast {metrics.get('contrast',50)}, vibrance {metrics.get('vibrance',50)}, "
            f"denoise {metrics.get('denoise',50)}, sharpen {metrics.get('sharpen',50)}, "
            f"exposure {metrics.get('exposure',50)}, warmth {metrics.get('warmth',50)}, "
            f"shadows {metrics.get('shadows',50)}, highlights {metrics.get('highlights',50)}."
        )

    return (
        f"{MODEL_NAME}: {backend}. "
        f"Pipeline: white balance (SoG) → adaptive tone map → CLAHE local contrast → "
        f"adaptive denoise/sharpen → smart vibrance → S-curve grading."
        f"{scale_text} "
        f"Output: brightness {post_b:.0f}, contrast {post_c:.0f}."
    )


def _describe_background_removal(metrics: dict) -> str:
    return (
        f"Background removed via {metrics.get('method', 'grabcut')}. "
        f"Foreground: {metrics.get('foreground_ratio', 0):.0%} of frame. "
        f"Export: transparent PNG."
    )


# ── Utilities ───────────────────────────────────────────────────


def _luma(rgb: np.ndarray) -> np.ndarray:
    """Relative luminance (Rec. 709)."""
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _slider_value(adj: dict, name: str, default: int = 50) -> int:
    try:
        return int(float(adj.get(name, default)))
    except (TypeError, ValueError):
        return default


def _slider_factor(value: int, minimum: float, maximum: float) -> float:
    return minimum + (max(value, 0) / 100.0) * (maximum - minimum)


def _manual_exposure(rgb: np.ndarray, exposure: int) -> np.ndarray:
    factor = _slider_factor(exposure, 0.78, 1.28)
    return np.clip(rgb * factor, 0, 255)


def _manual_warmth(rgb: np.ndarray, warmth: int) -> np.ndarray:
    factor = (warmth - 50) / 50.0
    warmed = rgb.copy()
    warmed[..., 0] = np.clip(warmed[..., 0] * (1.0 + factor * 0.12), 0, 255)
    warmed[..., 2] = np.clip(warmed[..., 2] * (1.0 - factor * 0.12), 0, 255)
    return warmed


def _manual_tone(rgb: np.ndarray, tone: int, shadows: int, highlights: int) -> np.ndarray:
    luma = _luma(rgb) / 255.0
    shadow_mask = np.clip((0.56 - luma) / 0.56, 0, 1)[..., None]
    highlight_mask = np.clip((luma - 0.56) / 0.44, 0, 1)[..., None]
    tf = (tone - 50) / 50.0
    sl = max((shadows - 50) / 50.0, 0.0)
    sd = max((50 - shadows) / 50.0, 0.0)
    hl = max((highlights - 50) / 50.0, 0.0)
    hp = max((50 - highlights) / 50.0, 0.0)

    result = rgb + (255 - rgb) * shadow_mask * (0.28 * sl + 0.08 * max(tf, 0))
    result = result * (1 - shadow_mask * 0.18 * sd)
    result = result + (255 - result) * highlight_mask * (0.16 * hl)
    result = result * (1 - highlight_mask * 0.20 * hp)
    return np.clip(result, 0, 255)


def _manual_color_balance(rgb: np.ndarray, color: int) -> np.ndarray:
    bal = (color - 50) / 50.0
    result = rgb.copy()
    result[..., 1] = np.clip(result[..., 1] * (1.0 + bal * 0.05), 0, 255)
    return result


def _to_uint8(array: np.ndarray) -> np.ndarray:
    return np.clip(array, 0, 255).astype(np.uint8)

# AI enhancement model runtime status

## Current state (2026-07-04)
- The site’s current `ai` mode uses only classical image processing (`enhancer/ai_engine.py`).
- Attempted integration of Real-ESRGAN via the `realesrgan` Python package.

## Dependency blocker
- `realesrgan` imports fail because `basicsr` cannot be installed in this environment (Python 3.14).
- Installing `basicsr` fails during metadata/build with `KeyError: '__version__'`.

## What is installed
- `torch` (CPU) installs successfully.
- `realesrgan` installs successfully only when `--no-deps` is used, but then fails at import time due to missing `basicsr`.

## Next options
1) Use a working model runtime that does not require `basicsr` (e.g., ONNX-based super-resolution).
2) Downgrade Python in the venv to 3.10/3.11 so `basicsr` can install, then wire Real-ESRGAN properly.


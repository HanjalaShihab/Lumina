# TODO

## Part A — Real AI enhancement (Real-ESRGAN)
- [x] Verify current AI pipeline usage and add Real-ESRGAN inference path in `enhancer/ai_engine.py` (lazy model load + CPU fallback)

- [ ] Update `enhancer/forms.py` + `ai_enhancer.html` to expose scale/model options (blocked until model runtime works)

- [ ] Update `enhancer/models.py` if we need to store scale/model metadata (or embed into `notes`)
- [ ] Update `requirements.txt` with Real-ESRGAN / torch dependencies

## Part B — Detailed website pages
- [ ] Add shared partials (features/how-it-works/FAQ) under `enhancer/templates/enhancer/partials/`
- [ ] Update `home.html`, `ai_enhancer.html`, `manual.html`, `batch.html`, `history.html` to include those sections
- [ ] Extend `static/css/style.css` for accordion/longform layout

## Validation
- [ ] Install deps and run Django
- [ ] Ensure ONNX runtime import works (already installed)
- [ ] Upload test image in AI mode and confirm output differs due to super-resolution (not brightness)
- [ ] Manually check all pages render correctly


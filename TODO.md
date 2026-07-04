# Lumina TODO

## UI upgrades (done after ✅)
- [ ] Add consistent “How it works / Quality / What you get” sections to:
  - [ ] enhancer/templates/enhancer/home.html
  - [ ] enhancer/templates/enhancer/manual.html
  - [ ] enhancer/templates/enhancer/ai_enhancer.html
  - [ ] enhancer/templates/enhancer/batch.html
  - [ ] enhancer/templates/enhancer/history.html
  - [ ] enhancer/templates/enhancer/partials/result.html
- [ ] Polish History/Result notes wording + formatting
- [ ] Add CSS for the new info blocks in static/css/style.css
- [ ] Run dev server and verify the updated website visually

## AI mode / ONNX correctness (next)
- [ ] Replace silent fallback in enhancer/ai_engine.py when ONNX weights are missing
- [ ] Wire in real ONNX model:
  - [ ] auto-download if missing
  - [ ] hard-fail with clear message if download/model missing
- [ ] Validate runtime end-to-end

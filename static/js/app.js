document.querySelectorAll('input[type="file"]').forEach((input) => {
  input.addEventListener("change", () => {
    const label = input.closest(".dropzone");
    if (!label || !input.files.length) return;
    const name = input.files.length === 1 ? input.files[0].name : `${input.files.length} files selected`;
    label.querySelector("span").textContent = name;
  });
});

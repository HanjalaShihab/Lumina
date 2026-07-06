(function () {
  const storageKey = "lumina-theme";
  const root = document.documentElement;
  const themeToggle = document.getElementById("themeToggle");
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');

  function applyTheme(theme) {
    root.dataset.theme = theme;
    localStorage.setItem(storageKey, theme);
    if (themeColorMeta) {
      themeColorMeta.setAttribute("content", theme === "light" ? "#f4f7fb" : "#08080e");
    }
    if (themeToggle) {
      themeToggle.textContent = theme === "light" ? "🌙" : "☀️";
    }
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      applyTheme(root.dataset.theme === "light" ? "dark" : "light");
    });
  }

  applyTheme(root.dataset.theme || "dark");

  // Dropzone file name updates
  document.querySelectorAll("input[type='file']").forEach((input) => {
    input.addEventListener("change", () => {
      const label = input.closest(".dropzone");
      if (!label) return;

      const previewMode = label.dataset.previewMode;
      const icon = label.querySelector(".icon");
      const text = label.querySelector(".text");
      const hint = label.querySelector(".hint");
      const preview = label.querySelector(".dropzone-preview");

      if (previewMode === "image" && preview) {
        if (input._previewUrl) {
          URL.revokeObjectURL(input._previewUrl);
          input._previewUrl = null;
        }

        if (input.files && input.files.length === 1) {
          const file = input.files[0];
          if (file.type.startsWith("image/")) {
            const objectUrl = URL.createObjectURL(file);
            input._previewUrl = objectUrl;
            preview.src = objectUrl;
            preview.style.display = "block";
            if (icon) icon.style.display = "none";
            if (text) text.textContent = "Image preview";
            if (hint) hint.textContent = "Image selected. Submit to remove the background.";
            return;
          }
        }

        preview.removeAttribute("src");
        preview.style.display = "none";
        if (icon) icon.style.display = "block";
        if (text) text.textContent = "Drop your image here or click to remove the background";
        if (hint) hint.textContent = "JPG, PNG, WebP · transparent PNG output";
        return;
      }

      const name =
        input.files && input.files.length === 1
          ? input.files[0].name
          : input.files && input.files.length
          ? `${input.files.length} files selected`
          : "Choose image";
      const span = label.querySelector("span");
      if (span) span.textContent = name;
    });
  });

  // Reveal on scroll (IntersectionObserver)
  const els = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("is-revealed");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    els.forEach((el) => io.observe(el));
  } else {
    els.forEach((el) => el.classList.add("is-revealed"));
  }

  // Subtle page load
  window.addEventListener("load", () => {
    document.documentElement.classList.add("js-loaded");
  });
})();

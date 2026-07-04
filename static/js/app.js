(function () {
  // Dropzone file name updates
  document.querySelectorAll("input[type='file']").forEach((input) => {
    input.addEventListener("change", () => {
      const label = input.closest(".dropzone");
      if (!label) return;
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

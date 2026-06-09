(() => {
  const onReady = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }

    callback();
  };

  const revealSections = () => {
    const explicitSections = Array.from(document.querySelectorAll(".reveal"));
    const automaticSections = Array.from(
      document.querySelectorAll(
        [
          'main[id="main-content"] > .ml-home-section',
          'main[id="main-content"] > .ml-taxonomy-header',
          'main[id="main-content"] > .ml-search-header',
          'main[id="main-content"] > .ml-not-found',
          'main[id="main-content"].ml-page-frame > .wp-block-post-title',
          'main[id="main-content"].ml-page-frame > .wp-block-post-content',
          'main[id="main-content"].ml-shell:not(.ml-page-frame):not(.ml-report-shell-ingest) > .wp-block-query',
          'main[id="main-content"].ml-shell:not(.ml-page-frame):not(.ml-report-shell-ingest) > .wp-block-post-title',
          'main[id="main-content"].ml-shell:not(.ml-page-frame):not(.ml-report-shell-ingest) > .wp-block-post-content'
        ].join(", ")
      )
    );

    const sections = Array.from(new Set([...explicitSections, ...automaticSections]));

    if (sections.length === 0) {
      return;
    }

    document.documentElement.classList.add("has-reveal-motion");
    sections.forEach((section) => section.classList.add("reveal-auto"));

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const isCompactViewport = window.matchMedia("(max-width: 782px)").matches;

    if (prefersReducedMotion || !("IntersectionObserver" in window)) {
      sections.forEach((section) => section.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }

          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      {
        threshold: isCompactViewport ? 0.06 : 0.18,
        rootMargin: isCompactViewport ? "0px 0px -2% 0px" : "0px 0px -6% 0px",
      }
    );

    sections.forEach((section) => observer.observe(section));
  };

  const configureReportFilters = () => {
    const filterPanel = document.querySelector(".ml-report-filter-panel");
    if (!(filterPanel instanceof HTMLDetailsElement)) {
      return;
    }

    const compactViewport = window.matchMedia("(max-width: 900px)");
    const syncPanelState = (event) => {
      filterPanel.open = !event.matches;
    };

    syncPanelState(compactViewport);
    compactViewport.addEventListener("change", syncPanelState);
  };

  onReady(() => {
    revealSections();
    configureReportFilters();
  });
})();

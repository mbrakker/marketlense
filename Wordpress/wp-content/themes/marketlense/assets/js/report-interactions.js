(() => {
  "use strict";

  const activeClass = "is-active";

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function hasAbsoluteUrl(value) {
    const candidate = String(value || "").trim();
    return /^(?:[a-z]+:)?\/\//i.test(candidate);
  }

  function initImageSrcsetFallback() {
    const images = Array.from(document.querySelectorAll(".ml-ingest-report-content img[srcset]"));
    if (!images.length) {
      return;
    }

    images.forEach((img) => {
      const src = (img.getAttribute("src") || "").trim();
      const srcset = (img.getAttribute("srcset") || "").trim();
      if (!src || !srcset || !hasAbsoluteUrl(src)) {
        return;
      }

      const entries = srcset
        .split(",")
        .map((entry) => entry.trim())
        .filter(Boolean);
      if (!entries.length) {
        return;
      }

      const hasRelativeEntry = entries.some((entry) => {
        const token = entry.split(/\s+/)[0] || "";
        return token && !hasAbsoluteUrl(token) && !token.startsWith("data:");
      });

      if (hasRelativeEntry) {
        img.removeAttribute("srcset");
      }
    });
  }

  function initReadingProgress() {
    const progressBar =
      document.getElementById("reading-progress-bar") ||
      document.querySelector("[data-reading-progress-bar]");
    if (!progressBar) {
      return;
    }

    const update = () => {
      const top = window.scrollY || window.pageYOffset || 0;
      const total = Math.max(
        (document.documentElement.scrollHeight || 0) - (window.innerHeight || 0),
        1
      );
      const percent = clamp((top / total) * 100, 0, 100);
      progressBar.style.width = `${percent.toFixed(2)}%`;
    };

    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();
  }

  function initChunkedProse() {
    const proseBlocks = Array.from(document.querySelectorAll("[data-chunk-prose]"));
    if (!proseBlocks.length) {
      return;
    }

    proseBlocks.forEach((element) => {
      const text = (element.textContent || "").trim();
      if (!text || text.length < 320) {
        return;
      }

      let parts = [];
      const lines = text
        .split(/\n+/)
        .map((line) => line.trim())
        .filter(Boolean);

      if (lines.length > 1) {
        parts = lines;
      } else {
        const sentences = text.match(/[^.!?]+[.!?]*/g) || [text];
        let bucket = "";
        sentences.forEach((sentence) => {
          const next = `${bucket} ${sentence}`.trim();
          if (next.length > 260 && bucket) {
            parts.push(bucket.trim());
            bucket = sentence;
          } else {
            bucket = next;
          }
        });
        if (bucket.trim()) {
          parts.push(bucket.trim());
        }
      }

      if (parts.length < 2) {
        return;
      }

      element.innerHTML = "";
      parts.forEach((part) => {
        const paragraph = document.createElement("p");
        paragraph.className = "prose-paragraph";
        paragraph.textContent = part;
        element.appendChild(paragraph);
      });
    });
  }

  function initRevealPanels() {
    const panels = Array.from(document.querySelectorAll("[data-reveal]"));
    if (!panels.length) {
      return;
    }

    panels.forEach((panel) => {
      const root = panel.closest(".ml-ingest-report-content");
      if (root) {
        root.classList.add("ml-report-interactive");
      }
    });

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!("IntersectionObserver" in window) || reducedMotion) {
      panels.forEach((panel) => panel.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries, instance) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }
          entry.target.classList.add("is-visible");
          instance.unobserve(entry.target);
        });
      },
      {
        root: null,
        rootMargin: "0px 0px -10% 0px",
        threshold: 0.1
      }
    );

    panels.forEach((panel) => observer.observe(panel));
  }

  function initSectionSpy() {
    const sectionLinks = Array.from(document.querySelectorAll("[data-section-link]"));

    if (!sectionLinks.length) {
      return;
    }

    const sectionMap = new Map();
    sectionLinks.forEach((link) => {
      const href = link.getAttribute("href");
      if (!href || !href.startsWith("#")) {
        return;
      }
      const target = document.querySelector(href);
      if (!target) {
        return;
      }
      if (!sectionMap.has(target)) {
        sectionMap.set(target, []);
      }
      sectionMap.get(target).push(link);
    });

    const allSections = Array.from(sectionMap.keys());
    if (!allSections.length) {
      return;
    }

    const setActive = (activeSection) => {
      sectionMap.forEach((links, section) => {
        const active = section === activeSection;
        links.forEach((link) => {
          link.classList.toggle(activeClass, active);
          if (active) {
            link.setAttribute("aria-current", "true");
          } else {
            link.removeAttribute("aria-current");
          }
        });
      });
    };

    if (!("IntersectionObserver" in window)) {
      setActive(allSections[0]);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActive(entry.target);
          }
        });
      },
      {
        root: null,
        rootMargin: "-35% 0px -45% 0px",
        threshold: 0.01
      }
    );

    setActive(allSections[0]);
    allSections.forEach((section) => observer.observe(section));
  }

  function initCarousel(carousel) {
    if (!carousel || carousel.dataset.mlReady === "true") {
      return;
    }

    const slides = Array.from(
      carousel.querySelectorAll("[data-carousel-slide], .carousel-slide")
    );
    if (!slides.length) {
      carousel.dataset.mlReady = "true";
      return;
    }

    const prevButton =
      carousel.querySelector("[data-carousel-prev]") ||
      carousel.querySelector(".carousel-btn.prev");
    const nextButton =
      carousel.querySelector("[data-carousel-next]") ||
      carousel.querySelector(".carousel-btn.next");
    const thumbs = Array.from(
      carousel.querySelectorAll("[data-carousel-thumb], .carousel-thumb")
    );
    const count = carousel.querySelector("[data-carousel-count]");
    const track = carousel.querySelector(".carousel-slides");
    const openLightboxButton = carousel.querySelector("[data-lightbox-open]");
    const lightbox =
      document.getElementById("figure-lightbox") ||
      document.querySelector(".lightbox");
    const lightboxImage =
      document.getElementById("lightbox-image") ||
      lightbox?.querySelector("img");
    const lightboxCaption =
      document.getElementById("lightbox-caption") ||
      lightbox?.querySelector("figcaption");
    const lightboxCloseButtons = lightbox
      ? Array.from(lightbox.querySelectorAll("[data-lightbox-close], .lightbox-close"))
      : [];

    let index = slides.findIndex((slide) => slide.classList.contains(activeClass));
    if (index < 0) {
      index = 0;
    }

    const render = () => {
      slides.forEach((slide, slideIndex) => {
        const active = slideIndex === index;
        slide.classList.toggle(activeClass, active);
        slide.hidden = !active;
      });

      thumbs.forEach((thumb, thumbIndex) => {
        const active = thumbIndex === index;
        thumb.classList.toggle(activeClass, active);
        thumb.setAttribute("aria-selected", active ? "true" : "false");
      });

      if (count) {
        count.textContent = `${index + 1} / ${slides.length}`;
      }
    };

    const goTo = (requestedIndex) => {
      index = clamp(requestedIndex, 0, slides.length - 1);
      render();
    };

    const goNext = () => goTo((index + 1) % slides.length);
    const goPrev = () => goTo((index - 1 + slides.length) % slides.length);

    if (prevButton) {
      prevButton.addEventListener("click", goPrev);
    }
    if (nextButton) {
      nextButton.addEventListener("click", goNext);
    }

    thumbs.forEach((thumb, thumbIndex) => {
      thumb.addEventListener("click", () => goTo(thumbIndex));
    });

    if (track) {
      track.setAttribute("tabindex", "0");
      track.addEventListener("keydown", (event) => {
        if (event.key === "ArrowRight") {
          event.preventDefault();
          goNext();
        }
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          goPrev();
        }
      });
    }

    let pointerStartX = 0;
    const onPointerDown = (event) => {
      pointerStartX = event.clientX;
    };
    const onPointerUp = (event) => {
      const delta = event.clientX - pointerStartX;
      if (Math.abs(delta) < 42) {
        return;
      }
      if (delta > 0) {
        goPrev();
      } else {
        goNext();
      }
    };

    if (track) {
      track.addEventListener("pointerdown", onPointerDown);
      track.addEventListener("pointerup", onPointerUp);
    }

    const closeLightbox = () => {
      if (!lightbox) {
        return;
      }
      lightbox.hidden = true;
      lightbox.setAttribute("aria-hidden", "true");
      if (lightboxImage) {
        lightboxImage.src = "";
      }
      document.body.style.overflow = "";
    };

    const openLightbox = () => {
      if (!lightbox || !lightboxImage) {
        return;
      }

      const activeSlide = slides[index];
      const image = activeSlide.querySelector("img");
      const caption = activeSlide.querySelector("figcaption");
      if (!image) {
        return;
      }

      lightboxImage.src = image.currentSrc || image.src;
      lightboxImage.alt = image.alt || "";
      if (lightboxCaption) {
        lightboxCaption.textContent = caption ? caption.textContent.trim() : "";
      }

      lightbox.hidden = false;
      lightbox.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    };

    slides.forEach((slide, slideIndex) => {
      slide.addEventListener("click", () => {
        goTo(slideIndex);
        openLightbox();
      });
    });

    if (openLightboxButton) {
      openLightboxButton.addEventListener("click", openLightbox);
    }
    if (lightbox) {
      lightbox.addEventListener("click", (event) => {
        if (event.target === lightbox) {
          closeLightbox();
        }
      });
    }
    lightboxCloseButtons.forEach((button) => {
      button.addEventListener("click", closeLightbox);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeLightbox();
      }
    });

    render();
    carousel.dataset.mlReady = "true";
  }

  function initCarousels() {
    const carousels = Array.from(document.querySelectorAll("[data-carousel], .figure-carousel"));
    carousels.forEach((carousel) => initCarousel(carousel));
  }

  function init() {
    initImageSrcsetFallback();
    initChunkedProse();
    initRevealPanels();
    initReadingProgress();
    initSectionSpy();
    initCarousels();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

// This script is loaded on every page via base.html, so it must be defensive.

(() => {
  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  onReady(() => {
    // Mobile menu (navbar).
    const toggle = document.getElementById("menu-toggle");
    const navMenu = document.getElementById("nav-menu");
    if (toggle && navMenu) {
      toggle.addEventListener("click", () => {
        navMenu.classList.toggle("active");
      });

      // Close menu when clicking a link (especially important for in-page anchors).
      navMenu.querySelectorAll("a").forEach(link => {
        link.addEventListener("click", () => {
          navMenu.classList.remove("active");
        });
      });
    }

    // Theme toggle (optional).
    const themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        document.body.classList.toggle("light-mode");
        const mode = document.body.classList.contains("light-mode") ? "light" : "dark";
        localStorage.setItem("theme", mode);
      });

      if (localStorage.getItem("theme") === "light") {
        document.body.classList.add("light-mode");
      }
    }

    // Active nav highlight for in-page anchors (works for "#id" and "/#id").
    const sections = Array.from(document.querySelectorAll("section[id]"));
    const navLinks = Array.from(document.querySelectorAll(".navbar a[href*=\"#\"]"));

    function updateActiveNav() {
      if (sections.length === 0 || navLinks.length === 0) return;

      let currentId = "";
      const scrollY = window.scrollY;

      for (const section of sections) {
        const sectionTop = section.offsetTop - 140;
        if (scrollY >= sectionTop) currentId = section.id;
      }

      navLinks.forEach((link) => {
        const hash = link.hash || "";
        link.classList.toggle("active", currentId && hash === `#${currentId}`);
      });
    }

    window.addEventListener("scroll", updateActiveNav, { passive: true });
    window.addEventListener("load", updateActiveNav);
    updateActiveNav();

    // Hero slider (home page).
    const heroSlider = document.querySelector("[data-hero-slider]");
    if (heroSlider) {
      const slides = Array.from(heroSlider.querySelectorAll(".slide"));
      const controls = document.querySelector("[data-hero-controls]");
      const dotsContainer = controls?.querySelector("[data-hero-dots]");
      const prevBtn = controls?.querySelector("[data-hero-prev]");
      const nextBtn = controls?.querySelector("[data-hero-next]");

      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

      function ensureBackground(slide) {
        if (!slide) return;
        if (slide.style.backgroundImage) return;
        const bg = slide.getAttribute("data-bg");
        if (!bg) return;
        slide.style.backgroundImage = `url("${bg}")`;
      }

      if (slides.length > 0) {
        let currentIndex = slides.findIndex((s) => s.classList.contains("active"));
        if (currentIndex < 0) currentIndex = 0;

        slides.forEach((s, i) => s.classList.toggle("active", i === currentIndex));
        ensureBackground(slides[currentIndex]);
        ensureBackground(slides[(currentIndex + 1) % slides.length]);

        let dots = [];

        function setActiveDot() {
          if (!dots || dots.length === 0) return;
          dots.forEach((dot, i) => {
            const isActive = i === currentIndex;
            dot.classList.toggle("active", isActive);
            if (isActive) {
              dot.setAttribute("aria-current", "true");
            } else {
              dot.removeAttribute("aria-current");
            }
          });
        }

        function renderDots() {
          if (!dotsContainer) return;
          dotsContainer.innerHTML = "";
          dots = slides.map((_, i) => {
            const dot = document.createElement("button");
            dot.type = "button";
            dot.className = "hero-dot";
            dot.setAttribute("aria-label", `Go to slide ${i + 1}`);
            dot.addEventListener("click", () => goTo(i, true));
            dotsContainer.appendChild(dot);
            return dot;
          });
          setActiveDot();
        }

        function goTo(nextIndex, userInitiated = false) {
          const normalized = (nextIndex + slides.length) % slides.length;
          if (normalized === currentIndex) return;

          slides[currentIndex].classList.remove("active");
          currentIndex = normalized;

          ensureBackground(slides[currentIndex]);
          ensureBackground(slides[(currentIndex + 1) % slides.length]);

          slides[currentIndex].classList.add("active");
          setActiveDot();

          if (userInitiated) restartTimer();
        }

        function next(userInitiated = false) {
          goTo(currentIndex + 1, userInitiated);
        }

        function prev(userInitiated = false) {
          goTo(currentIndex - 1, userInitiated);
        }

        renderDots();

        prevBtn?.addEventListener("click", () => prev(true));
        nextBtn?.addEventListener("click", () => next(true));

        // Auto-play (paused on hover/focus, disabled for reduced motion).
        const intervalMs = 6500;
        let timerId = null;
        let restartTimeoutId = null;

        function startTimer() {
          if (reduceMotion) return;
          if (slides.length <= 1) return;
          if (timerId) return;
          if (!isInViewport(heroSlider)) return;
          timerId = window.setInterval(() => next(false), intervalMs);
        }

        function stopTimer() {
          if (!timerId) return;
          window.clearInterval(timerId);
          timerId = null;
        }

        function restartTimer() {
          stopTimer();
          if (restartTimeoutId) window.clearTimeout(restartTimeoutId);
          restartTimeoutId = window.setTimeout(() => startTimer(), 4000);
        }

        heroSlider.addEventListener("pointerenter", stopTimer);
        heroSlider.addEventListener("pointerleave", startTimer);

        if (controls) {
          controls.addEventListener("pointerenter", stopTimer);
          controls.addEventListener("pointerleave", startTimer);
          controls.addEventListener("focusin", stopTimer);
          controls.addEventListener("focusout", (e) => {
            if (controls.contains(e.relatedTarget)) return;
            startTimer();
          });
        }

        document.addEventListener("visibilitychange", () => {
          if (document.hidden) {
            stopTimer();
            return;
          }
          startTimer();
        });

        function isInViewport(el) {
          const rect = el.getBoundingClientRect();
          return rect.bottom > 0 && rect.top < window.innerHeight;
        }

        document.addEventListener("keydown", (e) => {
          const tag = (e.target && e.target.tagName) || "";
          if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target?.isContentEditable) return;
          const lightbox = document.getElementById("lightbox");
          if (lightbox?.classList?.contains("open")) return;
          if (!isInViewport(heroSlider)) return;
          if (e.key === "ArrowLeft") prev(true);
          if (e.key === "ArrowRight") next(true);
        });

        // Swipe support (mobile).
        let swipeStartX = 0;
        let swipeStartY = 0;
        let swiping = false;

        heroSlider.addEventListener(
          "pointerdown",
          (e) => {
            if (!e.isPrimary) return;
            swiping = true;
            swipeStartX = e.clientX;
            swipeStartY = e.clientY;
          },
          { passive: true }
        );

        heroSlider.addEventListener(
          "pointerup",
          (e) => {
            if (!swiping) return;
            swiping = false;

            const dx = e.clientX - swipeStartX;
            const dy = e.clientY - swipeStartY;
            if (Math.abs(dx) > 60 && Math.abs(dy) < 40) {
              if (dx < 0) next(true);
              else prev(true);
            }
          },
          { passive: true }
        );

        heroSlider.addEventListener("pointercancel", () => {
          swiping = false;
        });

        if ("IntersectionObserver" in window) {
          const observer = new IntersectionObserver(
            (entries) => {
              const entry = entries && entries[0];
              if (!entry) return;
              if (entry.isIntersecting) startTimer();
              else stopTimer();
            },
            { threshold: 0.25 }
          );
          observer.observe(heroSlider);
        }

        startTimer();
      }
    }
  });
})();


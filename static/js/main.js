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
      const mobileQuery = window.matchMedia("(max-width: 768px)");

      function setMenuOpen(isOpen) {
        navMenu.classList.toggle("active", isOpen);
        toggle.setAttribute("aria-expanded", String(isOpen));
        document.body.classList.toggle("menu-open", isOpen && mobileQuery.matches);
      }

      function closeMenu() {
        setMenuOpen(false);
      }

      toggle.addEventListener("click", () => {
        const nextOpen = !navMenu.classList.contains("active");
        setMenuOpen(nextOpen);
      });

      // Close menu when clicking a link (especially important for in-page anchors).
      navMenu.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
          closeMenu();
        });
      });

      // Click outside closes the mobile drawer.
      document.addEventListener("click", (event) => {
        if (!mobileQuery.matches || !navMenu.classList.contains("active")) return;
        if (navMenu.contains(event.target) || toggle.contains(event.target)) return;
        closeMenu();
      });

      // Esc closes the drawer for accessibility.
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && navMenu.classList.contains("active")) {
          closeMenu();
        }
      });

      function onViewportChange() {
        if (!mobileQuery.matches) closeMenu();
      }

      if (mobileQuery.addEventListener) {
        mobileQuery.addEventListener("change", onViewportChange);
      } else if (mobileQuery.addListener) {
        mobileQuery.addListener(onViewportChange);
      }
    }

    // Mobile-first reveal animation for touch devices.
    const isTouchMobile = window.matchMedia("(hover: none) and (pointer: coarse)").matches;
    if (isTouchMobile && "IntersectionObserver" in window) {
      const mobileAnimatedNodes = document.querySelectorAll(
        [
          ".testimonial-chat",
          ".rate-box",
          ".philosophy-text",
          ".philosophy-image",
          ".about-content",
          ".about-image",
          ".contact-form",
          ".contact-info",
        ].join(",")
      );

      if (mobileAnimatedNodes.length > 0) {
        const observer = new IntersectionObserver(
          (entries, instance) => {
            entries.forEach((entry) => {
              if (!entry.isIntersecting) return;
              entry.target.classList.add("is-visible");
              instance.unobserve(entry.target);
            });
          },
          { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
        );

        mobileAnimatedNodes.forEach((node, index) => {
          node.classList.add("mobile-animate");
          node.style.transitionDelay = `${(index % 4) * 60}ms`;
          observer.observe(node);
        });
      }
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

    // Back-to-top button.
    const backToTop = document.getElementById("back-to-top");
    if (backToTop) {
      const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      function updateBackToTop() {
        backToTop.classList.toggle("is-visible", window.scrollY > 500);
      }

      window.addEventListener("scroll", updateBackToTop, { passive: true });
      window.addEventListener("load", updateBackToTop);
      updateBackToTop();

      backToTop.addEventListener("click", () => {
        if (reduceMotion) return window.scrollTo(0, 0);
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  });
})();

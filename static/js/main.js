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
  });
})();


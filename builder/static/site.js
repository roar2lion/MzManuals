(function () {
  "use strict";
  var root = document.documentElement;

  // ---- theme (per-viewer convenience only)
  function storedTheme() { try { return localStorage.getItem("theme"); } catch (e) { return null; } }
  var t = storedTheme();
  if (t) root.setAttribute("data-theme", t);

  function isDark() {
    var a = root.getAttribute("data-theme");
    return a ? a === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme");
    if (btn) btn.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
    });

    // ---- maths
    if (window.katex) {
      document.querySelectorAll("[data-tex]").forEach(function (el) {
        try {
          katex.render(el.getAttribute("data-tex"), el, { displayMode: el.classList.contains("display"), throwOnError: false });
        } catch (e) { el.textContent = el.getAttribute("data-tex"); }
      });
    }

    // ---- diagrams
    if (window.mermaid) {
      var printing = document.body.classList.contains("print");
      mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: (!printing && isDark()) ? "dark" : "neutral" });
      mermaid.run({ querySelector: "pre.mermaid" });
    }

    initToc();
    initSearch();
  });

  // ---- highlight the section being read in the sidebar
  function initToc() {
    var links = document.querySelectorAll(".sidebar .toc a");
    if (!links.length || !("IntersectionObserver" in window)) return;
    var byId = {};
    links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
    var current = null;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && byId[e.target.id]) {
          if (current) current.classList.remove("active");
          current = byId[e.target.id];
          current.classList.add("active");
        }
      });
    }, { rootMargin: "-10% 0px -80% 0px" });
    document.querySelectorAll("main section[id]").forEach(function (s) { obs.observe(s); });
  }

  // ---- search over site/static/search-index.js (works from file:// too)
  function initSearch() {
    var input = document.getElementById("search");
    var box = document.getElementById("search-results");
    if (!input || !box) return;
    var index = null, active = -1;

    function load(cb) {
      if (index) return cb();
      var s = document.createElement("script");
      s.src = (document.body.classList.contains("print") ? "../" : "") + "static/search-index.js";
      s.onload = function () { index = window.SEARCH_INDEX || []; cb(); };
      document.head.appendChild(s);
    }
    function escapeHtml(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
    function mark(s, words) {
      var out = escapeHtml(s);
      words.forEach(function (w) {
        out = out.replace(new RegExp("(" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi"), "<mark>$1</mark>");
      });
      return out;
    }
    function snippet(text, word) {
      var i = text.toLowerCase().indexOf(word);
      if (i < 0) return text.slice(0, 140);
      var a = Math.max(0, i - 60);
      return (a ? "… " : "") + text.slice(a, a + 160) + "…";
    }
    function run() {
      var q = input.value.trim().toLowerCase();
      if (q.length < 2) { box.hidden = true; return; }
      var words = q.split(/\s+/);
      var hits = [];
      index.forEach(function (e) {
        var title = e.t.toLowerCase(), body = e.x.toLowerCase(), score = 0;
        for (var i = 0; i < words.length; i++) {
          var inT = title.indexOf(words[i]) >= 0, inB = body.indexOf(words[i]) >= 0;
          if (!inT && !inB) return;
          score += (inT ? 10 : 0) + (inB ? 1 : 0);
        }
        hits.push({ e: e, s: score });
      });
      hits.sort(function (a, b) { return b.s - a.s; });
      active = -1;
      box.innerHTML = hits.length ? hits.slice(0, 20).map(function (h) {
        var e = h.e;
        return '<a href="' + e.u + '"><div class="r-where">' + escapeHtml(e.m) + (e.n ? " · §" + e.n : "") + "</div>" +
          "<div>" + mark(e.t, words) + '</div><div class="r-snip">' + mark(snippet(e.x, words[0]), words) + "</div></a>";
      }).join("") : '<div class="none">No matches</div>';
      box.hidden = false;
    }
    input.addEventListener("input", function () { load(run); });
    input.addEventListener("focus", function () { if (input.value.trim().length >= 2) load(run); });
    input.addEventListener("keydown", function (ev) {
      var items = box.querySelectorAll("a");
      if (ev.key === "Escape") { box.hidden = true; input.blur(); return; }
      if (!items.length) return;
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        if (active >= 0) items[active].classList.remove("active");
        active = (active + (ev.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items[active].classList.add("active");
        items[active].scrollIntoView({ block: "nearest" });
      } else if (ev.key === "Enter") {
        window.location.href = items[Math.max(active, 0)].getAttribute("href");
      }
    });
    document.addEventListener("click", function (ev) {
      if (!box.contains(ev.target) && ev.target !== input) box.hidden = true;
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "/" && document.activeElement !== input) { ev.preventDefault(); input.focus(); }
    });
  }
})();

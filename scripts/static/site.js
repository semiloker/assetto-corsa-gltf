/* Theme toggle, mobile navigation, and the on-this-page highlight. */
(function () {
  'use strict';

  /* ---- theme ----------------------------------------------------------- */
  var KEY = 'acgltf-theme';
  var root = document.documentElement;

  try {
    var saved = localStorage.getItem(KEY);
    if (saved === 'dark' || saved === 'light') root.dataset.theme = saved;
  } catch (e) { /* private window, blocked storage: the media query still works */ }

  var toggle = document.querySelector('.theme');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var dark = root.dataset.theme
        ? root.dataset.theme === 'dark'
        : window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.dataset.theme = dark ? 'light' : 'dark';
      try { localStorage.setItem(KEY, root.dataset.theme); } catch (e) {}
    });
  }

  /* ---- mobile navigation ----------------------------------------------- */
  var menu = document.querySelector('.menu');
  var side = document.getElementById('side');
  if (menu && side) {
    menu.addEventListener('click', function () {
      var open = side.classList.toggle('open');
      menu.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  /* ---- on-this-page ---------------------------------------------------- */
  var links = document.querySelectorAll('.toc a[href^="#"]');
  if (links.length && 'IntersectionObserver' in window) {
    var byId = {};
    var targets = [];
    links.forEach(function (a) {
      var el = document.getElementById(decodeURIComponent(a.hash.slice(1)));
      if (el) { byId[el.id] = a; targets.push(el); }
    });
    var seen = new Set();
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) seen.add(en.target.id);
        else seen.delete(en.target.id);
      });
      var first = targets.find(function (t) { return seen.has(t.id); });
      links.forEach(function (a) { a.style.color = ''; });
      if (first && byId[first.id]) byId[first.id].style.color = 'var(--accent)';
    }, { rootMargin: '-80px 0px -70% 0px' });
    targets.forEach(function (t) { io.observe(t); });
  }
})();

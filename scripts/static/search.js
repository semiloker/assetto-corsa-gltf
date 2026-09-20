/* Site search.
 *
 * The index is search-index.json, built by scripts/build_site.py from the
 * rendered pages, one entry per heading-delimited section. This file turns it
 * into an inverted index in the browser and answers queries against it.
 *
 * No dependency, and no server: the whole corpus is a few tens of kilobytes,
 * which is smaller than the library that would otherwise search it, and it is
 * fetched once on the first keystroke rather than with the page.
 *
 * The engine below is kept separate from the wiring under it so that
 * tests/test_search.js can drive the real thing under Node against the real
 * index, rather than a second implementation that only agrees with itself.
 */
(function () {
  'use strict';

  /* ---- tokenising ------------------------------------------------------ */
  /* Split on anything that is not a letter or a digit. That folds `--glb` to
   * `glb` and `.kn5` to `kn5`, which is what someone typing either expects.
   * `5` survives the length filter on its own because `kn5` splits to it. */
  function tokens(s) {
    return String(s).toLowerCase().split(/[^a-z0-9]+/).filter(function (t) {
      return t.length > 1 || t === '5';
    });
  }

  /* Plurals only, and conservatively. Someone typing `livery` should find the
   * section headed "Liveries and paint", and `texture` the paragraph about
   * textures; a full stemmer would also conflate `converting` with `convert`
   * and `encrypted` with `encrypt`, which on this corpus buys nothing and
   * costs precision. Both the raw term and its stem are indexed, so an exact
   * match still outranks a stemmed one. */
  function stem(t) {
    if (t.length > 4 && t.slice(-3) === 'ies') return t.slice(0, -3) + 'y';
    if (t.length > 3 && t.slice(-1) === 's' &&
        t.slice(-2) !== 'ss' && t.slice(-2) !== 'us') return t.slice(0, -1);
    return t;
  }

  /* ---- building the inverted index ------------------------------------- */
  function build(data) {
    var secs = [];
    var terms = new Map();

    function post(term, sec, weight) {
      add(term, sec, weight);
      var st = stem(term);
      if (st !== term) add(st, sec, weight);
    }

    function add(term, sec, weight) {
      var list = terms.get(term);
      if (!list) terms.set(term, (list = []));
      var last = list[list.length - 1];
      if (last && last.s === sec) last.w += weight;
      else list.push({ s: sec, w: weight });
    }

    data.pages.forEach(function (page) {
      page.s.forEach(function (section, i) {
        var id = secs.length;
        secs.push({
          url: page.u,
          page: page.t,
          heading: section.h || page.t,
          anchor: section.a,
          /* The page description is searchable, so it has to be part of the
           * text the snippet is cut from too -- otherwise a page can match on
           * its description and then show an excerpt with nothing highlighted
           * in it, which reads as a broken result. */
          text: i === 0 ? (page.d + ' ' + section.x).trim() : section.x,
          lead: i === 0
        });
        /* Field weights. A hit in a page title or a heading says more about
         * what the section is about than the twentieth word of a paragraph,
         * and without this every long page outranks the page named after the
         * thing being searched for. */
        tokens(page.t).forEach(function (t) { post(t, id, 8); });
        tokens(section.h || '').forEach(function (t) { post(t, id, 6); });
        if (i === 0) tokens(page.d).forEach(function (t) { post(t, id, 3); });
        tokens(section.x).forEach(function (t) { post(t, id, 1); });
      });
    });

    /* Length normalisation, so a 900-word section does not beat a precise
     * 40-word one on raw term counts alone. */
    secs.forEach(function (s) {
      s.norm = 1 / Math.sqrt(1 + tokens(s.text).length / 60);
    });

    return { terms: terms, secs: secs, list: Array.from(terms.keys()) };
  }

  /* ---- querying -------------------------------------------------------- */
  function matchesFor(index, token) {
    /* Exact term first, then any term it is a prefix of, so results appear
     * while the word is still being typed. The prefix hits are damped, or
     * `car` would rank `carpaint` above `cars`. */
    var hits = new Map();
    var exact = index.terms.get(token);
    if (exact) exact.forEach(function (p) { hits.set(p.s, p.w * 2); });
    var st = stem(token);
    if (st !== token) {
      var stemmed = index.terms.get(st);
      if (stemmed) {
        stemmed.forEach(function (p) {
          hits.set(p.s, Math.max(hits.get(p.s) || 0, p.w * 1.6));
        });
      }
    }
    if (token.length >= 2) {
      index.list.forEach(function (term) {
        if (term.length > token.length && term.startsWith(token)) {
          var damp = token.length / term.length;
          index.terms.get(term).forEach(function (p) {
            hits.set(p.s, Math.max(hits.get(p.s) || 0, p.w * damp));
          });
        }
      });
    }
    return hits;
  }

  function search(index, query, limit) {
    var qt = tokens(query);
    if (!index || !qt.length) return [];

    var scores = new Map();
    var hitCount = new Map();
    qt.forEach(function (t) {
      matchesFor(index, t).forEach(function (w, sec) {
        scores.set(sec, (scores.get(sec) || 0) + w);
        hitCount.set(sec, (hitCount.get(sec) || 0) + 1);
      });
    });

    /* Every word has to appear somewhere in the section. Two-word queries are
     * the common case, and an OR would bury the section that has both under a
     * dozen that have only the commoner word. If nothing satisfies all of
     * them, fall back rather than show an empty panel. */
    var all = [];
    var some = [];
    scores.forEach(function (score, sec) {
      var row = { sec: sec, score: score * index.secs[sec].norm };
      if (hitCount.get(sec) === qt.length) all.push(row);
      else some.push(row);
    });
    var rows = all.length ? all : some;
    rows.sort(function (a, b) { return b.score - a.score; });

    /* At most two sections from any one page, so a long page cannot fill the
     * panel with itself. */
    var seen = new Map();
    var out = [];
    for (var i = 0; i < rows.length && out.length < (limit || 8); i++) {
      var s = index.secs[rows[i].sec];
      var n = seen.get(s.url) || 0;
      if (n >= 2) continue;
      seen.set(s.url, n + 1);
      out.push({ sec: s, score: rows[i].score, q: qt });
    }
    return out;
  }

  /* ---- rendering helpers ----------------------------------------------- */
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function reEscape(t) {
    return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /* Wrap every query term in <mark>, escaping as it goes. Walking the match
   * ranges rather than substituting into already-escaped text: a placeholder
   * scheme has to pick a character that cannot occur in the corpus, and there
   * is no such character. */
  function highlight(text, qt) {
    if (!qt || !qt.length) return esc(text);
    var re = new RegExp(qt.map(reEscape).join('|'), 'gi');
    var out = '';
    var last = 0;
    var m;
    while ((m = re.exec(text)) !== null) {
      if (!m[0]) { re.lastIndex++; continue; }
      out += esc(text.slice(last, m.index)) + '<mark>' + esc(m[0]) + '</mark>';
      last = m.index + m[0].length;
    }
    return out + esc(text.slice(last));
  }

  function snippet(text, qt) {
    if (!text) return '';
    var lower = text.toLowerCase();
    var at = -1;
    for (var i = 0; i < qt.length; i++) {
      var p = lower.indexOf(qt[i]);
      if (p >= 0 && (at < 0 || p < at)) at = p;
    }
    if (at < 0) {
      return highlight(text.slice(0, 150), qt) + (text.length > 150 ? '…' : '');
    }
    var start = Math.max(0, at - 60);
    /* Start on a word boundary, so a snippet never opens mid-word. */
    if (start > 0) {
      var sp = text.indexOf(' ', start);
      if (sp > 0 && sp < start + 20) start = sp + 1;
    }
    var end = Math.min(text.length, start + 180);
    return (start > 0 ? '…' : '') + highlight(text.slice(start, end), qt) +
           (end < text.length ? '…' : '');
  }

  var engine = {
    tokens: tokens, stem: stem, build: build, search: search,
    esc: esc, highlight: highlight, snippet: snippet
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = engine;
  if (typeof window !== 'undefined') window.acgltfSearch = engine;

  /* ---- the page -------------------------------------------------------- */
  if (typeof document === 'undefined') return;

  var input = document.getElementById('q');
  var panel = document.getElementById('results');
  if (!input || !panel) return;

  var root = document.body.dataset.root || './';
  var form = input.closest('.search');
  var cancel = form && form.querySelector('.search-close');

  var index = null;
  var loading = null;
  var selected = -1;
  var current = [];

  function load() {
    if (loading) return loading;
    loading = fetch(root + 'search-index.json')
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (data) { index = build(data); return index; })
      .catch(function (e) { loading = null; throw e; });
    return loading;
  }

  var STARTERS = [
    ['docs/quick-start/', 'Quick start', 'One car, one file out, in five minutes'],
    ['docs/cli/', 'Command-line reference', 'Every flag of all three commands'],
    ['docs/cars/', 'Converting cars', 'Which .kn5, liveries, LOD twins'],
    ['docs/troubleshooting/', 'Troubleshooting', 'White, black, inside out, or eight boxes'],
    ['docs/faq/', 'FAQ', 'GLB, encryption, licensing, Blender']
  ];

  function foot() {
    return '<div class="res-foot">' +
           '<span><kbd>&uarr;</kbd><kbd>&darr;</kbd> to move</span>' +
           '<span><kbd>Enter</kbd> to open</span>' +
           '<span><kbd>Esc</kbd> to close</span></div>';
  }

  function renderEmpty() {
    panel.innerHTML =
      '<div class="res-msg">Search the documentation &mdash; or start here:</div>' +
      STARTERS.map(function (s) {
        return '<a class="res" role="option" aria-selected="false" href="' +
          root + s[0] + '"><span class="rt">' + esc(s[1]) +
          '</span><span class="rx">' + esc(s[2]) + '</span></a>';
      }).join('') + foot();
    current = Array.prototype.slice.call(panel.querySelectorAll('.res'));
    show();
  }

  function render(results, query) {
    if (!results.length) {
      panel.innerHTML = '<div class="res-msg">No matches for <b>' +
        esc(query) + '</b>.<br>Try a shorter word, or a term from the file ' +
        'format &mdash; <b>glb</b>, <b>skin</b>, <b>surfaces</b>, <b>lod</b>.</div>';
      current = [];
      show();
      return;
    }
    panel.innerHTML = results.map(function (r) {
      var s = r.sec;
      var href = root + s.url + (s.anchor && !s.lead ? '#' + s.anchor : '');
      /* On the section that IS the page, the crumb would repeat the title. */
      var crumb = s.heading === s.page ? '' : s.page;
      return '<a class="res" role="option" aria-selected="false" href="' +
        esc(href) + '">' +
        (crumb ? '<span class="crumb">' + esc(crumb) + '</span>' : '') +
        '<span class="rt">' + highlight(s.heading, r.q) + '</span>' +
        '<span class="rx">' + snippet(s.text, r.q) + '</span></a>';
    }).join('') + foot();
    current = Array.prototype.slice.call(panel.querySelectorAll('.res'));
    show();
  }

  function show() {
    selected = -1;
    panel.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    panel.scrollTop = 0;
  }

  function hide() {
    panel.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    selected = -1;
    document.body.classList.remove('searching');
  }

  function select(i) {
    if (!current.length) return;
    if (selected >= 0) {
      current[selected].classList.remove('sel');
      current[selected].setAttribute('aria-selected', 'false');
    }
    selected = (i + current.length) % current.length;
    var el = current[selected];
    el.classList.add('sel');
    el.setAttribute('aria-selected', 'true');
    if (!el.id) el.id = 'res-' + selected;
    input.setAttribute('aria-activedescendant', el.id);
    el.scrollIntoView({ block: 'nearest' });
  }

  var timer = null;

  function run() {
    var q = input.value.trim();
    if (!q) { renderEmpty(); return; }
    load().then(function () {
      if (input.value.trim() !== q) return;     // typed on while it loaded
      render(search(index, q), q);
    }).catch(function () {
      panel.innerHTML = '<div class="res-msg">The search index could not be ' +
        'loaded. <b>Reload the page</b>, or browse the ' +
        '<a href="' + root + 'docs/">documentation</a> directly.</div>';
      current = [];
      show();
    });
  }

  input.addEventListener('input', function () {
    clearTimeout(timer);
    /* Short enough to feel instant, long enough that a fast typist does not
     * score eight queries on the way to one word. */
    timer = setTimeout(run, 60);
  });

  input.addEventListener('focus', function () {
    document.body.classList.add('searching');
    load().catch(function () {});
    if (panel.hidden) run();
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); select(selected + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); select(selected - 1); }
    else if (e.key === 'Enter') {
      var go = selected >= 0 ? current[selected] : current[0];
      if (go) { e.preventDefault(); window.location.href = go.href; }
    } else if (e.key === 'Escape') {
      if (input.value) { input.value = ''; run(); }
      else { hide(); input.blur(); }
    }
  });

  if (cancel) {
    cancel.addEventListener('click', function () {
      input.value = '';
      hide();
      input.blur();
    });
  }

  document.addEventListener('click', function (e) {
    if (form && !form.contains(e.target)) hide();
  });

  document.addEventListener('keydown', function (e) {
    var k = (e.key || '').toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'k') {
      e.preventDefault();
      input.focus();
      input.select();
      return;
    }
    if (k === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var t = e.target;
      var typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
                         t.isContentEditable);
      if (!typing) { e.preventDefault(); input.focus(); }
    }
  });

  /* On a Mac the hint should say what the key is actually called. */
  var hint = form && form.querySelector('.hint');
  if (hint && /Mac|iPhone|iPad/.test(navigator.platform || '')) {
    hint.textContent = '⌘ K';
  }

  /* Warm the index when the browser is otherwise idle, so the first keystroke
   * has nothing to wait for. Best effort only. */
  if ('requestIdleCallback' in window) {
    requestIdleCallback(function () { load().catch(function () {}); },
                        { timeout: 4000 });
  }
})();

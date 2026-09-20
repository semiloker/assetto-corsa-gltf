/* The site search, exercised against the index the site actually ships.
 *
 *     python scripts/build_site.py && node tests/test_search.js
 *
 * It loads scripts/static/search.js -- the same file the browser gets, not a
 * copy of its logic -- and runs real queries through it. What is pinned here is
 * the behaviour a reader would notice: that searching for a thing finds the
 * page about that thing rather than the longest page mentioning it, that a
 * half-typed word already returns something, and that nothing user-supplied
 * reaches the results panel as markup.
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const INDEX = path.join(ROOT, 'site', 'search-index.json');

if (!fs.existsSync(INDEX)) {
  console.error('no site/search-index.json -- run: python scripts/build_site.py');
  process.exit(1);
}

const engine = require(path.join(ROOT, 'scripts', 'static', 'search.js'));
const data = JSON.parse(fs.readFileSync(INDEX, 'utf8'));
const index = engine.build(data);

let failures = 0;

function check(name, fn) {
  try {
    fn();
    console.log('ok  ' + name);
  } catch (e) {
    failures++;
    console.log('FAIL ' + name + '\n     ' + e.message);
  }
}

function top(query, n) {
  return engine.search(index, query, n || 8).map(function (r) {
    return { url: r.sec.url, anchor: r.sec.anchor, heading: r.sec.heading };
  });
}

function urls(query) {
  return top(query).map(function (r) { return r.url; });
}

/* ---- the index itself ---------------------------------------------------- */
check('index      every page contributes sections', function () {
  assert.ok(data.pages.length >= 15, 'only ' + data.pages.length + ' pages');
  data.pages.forEach(function (p) {
    assert.ok(p.s.length > 0, p.u + ' indexed no sections');
    assert.ok(p.t && p.d, p.u + ' is missing a title or description');
  });
  const words = index.secs.reduce(function (n, s) {
    return n + engine.tokens(s.text).length;
  }, 0);
  assert.ok(words > 5000, 'only ' + words + ' words indexed');
});

check('index      the landing page is searchable too', function () {
  const home = data.pages.filter(function (p) { return p.u === ''; });
  assert.strictEqual(home.length, 1, 'no entry for the landing page');
  assert.ok(home[0].s.length > 5, 'the landing page indexed too little');
});

check('index      no permalink glyphs leaked into headings', function () {
  index.secs.forEach(function (s) {
    assert.ok(!/#$/.test(s.heading), 'heading ends with #: ' + s.heading);
  });
});

/* ---- finding the right page ---------------------------------------------- */
const EXPECT = [
  ['glb', 'docs/cli/'],
  ['liveries and paint', 'docs/cars/'],
  ['white car', 'docs/troubleshooting/'],
  ['surfaces.ini', 'docs/tracks/'],
  ['blender', 'docs/workflow/'],
  ['install', 'docs/installation/'],
  ['encrypted', 'docs/limitations/'],
  ['clearcoat', 'docs/output/'],
  ['kn5-studio', 'docs/preview/'],
  ['keep-variants', 'docs/cli/'],
  ['suspension survey', 'docs/cli/'],
  ['running the tests', 'docs/development/']
];

EXPECT.forEach(function (pair) {
  check('query      "' + pair[0] + '" reaches ' + pair[1], function () {
    const got = urls(pair[0]);
    assert.ok(got.length, 'no results at all');
    assert.ok(got.slice(0, 3).indexOf(pair[1]) >= 0,
              'top 3 were ' + JSON.stringify(got.slice(0, 3)));
  });
});

check('query      a one-word query stays on topic', function () {
  /* Half a dozen pages legitimately answer "livery", so pinning one of them as
   * the top hit would be pinning the tie-break rather than the behaviour. What
   * has to hold is that nothing off-topic gets in. */
  const rows = engine.search(index, 'livery');
  assert.ok(rows.length >= 4, 'only ' + rows.length + ' results');
  rows.forEach(function (r) {
    const hay = (r.sec.heading + ' ' + r.sec.text).toLowerCase();
    assert.ok(/liver|skin|paint/.test(hay),
              'off-topic hit: ' + r.sec.url + ' / ' + r.sec.heading);
  });
});

check('query      the plural stem joins livery to liveries', function () {
  assert.strictEqual(engine.stem('liveries'), 'livery');
  assert.strictEqual(engine.stem('textures'), 'texture');
  assert.strictEqual(engine.stem('glass'), 'glass');     // not 'glas'
  assert.strictEqual(engine.stem('kn5'), 'kn5');
  assert.ok(index.terms.has('livery'), 'no stemmed posting for livery');
  const headings = engine.search(index, 'livery').map(function (r) {
    return r.sec.heading;
  });
  assert.ok(headings.some(function (h) { return /liveries/i.test(h); }),
            'a plural heading was not reached from the singular');
});

check('query      a flag lands on its own section, not the page top', function () {
  const hit = top('--glb').filter(function (r) { return r.anchor === 'glb'; });
  assert.ok(hit.length, 'no result anchored at #glb');
});

check('query      punctuation is ignored, so --glb and glb agree', function () {
  assert.deepStrictEqual(urls('--glb'), urls('glb'));
  assert.deepStrictEqual(urls('.kn5'), urls('kn5'));
});

check('query      a prefix finds the word before it is finished', function () {
  ['troub', 'liver', 'converti', 'instal'].forEach(function (q) {
    assert.ok(engine.search(index, q).length, 'nothing for "' + q + '"');
  });
});

check('query      two words prefer the section holding both', function () {
  const r = engine.search(index, 'texture case');
  assert.ok(r.length, 'no results');
  const text = (r[0].sec.heading + ' ' + r[0].sec.text).toLowerCase();
  assert.ok(text.indexOf('case') >= 0 && text.indexOf('texture') >= 0,
            'best hit had only one of the words: ' + r[0].sec.heading);
});

check('query      nonsense returns nothing rather than everything', function () {
  assert.strictEqual(engine.search(index, 'zzzzqqqq').length, 0);
  assert.strictEqual(engine.search(index, '').length, 0);
  assert.strictEqual(engine.search(index, '   ').length, 0);
});

check('query      one page cannot fill the panel', function () {
  const counts = {};
  urls('the').forEach(function (u) { counts[u] = (counts[u] || 0) + 1; });
  Object.keys(counts).forEach(function (u) {
    assert.ok(counts[u] <= 2, u + ' returned ' + counts[u] + ' rows');
  });
});

check('query      results are capped', function () {
  assert.ok(engine.search(index, 'the').length <= 8);
});

/* ---- what gets rendered -------------------------------------------------- */
check('render     query terms come back marked', function () {
  const out = engine.highlight('Convert a kn5 to GLB', ['glb']);
  assert.ok(out.indexOf('<mark>GLB</mark>') >= 0, out);
});

check('render     markup in the corpus is escaped, not run', function () {
  const out = engine.highlight('<script>alert(1)</script> glb', ['glb']);
  assert.ok(out.indexOf('<script>') < 0, 'raw script tag survived: ' + out);
  assert.ok(out.indexOf('&lt;script&gt;') >= 0, out);
  assert.ok(out.indexOf('<mark>glb</mark>') >= 0, out);
});

check('render     a regex in the query is a literal, not a pattern', function () {
  // `.*` would match everything if the term reached RegExp unescaped.
  const out = engine.highlight('nothing to see', ['.*']);
  assert.strictEqual(out, 'nothing to see');
  assert.doesNotThrow(function () { engine.highlight('x', ['(', '[a-']); });
  assert.doesNotThrow(function () { engine.search(index, '(((['); });
});

check('render     a snippet is short and centred on the match', function () {
  const long = index.secs.filter(function (s) { return s.text.length > 600; })[0];
  assert.ok(long, 'no long section to test with');
  const word = engine.tokens(long.text).filter(function (t) {
    return t.length > 5 && long.text.toLowerCase().indexOf(t) > 400;
  })[0];
  assert.ok(word, 'no late word to search for');
  const out = engine.snippet(long.text, [word]);
  assert.ok(out.length < 400, 'snippet was ' + out.length + ' chars');
  assert.ok(out.indexOf('<mark>') >= 0, 'the match was not marked');
  assert.ok(out.charAt(0) === '…', 'a mid-text snippet should be elided');
});

check('render     every result can be turned into a real link', function () {
  top('glb').concat(top('livery')).forEach(function (r) {
    const rel = r.url + (r.anchor ? '#' + r.anchor : '');
    assert.ok(!/^\//.test(rel), 'result url must stay relative: ' + rel);
    const file = path.join(ROOT, 'site', r.url, 'index.html');
    assert.ok(fs.existsSync(file), 'no page on disk for ' + r.url);
  });
});

console.log('');
if (failures) {
  console.log(failures + ' failed');
  process.exit(1);
}
console.log('all good');

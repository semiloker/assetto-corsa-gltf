#!/usr/bin/env python3
"""The built site, checked the way a crawler and a reader would find it wrong.

    python scripts/build_site.py && python tests/test_site.py

A static site fails quietly. A link goes stale, a canonical points at the wrong
host, a page loses its description, and nothing errors -- it just stops being
findable, months later, in a tool nobody runs locally. So every page the
generator produced is read back off disk here and checked against what it
claims: that its links resolve, that its metadata is present and consistent
with its URL, that the sitemap and the search index describe exactly the pages
that exist, and that the headings go down one level at a time.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
BASE = 'https://semiloker.github.io/assetto-corsa-gltf'

failures = []


def check(name, fn):
    try:
        fn()
        print('ok  %s' % name)
    except AssertionError as e:
        failures.append(name)
        print('FAIL %s\n     %s' % (name, e))


class Page(HTMLParser):
    """Everything about one page the checks below need, in a single pass."""

    def __init__(self, path, url):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.url = url
        self.links = []          # (href, line)
        self.ids = set()
        self.headings = []       # (level, text)
        self.meta = {}           # name/property -> content
        self.title = None
        self.lang = None
        self.jsonld = []
        self.images = []
        self.assets = []         # css/js/icon the page needs
        self._in_title = False
        self._in_ld = False
        self._ld = []
        self._heading = None
        self._in_main = False
        with open(path, encoding='utf-8') as f:
            self.feed(f.read())

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.add(a['id'])
        if tag == 'html':
            self.lang = a.get('lang')
        elif tag == 'title':
            self._in_title = True
        elif tag == 'meta':
            key = a.get('name') or a.get('property')
            if key:
                self.meta[key] = a.get('content', '')
        elif tag == 'link':
            rel = (a.get('rel') or '').lower()
            if 'canonical' in rel:
                self.meta['canonical'] = a.get('href', '')
            elif a.get('href'):
                self.assets.append(a['href'])
        elif tag == 'script':
            if a.get('type') == 'application/ld+json':
                self._in_ld = True
                self._ld = []
            elif a.get('src'):
                self.assets.append(a['src'])
        elif tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        elif tag == 'img':
            self.images.append(a)
        elif tag == 'main':
            self._in_main = True
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and self._in_main:
            self._heading = [int(tag[1]), []]

    def handle_endtag(self, tag):
        if tag == 'main':
            self._in_main = False
        elif tag == 'title':
            self._in_title = False
        elif tag == 'script' and self._in_ld:
            self.jsonld.append(''.join(self._ld))
            self._in_ld = False
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and self._heading:
            self.headings.append((self._heading[0],
                                  ''.join(self._heading[1]).strip()))
            self._heading = None

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or '') + data
        elif self._in_ld:
            self._ld.append(data)
        elif self._heading is not None:
            self._heading[1].append(data)


def load_pages():
    assert os.path.isdir(SITE), 'no site/ -- run: python scripts/build_site.py'
    pages = []
    for dirpath, _dirs, files in os.walk(SITE):
        if 'index.html' not in files:
            continue
        path = os.path.join(dirpath, 'index.html')
        rel = os.path.relpath(dirpath, SITE).replace(os.sep, '/')
        url = '' if rel == '.' else rel + '/'
        pages.append(Page(path, url))
    return sorted(pages, key=lambda p: p.url)


PAGES = load_pages()
BY_URL = {p.url: p for p in PAGES}


def resolve(page, href):
    """A relative href from `page` -> a site-root-relative path, or None if the
    link leaves the site."""
    if href.startswith(('http://', 'https://', 'mailto:', 'tel:')):
        return None
    if href.startswith('#'):
        return page.url + href
    return urljoin('/' + page.url, href).lstrip('/')


# ---- structure -------------------------------------------------------------
def test_the_expected_pages_were_built():
    assert len(PAGES) >= 15, 'only %d pages' % len(PAGES)
    assert '' in BY_URL, 'no landing page'
    assert 'docs/' in BY_URL, 'no documentation index'
    for must in ('docs/installation/', 'docs/cli/', 'docs/troubleshooting/'):
        assert must in BY_URL, 'missing %s' % must


def test_no_template_placeholder_survived():
    stray = re.compile(r'\{(root|assets|head|body|nav|toc|repo|year|version|'
                       r'sitename|edit|prevnext|lang)\}')
    for p in PAGES:
        with open(p.path, encoding='utf-8') as f:
            hit = stray.search(f.read())
        assert not hit, '%s still contains %s' % (p.url or '/', hit.group(0))


def test_every_internal_link_resolves():
    for p in PAGES:
        for href in p.links:
            target = resolve(p, href)
            if target is None:
                continue
            path, frag = urldefrag(target)
            assert path in BY_URL, \
                '%s links to %s, which was not built' % (p.url or '/', href)
            if frag:
                assert frag in BY_URL[path].ids, \
                    '%s links to #%s on %s, which has no such anchor' \
                    % (p.url or '/', frag, path or '/')


def test_every_asset_a_page_asks_for_exists():
    for p in PAGES:
        for href in p.assets:
            target = resolve(p, href)
            if target is None:
                continue
            path = os.path.join(SITE, *target.split('/'))
            assert os.path.isfile(path), \
                '%s references %s, which is not on disk' % (p.url or '/', href)


def test_every_page_is_reachable_from_the_landing_page():
    """An orphan is a page a crawler reaches only through the sitemap."""
    seen = {''}
    queue = ['']
    while queue:
        p = BY_URL[queue.pop()]
        for href in p.links:
            target = resolve(p, href)
            if target is None:
                continue
            path = urldefrag(target)[0]
            if path in BY_URL and path not in seen:
                seen.add(path)
                queue.append(path)
    orphans = sorted(set(BY_URL) - seen)
    assert not orphans, 'unreachable by link: %s' % ', '.join(orphans)


# ---- metadata --------------------------------------------------------------
def test_every_page_declares_what_it_is():
    for p in PAGES:
        who = p.url or '/'
        assert p.lang == 'en', '%s has no lang' % who
        assert p.title and len(p.title) > 10, '%s has no usable title' % who
        assert len(p.title) <= 70, '%s title is %d chars' % (who, len(p.title))
        desc = p.meta.get('description', '')
        assert 50 <= len(desc) <= 200, \
            '%s description is %d chars' % (who, len(desc))
        assert p.meta.get('viewport'), '%s has no viewport' % who


def test_canonical_urls_match_where_the_page_actually_is():
    for p in PAGES:
        want = '%s/%s' % (BASE, p.url)
        assert p.meta.get('canonical') == want, \
            '%s canonical is %r, expected %r' % (p.url or '/',
                                                 p.meta.get('canonical'), want)
        assert p.meta.get('og:url') == want, '%s og:url is wrong' % (p.url or '/')


def test_social_cards_are_complete():
    for p in PAGES:
        who = p.url or '/'
        for key in ('og:type', 'og:site_name', 'og:title', 'og:description',
                    'og:image', 'og:image:alt'):
            assert p.meta.get(key), '%s has no %s' % (who, key)
        assert p.meta.get('twitter:card') == 'summary_large_image', who
        assert p.meta.get('twitter:title') and p.meta.get('twitter:image'), who
        assert p.meta['og:image'].startswith(BASE), who
        assert p.meta['og:title'] == p.title, '%s og:title drifted' % who
        assert p.meta['og:description'] == p.meta['description'], \
            '%s og:description drifted' % who


def test_structured_data_parses_and_points_at_the_page():
    for p in PAGES:
        who = p.url or '/'
        assert len(p.jsonld) >= 2, '%s has %d ld+json blocks' % (who, len(p.jsonld))
        kinds = set()
        for blob in p.jsonld:
            try:
                doc = json.loads(blob)
            except ValueError as e:
                raise AssertionError('%s has invalid ld+json: %s' % (who, e))
            assert doc.get('@context') == 'https://schema.org', who
            kinds.add(doc['@type'])
            if doc['@type'] == 'BreadcrumbList':
                items = doc['itemListElement']
                assert items[0]['item'] == BASE + '/', who
                positions = [i['position'] for i in items]
                assert positions == list(range(1, len(items) + 1)), who
            elif 'url' in doc:
                assert doc['url'].startswith(BASE), who
        assert 'BreadcrumbList' in kinds, '%s has no breadcrumbs' % who


def test_headings_go_down_one_level_at_a_time():
    for p in PAGES:
        who = p.url or '/'
        levels = [lv for lv, _ in p.headings]
        assert levels.count(1) == 1, '%s has %d h1' % (who, levels.count(1))
        assert levels[0] == 1, '%s does not start with its h1' % who
        prev = 1
        for lv, text in p.headings:
            assert lv <= prev + 1, \
                '%s jumps from h%d to h%d at %r' % (who, prev, lv, text)
            prev = lv
        for lv, text in p.headings:
            assert text, '%s has an empty h%d' % (who, lv)


def test_images_carry_alt_text():
    for p in PAGES:
        for img in p.images:
            assert 'alt' in img, \
                '%s has an <img> with no alt: %s' % (p.url or '/', img.get('src'))


# ---- crawler files ---------------------------------------------------------
def test_the_sitemap_lists_exactly_the_pages_that_exist():
    tree = ET.parse(os.path.join(SITE, 'sitemap.xml'))
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    locs = [e.text for e in tree.getroot().findall('s:url/s:loc', ns)]
    assert locs, 'the sitemap is empty'
    want = sorted('%s/%s' % (BASE, p.url) for p in PAGES)
    assert sorted(locs) == want, \
        'sitemap and site disagree:\n  only in sitemap: %s\n  only on disk: %s' \
        % (sorted(set(locs) - set(want)), sorted(set(want) - set(locs)))
    for e in tree.getroot().findall('s:url', ns):
        assert e.find('s:lastmod', ns) is not None, 'a url has no lastmod'


def test_robots_allows_crawling_and_names_the_sitemap():
    with open(os.path.join(SITE, 'robots.txt'), encoding='utf-8') as f:
        txt = f.read()
    assert 'User-agent: *' in txt
    assert 'Disallow: /' not in txt, 'robots.txt blocks the whole site'
    assert 'Sitemap: %s/sitemap.xml' % BASE in txt
    assert os.path.isfile(os.path.join(SITE, 'sitemap.xml'))


def test_jekyll_is_disabled():
    """GitHub Pages runs Jekyll otherwise, and Jekyll eats _-prefixed paths."""
    assert os.path.isfile(os.path.join(SITE, '.nojekyll'))


def test_the_search_index_covers_every_page():
    with open(os.path.join(SITE, 'search-index.json'), encoding='utf-8') as f:
        data = json.load(f)
    indexed = {p['u'] for p in data['pages']}
    assert indexed == set(BY_URL), \
        'index and site disagree:\n  only indexed: %s\n  only on disk: %s' \
        % (sorted(indexed - set(BY_URL)), sorted(set(BY_URL) - indexed))
    for entry in data['pages']:
        page = BY_URL[entry['u']]
        assert entry['t'] and entry['d'], '%s indexed without metadata' % entry['u']
        assert entry['s'], '%s indexed no sections' % entry['u']
        for sec in entry['s']:
            if sec['a']:
                assert sec['a'] in page.ids, \
                    '%s indexes anchor #%s, which is not on the page' \
                    % (entry['u'] or '/', sec['a'])


def test_the_index_is_small_enough_to_fetch():
    size = os.path.getsize(os.path.join(SITE, 'search-index.json'))
    assert size < 400 * 1024, 'the search index is %.0f KB' % (size / 1024)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            check(name[5:].replace('_', ' '), fn)
    print('')
    if failures:
        print('%d failed' % len(failures))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    sys.exit(main())

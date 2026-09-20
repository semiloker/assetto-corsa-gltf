#!/usr/bin/env python3
"""Build the project website from docs/*.md.

    pip install -e ".[docs]"
    python scripts/build_site.py [--base-url URL] [--out site]

One Markdown file becomes one page at a clean URL: docs/installation.md ->
/docs/installation/. Front matter supplies the title and the meta description,
which between them drive <title>, the description tag, Open Graph, the Twitter
card and the canonical link, so adding a page is adding a file.

Two things here are deliberate rather than incidental.

THE SEARCH INDEX IS BUILT FROM THE RENDERED PAGES, not from the Markdown. It is
the same HTML a reader gets, parsed back into heading-delimited sections. That
costs one extra parse and buys the guarantee that the index cannot describe
something the page does not say -- including for the landing page, which is a
template rather than a document and would otherwise be invisible to search.

LINKS ARE CHECKED AND A BAD ONE FAILS THE BUILD. Internal links are written as
`installation.md#requirements` so they work on GitHub too, and are rewritten to
`../installation/#requirements` here. Every target, anchor included, is resolved
against the pages actually produced; a typo is a build error rather than a 404
somebody finds later.
"""
import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import date
from html.parser import HTMLParser

try:
    import markdown
except ImportError:                                    # noqa: BLE001
    sys.exit('needs Python-Markdown:  pip install -e ".[docs]"')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

BASE_URL = 'https://semiloker.github.io/assetto-corsa-gltf'
REPO = 'https://github.com/semiloker/assetto-corsa-gltf'
SITE_NAME = 'assetto-corsa-gltf'
TAGLINE = 'Assetto Corsa .kn5 to glTF 2.0 / GLB'

# The order is the navigation, the sitemap, and the prev/next chain. A document
# not listed here is not part of the site -- which is checked below, so adding a
# file and forgetting this line is an error rather than a silently orphaned page.
NAV = [
    ('Getting started', [
        ('index', 'Introduction'),
        ('installation', 'Installation'),
        ('quick-start', 'Quick start'),
    ]),
    ('Converting', [
        ('cars', 'Converting cars'),
        ('tracks', 'Converting tracks'),
        ('preview', 'Previewing with kn5-studio'),
    ]),
    ('Reference', [
        ('cli', 'Command-line reference'),
        ('output', 'The glTF output'),
        ('supported-files', 'Supported files'),
        ('workflow', 'Blender, three.js and Unity'),
    ]),
    ('Help', [
        ('troubleshooting', 'Troubleshooting'),
        ('faq', 'FAQ'),
        ('limitations', 'Limitations'),
    ]),
    ('Project', [
        ('development', 'Development'),
    ]),
]
ORDER = [slug for _, group in NAV for slug, _ in group]


# --- front matter -----------------------------------------------------------
def split_front_matter(text):
    """`---` delimited key: value block at the top of a document.

    Hand-rolled rather than pulled in with PyYAML: it is two keys, the whole
    grammar is `key: value` on one line, and a documentation build should not
    need a parser it could not explain.
    """
    if not text.startswith('---\n'):
        return {}, text
    end = text.find('\n---\n', 4)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip()
    return meta, text[end + 5:]


# --- turning rendered HTML back into indexable sections ---------------------
SKIP_TAGS = {'script', 'style', 'nav', 'svg'}
HEADINGS = {'h1', 'h2', 'h3', 'h4'}
# The toc extension hangs a permalink anchor inside every heading. Indexed
# it appends a '#' to the heading text and puts a stray hit on every one.
SKIP_CLASSES = ('search-skip', 'headerlink')


class Sectioniser(HTMLParser):
    """Rendered page -> [(anchor, heading, text)], one per h1/h2/h3.

    Reading the output rather than the source is what keeps the index honest:
    anything a template adds is indexed, anything Markdown drops is not.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = [['', '', []]]
        self.skip = 0
        self.in_heading = None
        self.indexing = False
        self.open_skips = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'main':
            self.indexing = True
            return
        if not self.indexing:
            return
        cls = a.get('class') or ''
        if tag in SKIP_TAGS or any(c in cls for c in SKIP_CLASSES):
            self.skip += 1
            self.open_skips.append(tag)
        elif tag in HEADINGS:
            self.in_heading = [a.get('id', ''), []]

    def handle_endtag(self, tag):
        if tag == 'main':
            self.indexing = False
            return
        if not self.indexing:
            return
        if self.open_skips and self.open_skips[-1] == tag:
            self.open_skips.pop()
            self.skip = max(0, self.skip - 1)
        elif tag in HEADINGS and self.in_heading is not None:
            anchor, parts = self.in_heading
            self.sections.append([anchor, ''.join(parts).strip(), []])
            self.in_heading = None

    def handle_data(self, data):
        if not self.indexing or self.skip:
            return
        if self.in_heading is not None:
            self.in_heading[1].append(data)
        else:
            self.sections[-1][2].append(data)

    def result(self):
        out = []
        for anchor, heading, body in self.sections:
            text = re.sub(r'\s+', ' ', ''.join(body)).strip()
            if heading or text:
                out.append({'a': anchor, 'h': heading, 'x': text})
        return out


class AnchorCollector(HTMLParser):
    """Every id= on a rendered page, so links to #fragments can be checked."""

    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        got = dict(attrs).get('id')
        if got:
            self.ids.add(got)


# --- the build --------------------------------------------------------------
class Page:
    def __init__(self, slug, title, description, body, url, nav_title):
        self.slug = slug
        self.title = title
        self.description = description
        self.body = body
        self.url = url                 # '' for home, 'docs/cli/' for a document
        self.nav_title = nav_title
        self.anchors = set()
        self.sections = []

    @property
    def depth(self):
        return self.url.count('/')

    def rel(self, target):
        """A link from this page to a site-root-relative path.

        Relative rather than absolute so the same output works when served from
        a subdirectory (GitHub Pages puts the site under /assetto-corsa-gltf/)
        and from the root of a local preview server, with no base tag and no
        build-time host baked into every href.
        """
        up = '../' * self.depth
        return (up + target) or './'


def read_docs():
    pages = []
    titles = {slug: nav for _, group in NAV for slug, nav in group}
    seen = set()
    for slug in ORDER:
        path = os.path.join(DOCS, slug + '.md')
        if not os.path.isfile(path):
            sys.exit('NAV lists %s.md, which does not exist' % slug)
        with open(path, encoding='utf-8') as f:
            meta, text = split_front_matter(f.read())
        if 'title' not in meta or 'description' not in meta:
            sys.exit('%s.md needs both `title` and `description` front matter' % slug)
        url = 'docs/' if slug == 'index' else 'docs/%s/' % slug
        pages.append(Page(slug, meta['title'], meta['description'], text, url,
                          titles[slug]))
        seen.add(slug)
    stray = {f[:-3] for f in os.listdir(DOCS) if f.endswith('.md')} - seen
    if stray:
        sys.exit('docs/ has %s, which NAV does not list'
                 % ', '.join(sorted(s + '.md' for s in stray)))
    return pages


def flatten_toc(tokens, out):
    for t in tokens:
        if t['level'] == 2:
            out.append((t['id'], t['name']))
        flatten_toc(t.get('children', ()), out)
    return out


def render_markdown(page):
    md = markdown.Markdown(extensions=['extra', 'toc', 'sane_lists'],
                           extension_configs={'toc': {
                               'permalink': '#',
                               'permalink_title': 'Link to this section'}})
    body = md.convert(page.body)
    page.toc = flatten_toc(md.toc_tokens, [])
    return body


LINK_RE = re.compile(r'href="([^"]+)"')
# Documents reference images as ../assets/x.png, which is where they are
# relative to docs/ in the repository -- so the Markdown renders correctly on
# GitHub. On the site the same file is at /assets/x.png, a different number of
# levels up, so the src is rewritten the same way a link is.
IMG_RE = re.compile(r'src="\.\./assets/([^"]+)"')


def rewrite_links(body, page, pages, check=None):
    """`cli.md#--glb` -> `../cli/#--glb`, and report what it could not resolve.

    Documents link to each other by filename so the same Markdown reads
    correctly on GitHub, where there is no site. Here they become the clean URLs
    the pages are actually published at.
    """
    by_slug = {p.slug: p for p in pages}
    problems = []

    def one(m):
        href = m.group(1)
        if href.startswith(('http://', 'https://', 'mailto:', '#')):
            return m.group(0)        # a link off the site, or within this page
        if not href.endswith('.md') and '.md#' not in href:
            return m.group(0)
        target, _, frag = href.partition('#')
        slug = os.path.basename(target)[:-3]
        if slug not in by_slug:
            problems.append(href)
            return m.group(0)
        dest = by_slug[slug]
        if check is not None and frag and frag not in dest.anchors:
            problems.append(href)
        return 'href="%s"' % (page.rel(dest.url) + ('#' + frag if frag else ''))

    out = LINK_RE.sub(one, body)
    out = IMG_RE.sub(lambda m: 'src="%s"' % page.rel('assets/' + m.group(1)), out)
    for m in IMG_RE.finditer(body):
        if not os.path.isfile(os.path.join(ROOT, 'assets', m.group(1))):
            problems.append('../assets/' + m.group(1))
    if check is not None:
        check.extend((page.slug, h) for h in problems)
    return out


def template(name):
    with open(os.path.join(TPL, name), encoding='utf-8') as f:
        return f.read()


def nav_html(page, pages, current):
    by_slug = {p.slug: p for p in pages}
    out = []
    for group, items in NAV:
        # A label, not a heading: these sit before the article's h1 in the
        # document, and as headings they put the page's own outline second.
        out.append('<div class="nav-group"><p class="nav-head">%s</p><ul>'
                   % html.escape(group))
        for slug, label in items:
            cls = ' class="here" aria-current="page"' if slug == current else ''
            out.append('<li><a href="%s"%s>%s</a></li>'
                       % (page.rel(by_slug[slug].url), cls, html.escape(label)))
        out.append('</ul></div>')
    return '\n'.join(out)


def toc_html(page):
    if len(page.toc) < 2:
        return ''
    items = '\n'.join('<li><a href="#%s">%s</a></li>' % (i, html.escape(n))
                      for i, n in page.toc)
    return ('<nav class="toc" aria-label="On this page">'
            '<p class="toc-head">On this page</p><ul>%s</ul></nav>' % items)


def crumbs_html(page, pages):
    """The visible counterpart of the BreadcrumbList already in the JSON-LD.

    Marked search-skip so "Documentation" does not end up in every page's
    indexed lead section, where it would match the word on all fifteen of them.
    """
    docs = next(p for p in pages if p.slug == 'index')
    bits = ['<nav class="crumbs search-skip" aria-label="Breadcrumb">',
            '<a href="%s">Documentation</a>' % page.rel(docs.url)]
    if page.slug != 'index':
        bits.append('<span class="sep" aria-hidden="true">/</span>')
        bits.append('<span aria-current="page">%s</span>'
                    % html.escape(page.nav_title))
    return ''.join(bits) + '</nav>'


def prev_next_html(page, pages):
    i = ORDER.index(page.slug)
    by_slug = {p.slug: p for p in pages}
    bits = []
    if i > 0:
        p = by_slug[ORDER[i - 1]]
        bits.append('<a class="pn prev" href="%s"><span>Previous</span>%s</a>'
                    % (page.rel(p.url), html.escape(p.nav_title)))
    if i < len(ORDER) - 1:
        n = by_slug[ORDER[i + 1]]
        bits.append('<a class="pn next" href="%s"><span>Next</span>%s</a>'
                    % (page.rel(n.url), html.escape(n.nav_title)))
    return '<nav class="prevnext">%s</nav>' % ''.join(bits) if bits else ''


def head_html(page, kind='article'):
    """Title, description, canonical, Open Graph, Twitter card, JSON-LD."""
    canon = BASE_URL + '/' + page.url
    full_title = (page.title if page.slug == 'home'
                  else '%s - %s' % (page.title, SITE_NAME))
    ld = {
        '@context': 'https://schema.org',
        '@type': 'TechArticle' if kind == 'article' else 'SoftwareApplication',
        'name': page.title,
        'headline': page.title,
        'description': page.description,
        'url': canon,
        'inLanguage': 'en',
        'isPartOf': {'@type': 'WebSite', 'name': SITE_NAME, 'url': BASE_URL + '/'},
    }
    if kind != 'article':
        ld = {
            '@context': 'https://schema.org',
            '@type': 'SoftwareApplication',
            'name': SITE_NAME,
            'alternateName': 'Assetto Corsa to glTF converter',
            'description': page.description,
            'url': BASE_URL + '/',
            'applicationCategory': 'DeveloperApplication',
            'operatingSystem': 'Windows, macOS, Linux',
            'softwareVersion': version(),
            'license': 'https://opensource.org/licenses/MIT',
            'codeRepository': REPO,
            'programmingLanguage': 'Python',
            'offers': {'@type': 'Offer', 'price': '0',
                       'priceCurrency': 'USD'},
        }
    crumbs = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': SITE_NAME,
             'item': BASE_URL + '/'}]}
    if page.url:
        crumbs['itemListElement'].append(
            {'@type': 'ListItem', 'position': 2, 'name': 'Documentation',
             'item': BASE_URL + '/docs/'})
        if page.slug != 'index':
            crumbs['itemListElement'].append(
                {'@type': 'ListItem', 'position': 3, 'name': page.title,
                 'item': canon})

    j = lambda o: json.dumps(o, separators=(',', ':'))     # noqa: E731
    return '\n'.join([
        '<title>%s</title>' % html.escape(full_title),
        '<meta name="description" content="%s">' % html.escape(page.description),
        '<link rel="canonical" href="%s">' % canon,
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="%s">' % SITE_NAME,
        '<meta property="og:title" content="%s">' % html.escape(full_title),
        '<meta property="og:description" content="%s">' % html.escape(page.description),
        '<meta property="og:url" content="%s">' % canon,
        '<meta property="og:image" content="%s/assets/og.png">' % BASE_URL,
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="%s - %s">'
        % (SITE_NAME, TAGLINE),
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="twitter:title" content="%s">' % html.escape(full_title),
        '<meta name="twitter:description" content="%s">' % html.escape(page.description),
        '<meta name="twitter:image" content="%s/assets/og.png">' % BASE_URL,
        '<script type="application/ld+json">%s</script>' % j(ld),
        '<script type="application/ld+json">%s</script>' % j(crumbs),
    ])


def version():
    path = os.path.join(ROOT, 'src', 'acgltf', '__init__.py')
    with open(path, encoding='utf-8') as f:
        return re.search(r"__version__ = '([^']+)'", f.read()).group(1)


def write(out, url, text):
    path = os.path.join(out, url, 'index.html') if url else os.path.join(out, 'index.html')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def build(out, base_url):
    global BASE_URL
    BASE_URL = base_url.rstrip('/')

    pages = read_docs()
    home = Page('home', '%s - %s' % (SITE_NAME, TAGLINE),
                'Convert Assetto Corsa .kn5 cars and tracks to glTF 2.0 or GLB '
                'from the command line. Keeps the full node hierarchy, resolves '
                'liveries, and maps AC shader parameters onto PBR materials.',
                '', '', 'Home')

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    shell = template('page.html')
    rendered = {}

    # Pass 1: render, so every page's anchors exist before links are checked.
    for p in pages:
        raw = render_markdown(p)
        collector = AnchorCollector()
        collector.feed(raw)
        p.anchors = collector.ids
        rendered[p.slug] = raw

    # Pass 2: rewrite links against the anchors, and fail on anything unresolved.
    broken = []
    written = []
    for p in pages:
        body = rewrite_links(rendered[p.slug], p, pages, check=broken)
        page_html = shell.format(
            lang='en',
            head=head_html(p),
            root=p.rel(''),
            assets=p.rel('assets'),
            nav=nav_html(p, pages, p.slug),
            crumbs=crumbs_html(p, pages),
            toc=toc_html(p),
            body=body,
            prevnext=prev_next_html(p, pages),
            repo=REPO,
            edit=REPO + '/blob/main/docs/%s.md' % p.slug,
            year=date.today().year,
            version=version(),
            sitename=SITE_NAME,
        )
        written.append((p, write(out, p.url, page_html)))

    home_html = template('home.html').format(
        head=head_html(home, kind='home'),
        root='./', assets='assets', repo=REPO, year=date.today().year,
        version=version(), sitename=SITE_NAME,
    )
    written.insert(0, (home, write(out, '', home_html)))

    if broken:
        for slug, href in broken:
            print('  broken link in docs/%s.md -> %s' % (slug, href),
                  file=sys.stderr)
        sys.exit('%d broken internal link(s)' % len(broken))

    # Static files, the search index built from what was just written, and the
    # two files a crawler looks for.
    shutil.copytree(os.path.join(os.path.dirname(TPL), 'static'),
                    os.path.join(out, 'assets'))
    # Images that belong to the project rather than to the theme -- the social
    # card, screenshots -- live in assets/ at the top level so the README can
    # use them too, and are copied in beside the stylesheet.
    for name in sorted(os.listdir(os.path.join(ROOT, 'assets'))):
        src = os.path.join(ROOT, 'assets', name)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(out, 'assets', name))

    index = []
    for p, path in written:
        with open(path, encoding='utf-8') as f:
            s = Sectioniser()
            s.feed(f.read())
        p.sections = s.result()
        index.append({'u': p.url, 't': p.title, 'd': p.description,
                      's': p.sections})
    with open(os.path.join(out, 'search-index.json'), 'w', encoding='utf-8') as f:
        json.dump({'v': version(), 'pages': index}, f, separators=(',', ':'))

    today = date.today().isoformat()
    urls = '\n'.join(
        '  <url><loc>%s/%s</loc><lastmod>%s</lastmod>'
        '<changefreq>monthly</changefreq><priority>%s</priority></url>'
        % (BASE_URL, p.url, today, '1.0' if not p.url else
           ('0.9' if p.slug in ('index', 'installation', 'quick-start') else '0.8'))
        for p, _ in written)
    with open(os.path.join(out, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                '%s\n</urlset>\n' % urls)
    with open(os.path.join(out, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write('User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n' % BASE_URL)
    # GitHub Pages runs Jekyll unless told not to, and Jekyll drops files and
    # folders beginning with an underscore.
    open(os.path.join(out, '.nojekyll'), 'w').close()

    words = sum(len(sec['x'].split()) for p, _ in written for sec in p.sections)
    size = os.path.getsize(os.path.join(out, 'search-index.json'))
    print('pages  : %d' % len(written))
    print('index  : %d sections, %d words, %.0f KB'
          % (sum(len(p.sections) for p, _ in written), words, size / 1024))
    print('base   : %s' % BASE_URL)
    print('wrote  : %s' % out)


def main():
    ap = argparse.ArgumentParser(prog='build_site.py')
    ap.add_argument('--out', default=os.path.join(ROOT, 'site'))
    ap.add_argument('--base-url', default=BASE_URL,
                    help='canonical host for canonical links, Open Graph and '
                         'the sitemap. Internal links are relative and do not '
                         'depend on it.')
    a = ap.parse_args()
    build(a.out, a.base_url)


if __name__ == '__main__':
    sys.exit(main() or 0)

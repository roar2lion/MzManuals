"""Build the documentation site and PDFs from the JSON manuals.

    python builder/build.py                 validate + build site/ (published manuals only)
    python builder/build.py --drafts        also build manuals with "publish": false
    python builder/build.py --pdf           also print each manual to site/pdf/<id>.pdf
    python builder/build.py --check         validate only, write nothing
    python builder/build.py --new ID TITLE  scaffold content/manuals/ID.json

Everything a manual needs is in its JSON (see schema/manual.schema.json and the
authoring-guide manual). The output is deterministic: same JSON in, same files out.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
MANUALS = CONTENT / "manuals"
ASSETS = CONTENT / "assets"
SCHEMA = ROOT / "schema"
STATIC = Path(__file__).resolve().parent / "static"
SITE = ROOT / "site"

KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

LABEL_KIND = {"table": "Table", "figure": "Figure", "diagram": "Figure", "equation": "Eq."}
CALLOUT_TITLE = {"note": "Note", "important": "Important", "warning": "Warning",
                 "assumption": "Assumption", "limitation": "Limitation"}


def esc(s, quote=False):
    return html.escape(str(s), quote=quote)


def paras(v):
    return [v] if isinstance(v, str) else list(v)


def load_json(path, problems):
    try:
        with open(path, encoding="utf-8-sig") as f:      # tolerate a BOM from Windows editors
            return json.load(f)
    except json.JSONDecodeError as e:
        problems.append(f"{path.relative_to(ROOT)}: invalid JSON at line {e.lineno} col {e.colno}: {e.msg}")
        return None


def schema_check(doc, schema_name, where, problems):
    try:
        import jsonschema
    except ImportError:
        sys.exit("jsonschema is missing: run  pip install -r requirements.txt")
    with open(SCHEMA / schema_name, encoding="utf-8") as f:
        validator = jsonschema.Draft202012Validator(json.load(f))
    errors = sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path])
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "(root)"
        problems.append(f"{where} @ {path}: {e.message}")
    return not errors


# --------------------------------------------------------------------------- index

class Index:
    """Numbers of every section and labelled block of one manual, in document order."""

    def __init__(self, manual, problems):
        self.manual = manual
        self.id = manual["id"]
        self.title = manual["title"]
        self.sections = {}      # anchor -> (number, title)
        self.labels = {}        # block anchor -> "Table 2", "Eq. (3)", ...
        self.block_no = {}      # id(block) -> number within its kind
        self.toc = []           # (level, anchor, number, title)
        self._problems = problems
        counters = {"Table": 0, "Figure": 0, "Eq.": 0}
        self._walk(manual["sections"], "", 1, counters, numeric=True)
        self._walk(manual.get("appendices", []), "", 1, counters, numeric=False)

    def _claim(self, anchor, where):
        if anchor in self.sections or anchor in self.labels:
            self._problems.append(f"{self.id}: duplicate anchor '{anchor}' ({where})")

    def _walk(self, sections, prefix, level, counters, numeric):
        for i, s in enumerate(sections, 1):
            own = str(i) if numeric or level > 1 else chr(64 + i)
            num = f"{prefix}{own}"
            self._claim(s["id"], f"section {num}")
            self.sections[s["id"]] = (num, s["title"])
            self.toc.append((level, s["id"], num, s["title"]))
            for b in s.get("blocks", []):
                kind = LABEL_KIND.get(b["type"])
                if kind:
                    counters[kind] += 1
                    self.block_no[id(b)] = counters[kind]
                    if "id" in b:
                        self._claim(b["id"], f"{b['type']} in {num}")
                        n = counters[kind]
                        self.labels[b["id"]] = f"Eq. ({n})" if kind == "Eq." else f"{kind} {n}"
                for item in b.get("items", []) if b["type"] == "entries" else []:
                    if "id" in item:
                        self._claim(item["id"], f"entry in {num}")
                        self.labels[item["id"]] = item["title"]
            self._walk(s.get("sections", []), f"{num}.", level + 1, counters, numeric)


# --------------------------------------------------------------------------- inline

CODE2 = re.compile(r"`` ?(.+?) ?``")          # double backticks: code that itself contains `
INLINE_MATH = re.compile(r"\$`(.+?)`\$")
CODE = re.compile(r"`([^`]+)`")
TERM = re.compile(r"\[\[([a-z0-9-]+)(?:\|([^\]]+))?\]\]")
XREF = re.compile(r"\[@([a-z0-9-]*)(?:#([a-z][a-z0-9-]*))?(?:\|([^\]]+))?\]")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITAL = re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])")
MARKUP = re.compile(r"\$`|`\$|`|\*\*|\[\[|\]\]|\[@[^|\]]*\|?|\*")


def plain(text):
    """Text with the markup stripped, for tooltips and the search index."""
    text = TERM.sub(lambda m: m[2] or m[1], text)
    text = XREF.sub(lambda m: m[3] or "", text)
    text = LINK.sub(lambda m: m[1], text)
    return MARKUP.sub("", text)


class Ctx:
    """Rendering state for one page."""

    def __init__(self, build, manual_id, mode, where):
        self.build = build
        self.manual_id = manual_id    # None on the glossary/landing pages
        self.mode = mode              # "site" or "print"
        self.where = where
        self.used_terms = set()

    @property
    def root(self):
        return "../" if self.mode == "print" else ""

    def problem(self, msg):
        self.build.problems.append(f"{self.where}: {msg}")

    def href(self, mid, anchor):
        frag = f"#{anchor}" if anchor else ""
        if mid == self.manual_id:
            return frag or "#top"
        if self.mode == "print":
            return f"{self.build.base_url}{mid}.html{frag}"
        return f"{mid}.html{frag}"

    def term_href(self, tid):
        if self.mode == "print":
            return f"#gl-{tid}"
        return f"glossary.html#{tid}"


def inline(text, ctx):
    stash = []

    def keep(fragment):
        stash.append(fragment)
        return f"\x00{len(stash) - 1}\x00"

    text = CODE2.sub(lambda m: keep(f"<code>{esc(m[1])}</code>"), text)
    text = INLINE_MATH.sub(lambda m: keep(f'<span class="tex" data-tex="{esc(m[1], True)}"></span>'), text)
    text = CODE.sub(lambda m: keep(f"<code>{esc(m[1])}</code>"), text)
    text = esc(text)
    text = TERM.sub(lambda m: keep(_term(m[1], m[2], ctx)), text)
    text = XREF.sub(lambda m: keep(_xref(m[1], m[2], m[3], ctx)), text)
    text = LINK.sub(lambda m: keep(f'<a href="{m[2]}">{m[1]}</a>'), text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITAL.sub(r"<em>\1</em>", text)
    while "\x00" in text:
        text = re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m[1])], text)
    return text


def _term(tid, label, ctx):
    term = ctx.build.terms.get(tid)
    if term is None:
        ctx.problem(f"unknown glossary term [[{tid}]]")
        return label or tid
    ctx.used_terms.add(tid)
    if ctx.manual_id:
        ctx.build.term_usage.setdefault(tid, set()).add(ctx.manual_id)
    tip = esc(plain(" ".join(paras(term["definition"]))), True)
    return f'<a class="term" href="{ctx.term_href(tid)}" title="{tip}">{label or esc(term["term"])}</a>'


def _xref(mid, anchor, label, ctx):
    mid = mid or ctx.manual_id
    if mid is None:
        ctx.problem(f"cross-reference to '#{anchor}' needs a manual id outside a manual")
        return label or "??"
    idx = ctx.build.index.get(mid)
    if idx is None:
        ctx.problem(f"cross-reference to unknown manual '{mid}'")
        return label or "??"
    if mid not in ctx.build.selected:
        ctx.problem(f"cross-reference to manual '{mid}', which is not published in this build")
    if anchor is None:
        text = label or esc(idx.title)
    elif anchor in idx.sections:
        num, title = idx.sections[anchor]
        text = label or f"§{num} {esc(title)}"
    elif anchor in idx.labels:
        text = label or esc(idx.labels[anchor])
    else:
        ctx.problem(f"cross-reference to unknown anchor '{mid}#{anchor}'")
        return label or "??"
    if mid != ctx.manual_id and not label:
        text = f"{esc(idx.title)}, {text}" if anchor else text
    return f'<a class="xref" href="{ctx.href(mid, anchor)}">{text}</a>'


def rich(v, ctx, tag="p"):
    return "".join(f"<{tag}>{inline(p, ctx)}</{tag}>" for p in paras(v))


# --------------------------------------------------------------------------- blocks

def badges(applies):
    return "".join(f' <span class="badge badge-{m.lower()}">{m}</span>' for m in applies or [])


def render_list(items, ordered, ctx):
    tag = "ol" if ordered else "ul"
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(f"<li>{inline(it, ctx)}</li>")
        else:
            sub = render_list(it["items"], it.get("ordered", False), ctx) if it.get("items") else ""
            out.append(f"<li>{inline(it['text'], ctx)}{sub}</li>")
    return f"<{tag}>{''.join(out)}</{tag}>"


def render_block(b, ctx, idx):
    t = b["type"]
    aid = f' id="{b["id"]}"' if "id" in b else ""
    n = idx.block_no.get(id(b))

    if t == "text":
        return f"<div{aid}>{rich(b['text'], ctx)}</div>" if aid else rich(b["text"], ctx)

    if t == "list":
        return f"<div{aid}>{render_list(b['items'], b.get('ordered', False), ctx)}</div>"

    if t == "table":
        align = b.get("align", [])
        cls = lambda i: f' class="a-{align[i]}"' if i < len(align) else ""
        head = "".join(f"<th{cls(i)}>{inline(c, ctx)}</th>" for i, c in enumerate(b["columns"]))
        rows = []
        for r, row in enumerate(b["rows"]):
            if len(row) != len(b["columns"]):
                ctx.problem(f"table {n} row {r + 1} has {len(row)} cells, expected {len(b['columns'])}")
            cells = "".join(f"<td{cls(i)}>{'' if c is None else inline(str(c), ctx)}</td>" for i, c in enumerate(row))
            rows.append(f"<tr>{cells}</tr>")
        cap = f"<caption><span class=\"label\">Table {n}</span> {inline(b['caption'], ctx)}</caption>" if b.get("caption") else ""
        notes = f'<div class="table-notes">{rich(b["notes"], ctx)}</div>' if b.get("notes") else ""
        return (f'<div class="table-wrap"{aid}><table>{cap}<thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>{notes}</div>')

    if t == "entries":
        cards = []
        for item in b["items"]:
            iid = f' id="{item["id"]}"' if "id" in item else ""
            known = {"title", "id", "applies_to"} | {f["key"] for f in b["fields"]}
            for extra in set(item) - known:
                ctx.problem(f"entry '{item['title']}' has field '{extra}' not listed in the block's fields")
            rows = []
            for f in b["fields"]:
                if f["key"] in item:
                    val = item[f["key"]]
                    body = inline(val, ctx) if isinstance(val, str) else render_list(val, False, ctx)
                    rows.append(f'<dt>{esc(f["label"])}</dt><dd>{body}</dd>')
            cards.append(f'<div class="entry"{iid}><h4>{inline(item["title"], ctx)}{badges(item.get("applies_to"))}</h4>'
                         f'<dl>{"".join(rows)}</dl></div>')
        return f'<div class="entries"{aid}>{"".join(cards)}</div>'

    if t == "equation":
        where = ""
        if b.get("where"):
            rows = "".join(
                f'<tr><td><span class="tex" data-tex="{esc(w["symbol"], True)}"></span></td>'
                f'<td>{inline(w["meaning"], ctx)}</td><td>{esc(w.get("unit", ""))}</td></tr>'
                for w in b["where"])
            where = f'<table class="where"><caption>where</caption><tbody>{rows}</tbody></table>'
        cap = f'<div class="eq-caption">{inline(b["caption"], ctx)}</div>' if b.get("caption") else ""
        return (f'<div class="equation"{aid}>{cap}<div class="eq-row"><div class="tex display" data-tex="{esc(b["tex"], True)}"></div>'
                f'<span class="eqno">({n})</span></div>{where}</div>')

    if t == "callout":
        title = b.get("title") or CALLOUT_TITLE[b["kind"]]
        return (f'<aside class="callout callout-{b["kind"]}"{aid}><div class="callout-title">{inline(title, ctx)}</div>'
                f'{rich(b["text"], ctx)}</aside>')

    if t == "figure":
        if not (ASSETS / b["src"]).is_file():
            ctx.problem(f"figure file content/assets/{b['src']} not found")
        ctx.build.assets_used.add(b["src"])
        style = f' style="width:{b["width"]}"' if b.get("width") else ""
        cap = f'<figcaption><span class="label">Figure {n}</span> {inline(b["caption"], ctx)}</figcaption>' if b.get("caption") else ""
        return f'<figure{aid}><img src="{ctx.root}assets/{esc(b["src"], True)}" alt="{esc(b["alt"], True)}"{style}>{cap}</figure>'

    if t == "diagram":
        ctx.build.needs_mermaid.add(idx.id)
        src = "\n".join(paras(b["mermaid"]))
        cap = f'<figcaption><span class="label">Figure {n}</span> {inline(b["caption"], ctx)}</figcaption>' if b.get("caption") else ""
        return f'<figure class="diagram"{aid}><pre class="mermaid">{esc(src)}</pre>{cap}</figure>'

    if t == "code":
        lang = f' data-lang="{esc(b["lang"], True)}"' if b.get("lang") else ""
        return f'<pre class="code"{aid}{lang}><code>{esc(chr(10).join(paras(b["text"])))}</code></pre>'

    raise ValueError(t)


def render_section(s, ctx, idx, level):
    num, _ = idx.sections[s["id"]]
    h = min(level + 1, 6)
    out = [f'<section id="{s["id"]}" class="level{level}">',
           f'<h{h}><span class="secno">{num}</span> {inline(s["title"], ctx)}{badges(s.get("applies_to"))}'
           f'<a class="anchor" href="#{s["id"]}" aria-label="Link to this section">#</a></h{h}>']
    if s.get("summary"):
        out.append(f'<div class="summary">{rich(s["summary"], ctx)}</div>')
    out.extend(render_block(b, ctx, idx) for b in s.get("blocks", []))
    out.extend(render_section(c, ctx, idx, level + 1) for c in s.get("sections", []))
    if s.get("sources"):                     # after subsections: a parent's sources cover them all
        srcs = ", ".join(f"<code>{esc(x)}</code>" for x in s["sources"])
        out.append(f'<p class="sources">Sources: {srcs}</p>')
    out.append("</section>")
    return "\n".join(out)


def search_text(node):
    """All prose of a section's own blocks (not its subsections), markup stripped."""
    parts = []

    def grab(v):
        if isinstance(v, str):
            parts.append(plain(v))
        elif isinstance(v, list):
            for x in v:
                grab(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in ("type", "id", "src", "tex", "kind", "lang", "mermaid", "align", "applies_to", "key"):
                    grab(x)

    grab(node.get("summary", ""))
    grab(node.get("blocks", []))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:4000]


# --------------------------------------------------------------------------- pages

def toc_html(idx, depth):
    out, prev = [], 0
    for level, anchor, num, title in idx.toc:
        if level > depth:
            continue
        if level > prev:
            out.append("<ul>" * (level - prev))
        elif level < prev:
            out.append("</li></ul>" * (prev - level) + "</li>")
        else:
            out.append("</li>")
        out.append(f'<li><a href="#{anchor}"><span class="secno">{num}</span> {esc(title)}</a>')
        prev = level
    out.append("</li></ul>" * prev)
    return "".join(out)


def head(title, root, math=True, mermaid=False, extra_css=()):
    css = [f'<link rel="stylesheet" href="{root}static/site.css">']
    css += [f'<link rel="stylesheet" href="{root}static/{c}">' for c in extra_css]
    js = [f'<script defer src="{root}static/site.js"></script>']
    if math:
        css.insert(0, f'<link rel="stylesheet" href="{KATEX}/katex.min.css">')
        js.insert(0, f'<script defer src="{KATEX}/katex.min.js"></script>')
    if mermaid:
        js.insert(0, f'<script defer src="{MERMAID}"></script>')
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{esc(title)}</title>\n" + "\n".join(css + js) + "\n</head>\n")


def topbar(site, current):
    nav = [("index.html", "Manuals", "home"), ("glossary.html", "Glossary", "glossary")]
    links = "".join(f'<a href="{h}"{" aria-current=\"page\"" if k == current else ""}>{t}</a>' for h, t, k in nav)
    return (f'<header class="topbar"><a class="brand" href="index.html">{esc(site["title"])}</a>'
            f'<nav>{links}</nav><div class="search"><input type="search" id="search" placeholder="Search manuals"'
            f' aria-label="Search manuals" autocomplete="off"><div id="search-results" hidden></div></div>'
            f'<button id="theme" type="button" aria-label="Toggle dark mode">◐</button></header>')


def meta_line(m):
    bits = [f'<span class="status status-{m["status"]}">{m["status"]}</span>',
            f"v{esc(m['version'])}", f"updated {esc(m['updated'])}"]
    if m.get("authors"):
        bits.append(esc(", ".join(m["authors"])))
    return f'<p class="meta">{" · ".join(bits)}{badges(m.get("applies_to"))}</p>'


def glossary_appendix(ctx):
    if not ctx.used_terms:
        return ""
    defs, seen = {}, set()
    while ctx.used_terms - seen:             # definitions can use further terms; include those too
        for tid in sorted(ctx.used_terms - seen):
            seen.add(tid)
            defs[tid] = rich(ctx.build.terms[tid]["definition"], ctx)
    rows = []
    for t in sorted((ctx.build.terms[t] for t in defs), key=lambda t: t["term"].lower()):
        exp = f' <span class="expansion">({esc(t["expansion"])})</span>' if t.get("expansion") else ""
        rows.append(f'<dt id="gl-{t["id"]}">{esc(t["term"])}{exp}</dt><dd>{defs[t["id"]]}</dd>')
    return f'<section class="appendix-glossary"><h2>Terms used</h2><dl class="glossary">{"".join(rows)}</dl></section>'


def changelog_html(m):
    if not m.get("changelog"):
        return ""
    rows = "".join(f'<tr><td>{esc(c["version"])}</td><td>{esc(c["date"])}</td>'
                   f'<td><ul>{"".join(f"<li>{esc(x)}</li>" for x in c["changes"])}</ul></td></tr>'
                   for c in m["changelog"])
    return (f'<section class="changelog"><h2>Version history</h2><div class="table-wrap"><table>'
            f'<thead><tr><th>Version</th><th>Date</th><th>Changes</th></tr></thead><tbody>{rows}</tbody></table></div></section>')


def manual_body(m, ctx, idx):
    body = [render_section(s, ctx, idx, 1) for s in m["sections"]]
    if m.get("appendices"):
        body.append('<div class="appendices"><h2 class="part">Appendices</h2>')
        body += [render_section(s, ctx, idx, 1) for s in m["appendices"]]
        body.append("</div>")
    return "\n".join(body)


def manual_page(m, build):
    idx = build.index[m["id"]]
    ctx = Ctx(build, m["id"], "site", f"{m['id']}.json")
    body = manual_body(m, ctx, idx)
    pdf = f'<a class="button" href="pdf/{m["id"]}.pdf">Download PDF</a>' if build.pdf else ""
    draft = '<div class="draft-banner">Draft: not yet reviewed</div>' if m["status"] == "draft" else ""
    sub = f'<p class="subtitle">{esc(m["subtitle"])}</p>' if m.get("subtitle") else ""
    page = (head(f"{m['title']} | {build.site['title']}", "", mermaid=m["id"] in build.needs_mermaid)
            + f'<body data-manual="{m["id"]}">\n{topbar(build.site, m["id"])}\n<div class="layout">'
            f'<aside class="sidebar"><nav class="toc" aria-label="Contents"><div class="toc-title">Contents</div>'
            f'{toc_html(idx, m.get("toc_depth", 3))}</nav></aside>'
            f'<main id="top">{draft}<header class="doc-head"><h1>{esc(m["title"])}</h1>{sub}{meta_line(m)}{pdf}</header>'
            f'{body}{glossary_appendix(ctx)}{changelog_html(m)}</main></div>\n{footer(build.site)}</body>\n</html>\n')
    return page, ctx


def print_page(m, build):
    idx = build.index[m["id"]]
    ctx = Ctx(build, m["id"], "print", f"{m['id']}.json (print)")
    body = manual_body(m, ctx, idx)
    site = build.site
    sub = f'<p class="subtitle">{esc(m["subtitle"])}</p>' if m.get("subtitle") else ""
    org = f'<p class="org">{esc(site["organisation"])}</p>' if site.get("organisation") else ""
    authors = f'<p>{esc(", ".join(m["authors"]))}</p>' if m.get("authors") else ""
    draft = '<p class="cover-draft">DRAFT</p>' if m["status"] == "draft" else ""
    return (head(m["title"], "../", mermaid=m["id"] in build.needs_mermaid, extra_css=("print.css",))
            + f'<body class="print" data-manual="{m["id"]}">'
            f'<div class="cover"><p class="cover-site">{esc(site["title"])}</p><h1>{esc(m["title"])}</h1>{sub}{draft}'
            f'<p class="cover-meta">Version {esc(m["version"])} · {esc(m["updated"])} · {esc(m["status"])}</p>{authors}{org}</div>'
            f'<nav class="toc print-toc"><h2>Contents</h2>{toc_html(idx, m.get("toc_depth", 3))}</nav>'
            f'<main>{body}{glossary_appendix(ctx)}{changelog_html(m)}</main></body>\n</html>\n')


def footer(site):
    bits = [esc(site["organisation"])] if site.get("organisation") else []
    if site.get("repo_url"):
        bits.append(f'<a href="{esc(site["repo_url"], True)}">Source</a>')
    return f'<footer class="footer">{" · ".join(bits)}</footer>' if bits else ""


def index_page(build):
    site = build.site
    ctx = Ctx(build, None, "site", "site.json")
    cards = []
    for m in build.ordered:
        sub = f'<p class="subtitle">{esc(m["subtitle"])}</p>' if m.get("subtitle") else ""
        desc = f'<p>{inline(m["description"], ctx)}</p>' if m.get("description") else ""
        pdf = f' · <a href="pdf/{m["id"]}.pdf">PDF</a>' if build.pdf else ""
        cards.append(f'<article class="card"><h2><a href="{m["id"]}.html">{esc(m["title"])}</a></h2>{sub}'
                     f'{desc}{meta_line(m)}<p class="card-links"><a href="{m["id"]}.html">Read online</a>{pdf}</p></article>')
    if not cards:
        cards.append('<p class="empty">No manuals published yet.</p>')
    intro = rich(site["intro"], ctx) if site.get("intro") else ""
    tagline = f'<p class="subtitle">{esc(site["tagline"])}</p>' if site.get("tagline") else ""
    return (head(site["title"], "", math=False) + f"<body>\n{topbar(site, 'home')}\n<main class=\"home\">"
            f'<header class="doc-head"><h1>{esc(site["title"])}</h1>{tagline}</header>{intro}'
            f'<div class="cards">{"".join(cards)}</div></main>\n{footer(site)}</body>\n</html>\n')


def glossary_page(build):
    ctx = Ctx(build, None, "site", "glossary.json")
    items = []
    for t in sorted(build.terms.values(), key=lambda t: t["term"].lower()):
        exp = f' <span class="expansion">({esc(t["expansion"])})</span>' if t.get("expansion") else ""
        aliases = f'<p class="aliases">Also: {esc(", ".join(t["aliases"]))}</p>' if t.get("aliases") else ""
        see = ""
        if t.get("see_also"):
            links = []
            for s in t["see_also"]:
                if s in build.terms:
                    links.append(f'<a href="#{s}">{esc(build.terms[s]["term"])}</a>')
                else:
                    ctx.problem(f"term '{t['id']}' see_also refers to unknown term '{s}'")
            see = f'<p class="see-also">See also: {", ".join(links)}</p>'
        used = sorted(build.term_usage.get(t["id"], ()), key=lambda i: build.order_of[i])
        used_links = ", ".join(f'<a href="{u}.html">{esc(build.index[u].title)}</a>' for u in used)
        used_html = f'<p class="used-in">Used in: {used_links}</p>' if used else ""
        items.append(f'<dt id="{t["id"]}">{esc(t["term"])}{exp}{badges(t.get("applies_to"))}</dt>'
                     f'<dd>{rich(t["definition"], ctx)}{aliases}{see}{used_html}</dd>')
    return (head(f"Glossary | {build.site['title']}", "", math=True) + f"<body>\n{topbar(build.site, 'glossary')}\n"
            f'<main class="home"><header class="doc-head"><h1>Glossary</h1>'
            f'<p class="subtitle">Terms shared by all manuals.</p></header><dl class="glossary">{"".join(items)}</dl></main>\n'
            f"{footer(build.site)}</body>\n</html>\n")


# --------------------------------------------------------------------------- pdf

def find_browser():
    names = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge")
    cands = [os.environ.get("CHROME_PATH")] + [shutil.which(n) for n in names] + [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    return next((c for c in cands if c and Path(c).is_file()), None)


def print_pdf(browser, html_path, pdf_path):
    with tempfile.TemporaryDirectory() as profile:
        args = [browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=20000", f"--print-to-pdf={pdf_path}", html_path.as_uri()]
        if sys.platform.startswith("linux"):
            args.insert(1, "--no-sandbox")
        subprocess.run(args, check=True, capture_output=True, timeout=300)
    if not pdf_path.is_file():
        raise RuntimeError(f"browser produced no PDF for {html_path.name}")


# --------------------------------------------------------------------------- build

def clear_dir(path):
    """Empty a folder. OneDrive can hold a lock on a folder for a moment, so retry, then
    fall back to deleting what can be deleted (a leftover empty folder is harmless)."""
    for _ in range(5):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            time.sleep(0.5)
    for p in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            p.unlink() if p.is_file() else p.rmdir()
        except OSError:
            pass


class Build:
    def __init__(self, drafts, pdf):
        self.problems = []
        self.pdf = pdf
        self.terms = {}
        self.term_usage = {}
        self.assets_used = set()
        self.needs_mermaid = set()
        self.index = {}
        self.selected = set()

        site_doc = load_json(CONTENT / "site.json", self.problems)
        if site_doc is not None:
            schema_check(site_doc, "site.schema.json", "site.json", self.problems)
        self.site = site_doc or {"title": "Documentation"}
        base = self.site.get("base_url", "")
        self.base_url = base if not base or base.endswith("/") else base + "/"

        gl = load_json(CONTENT / "glossary.json", self.problems)
        if gl is not None and schema_check(gl, "glossary.schema.json", "glossary.json", self.problems):
            for t in gl["terms"]:
                if t["id"] in self.terms:
                    self.problems.append(f"glossary.json: duplicate term id '{t['id']}'")
                self.terms[t["id"]] = t

        manuals = []
        for path in sorted(MANUALS.glob("*.json")):
            doc = load_json(path, self.problems)
            where = f"manuals/{path.name}"
            if doc is None or not schema_check(doc, "manual.schema.json", where, self.problems):
                continue
            if doc["id"] != path.stem:
                self.problems.append(f"{where}: id '{doc['id']}' must equal the file name '{path.stem}'")
                continue
            manuals.append(doc)
            self.index[doc["id"]] = Index(doc, self.problems)
        manuals.sort(key=lambda m: (m.get("order", 1000), m["id"]))
        self.ordered = [m for m in manuals if drafts or m.get("publish", True)]
        self.selected = {m["id"] for m in self.ordered}
        self.order_of = {m["id"]: i for i, m in enumerate(manuals)}

    def render(self):
        """All pages as {relative path: html}; problems are collected, nothing is written."""
        pages, self.prints = {}, {}
        for m in self.ordered:
            pages[f"{m['id']}.html"], _ = manual_page(m, self)
            if self.pdf:
                self.prints[m["id"]] = print_page(m, self)
        pages["index.html"] = index_page(self)
        pages["glossary.html"] = glossary_page(self)   # after the manuals, so "Used in" is complete
        return pages

    def search_index(self):
        entries = []
        for m in self.ordered:
            idx = self.index[m["id"]]

            def walk(sections):
                for s in sections:
                    num, title = idx.sections[s["id"]]
                    entries.append({"u": f"{m['id']}.html#{s['id']}", "m": m["title"], "n": num,
                                    "t": title, "x": search_text(s)})
                    walk(s.get("sections", []))
            walk(m["sections"])
            walk(m.get("appendices", []))
        for t in sorted(self.terms.values(), key=lambda t: t["id"]):
            entries.append({"u": f"glossary.html#{t['id']}", "m": "Glossary", "n": "", "t": t["term"],
                            "x": plain(" ".join(paras(t["definition"])) + " " + " ".join(t.get("aliases", [])))})
        return "window.SEARCH_INDEX = " + json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + ";\n"

    def write(self, pages):
        clear_dir(SITE)
        (SITE / "static").mkdir(parents=True, exist_ok=True)
        for f in sorted(STATIC.iterdir()):
            shutil.copy2(f, SITE / "static" / f.name)
        for a in sorted(self.assets_used):
            dst = SITE / "assets" / a
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ASSETS / a, dst)
        for name, text in pages.items():
            (SITE / name).write_text(text, encoding="utf-8", newline="\n")
        (SITE / "static" / "search-index.js").write_text(self.search_index(), encoding="utf-8", newline="\n")
        (SITE / ".nojekyll").write_text("", encoding="utf-8")

    def write_pdfs(self):
        browser = find_browser()
        if browser is None:
            sys.exit("No Chrome/Edge/Chromium found for PDF printing (set CHROME_PATH).")
        tmp, out = SITE / "_print", SITE / "pdf"
        tmp.mkdir(exist_ok=True)
        out.mkdir(exist_ok=True)
        try:
            for mid, text in self.prints.items():
                page = tmp / f"{mid}.html"
                page.write_text(text, encoding="utf-8", newline="\n")
                print_pdf(browser, page, out / f"{mid}.pdf")
                print(f"  pdf/{mid}.pdf")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


NEW_MANUAL = {
    "$schema": "../../schema/manual.schema.json",
    "id": None, "title": None, "subtitle": "", "description": "",
    "version": "0.1", "status": "draft", "updated": None,
    "authors": [], "applies_to": ["PLEXOS", "PyPSA"], "publish": False, "order": 100,
    "sections": [{"id": "introduction", "title": "Introduction",
                  "blocks": [{"type": "text", "text": "Purpose and scope of this manual."}]}],
    "changelog": [],
}


def scaffold(mid, title):
    import datetime
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", mid):
        sys.exit("Manual id must be lower-case letters, digits and hyphens, e.g. methodology")
    path = MANUALS / f"{mid}.json"
    if path.exists():
        sys.exit(f"{path.relative_to(ROOT)} already exists")
    doc = dict(NEW_MANUAL, id=mid, title=title, updated=datetime.date.today().isoformat())
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Created {path.relative_to(ROOT)} (publish: false until it is ready)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafts", action="store_true", help='include manuals with "publish": false')
    ap.add_argument("--pdf", action="store_true", help="print each manual to site/pdf/")
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--new", nargs=2, metavar=("ID", "TITLE"), help="scaffold a new manual")
    args = ap.parse_args()

    if args.new:
        scaffold(*args.new)
        return

    build = Build(drafts=args.drafts, pdf=args.pdf and not args.check)
    pages = build.render()
    if build.problems:
        print(f"{len(build.problems)} problem(s):")
        for p in build.problems:
            print("  -", p)
        sys.exit(1)
    names = ", ".join(m["id"] for m in build.ordered) or "none"
    if args.check:
        print(f"OK: {len(build.index)} manual(s) valid, {len(build.terms)} glossary terms. Would publish: {names}")
        return
    build.write(pages)
    print(f"Built site/ with manuals: {names}")
    if build.pdf:
        build.write_pdfs()


if __name__ == "__main__":
    main()

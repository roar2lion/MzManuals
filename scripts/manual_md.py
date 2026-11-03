"""Shared by json_to_md.py and md_to_json.py: the Markdown form of a manual.

A manual's JSON (content/manuals/<id>.json) is written to md/<id>.md as readable
Markdown, edited there (by hand or with AI help), and read back into the JSON.
The round trip is exact: json -> md -> json gives the same data, and writing
the JSON back keeps the original text of every part that wasn't edited, so an
unedited round trip leaves the file byte for byte unchanged.

The Markdown form:

    <!-- manual-md 1 | source: content/manuals/<id>.json | sha256: ... -->
    ---
    title: "..."                    one line per top-level key, value as JSON
    ---
    # Section title {#section-id}   heading depth = nesting depth
    <!-- section {"sources": [...]} -->   keys that aren't prose
    > Summary paragraph.
    <!-- text -->                   each block starts with its type ...
    A paragraph.                    ... followed by its content as Markdown
    <!-- table {"id": "tab-x", "caption": "..."} -->
    | Column | Column |
    ...
    <!-- appendices -->             sections after this line are appendices

Block bodies: text and callout = paragraphs; list = Markdown list; table = pipe
table; entries = one "- **Title**" item per entry with "  - key: value" fields;
equation = ```math fence plus an optional Symbol | Meaning | Unit table;
figure = ![alt](path); diagram = ```mermaid fence; code = fenced code.
"""
import hashlib
import json
import re
from json.decoder import scanstring
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUALS = ROOT / "content" / "manuals"
MD_DIR = ROOT / "md"
ASSETS_FROM_MD = "../content/assets/"
FORMAT = "manual-md 1"

SECTION_ORDER = ["id", "title", "summary", "applies_to", "blocks", "sections", "sources"]
BLOCK_ORDER = {
    "text": ["type", "id", "text"],
    "list": ["type", "id", "ordered", "items"],
    "table": ["type", "id", "caption", "columns", "align", "rows", "notes"],
    "entries": ["type", "id", "fields", "items"],
    "equation": ["type", "id", "tex", "caption", "where"],
    "callout": ["type", "id", "kind", "title", "text"],
    "figure": ["type", "id", "src", "alt", "caption", "width"],
    "diagram": ["type", "id", "caption", "mermaid"],
    "code": ["type", "id", "lang", "text"],
}
ENTRY_META = ("id", "applies_to")          # entry keys kept in the item's comment, not as fields
ALIGN = {"left": ":---", "right": "---:", "center": ":---:"}

EDIT_NOTE = ("<!-- Edit the prose freely: headings, paragraphs, list items, table cells, entry values, "
             "and the text inside the JSON of a comment line (captions, notes). Keep the front matter, "
             "every comment line and the {#id} at the end of each heading: md_to_json uses them to rebuild "
             "the JSON. A new paragraph under a heading needs nothing extra; a new list, table or other "
             "block starts with a type comment line copied from a block of the same type. A new heading "
             "needs its own {#id} (lower case, digits, hyphens). Inline markup is the manual's own: "
             "[[term]] glossary, [@#anchor] cross-reference, $`tex`$ maths, **bold**. -->")


class FormatError(ValueError):
    pass


# ---------------------------------------------------------------- helpers
def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def same(a, b):
    """Deep equality that also tells True from 1 and keeps list order."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def ordered(d, order):
    out = {k: d[k] for k in order if k in d}
    out.update((k, v) for k, v in d.items() if k not in out)
    return out


def cjson(d):
    """JSON for inside an HTML comment: one line, and never a literal -->."""
    return json.dumps(d, ensure_ascii=False).replace("-->", "--\\u003e")


def comment(word, attrs=None):
    return f"<!-- {word} {cjson(attrs)} -->" if attrs else f"<!-- {word} -->"


def fence_for(lines):
    longest = max([len(m) for ln in lines for m in re.findall(r"`+", ln)] + [0])
    return "`" * max(3, longest + 1)


def paras_of(lines):
    """Blank-line separated paragraphs; wrapped lines are joined with a space."""
    out, cur = [], []
    for ln in lines + [""]:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            out.append(" ".join(cur))
            cur = []
    return out


def rich(paras, as_list):
    if as_list or len(paras) > 1:
        return paras
    return paras[0] if paras else ""


def esc_cell(v):
    return str(v).replace("|", "\\|")


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def is_table_line(line):
    return line.lstrip().startswith("|")


# ---------------------------------------------------------------- JSON -> MD
def to_md(manual, source_rel, sha):
    out = [f"<!-- {FORMAT} | source: {source_rel} | sha256: {sha} -->", EDIT_NOTE, "", "---"]
    for k, v in manual.items():
        if k not in ("sections", "appendices"):
            out.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    out += ["---", ""]
    for s in manual.get("sections", []):
        out += _section(s, 1)
    if "appendices" in manual:
        out += [comment("appendices"), ""]
        for s in manual["appendices"]:
            out += _section(s, 1)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def _section(s, depth):
    if depth > 6:
        raise FormatError(f"section {s['id']}: nested deeper than 6 levels")
    out = ["#" * depth + f" {s['title']} {{#{s['id']}}}"]
    extra = {k: v for k, v in s.items() if k not in ("id", "title", "summary", "blocks", "sections")}
    if isinstance(s.get("summary"), list):
        extra["_summary_list"] = True
    for k in ("blocks", "sections"):
        if k in s and not s[k]:
            extra[f"_{k}"] = True             # key present but empty
    if extra:
        out.append(comment("section", extra))
    out.append("")
    if "summary" in s:
        paras = s["summary"] if isinstance(s["summary"], list) else [s["summary"]]
        for i, p in enumerate(paras):
            if i:
                out.append(">")
            out.append(f"> {p}")
        out.append("")
    for b in s.get("blocks", []):
        out += _block(b) + [""]
    for sub in s.get("sections", []):
        out += _section(sub, depth + 1)
    return out


def _paras_body(v):
    paras = v if isinstance(v, list) else [v]
    out = []
    for i, p in enumerate(paras):
        if i:
            out.append("")
        out.append(p)
    return out


def _block(b):
    t = b.get("type")
    if t not in BLOCK_ORDER:
        return [comment("block", b)]           # unknown type: carried whole
    attrs = {k: v for k, v in b.items() if k != "type"}
    body = []
    if t in ("text", "callout"):
        v = attrs.pop("text")
        if isinstance(v, list):
            attrs["_list"] = True
        body = _paras_body(v)
    elif t == "list":
        body = _list_items(attrs.pop("items"), attrs.get("ordered", False), "")
    elif t == "table":
        cols, rows, align = attrs.pop("columns"), attrs.pop("rows"), attrs.pop("align", None)
        cells = [[r, c, v] for r, row in enumerate(rows) for c, v in enumerate(row) if not isinstance(v, str)]
        if cells:
            attrs["_cells"] = cells
        if align is not None and len(align) != len(cols):
            attrs["align"] = align               # can't be shown in the separator row
            align = None
        body = ["| " + " | ".join(esc_cell(c) for c in cols) + " |",
                "| " + " | ".join(ALIGN[a] for a in align) + " |" if align else
                "| " + " | ".join("---" for _ in cols) + " |"]
        body += ["| " + " | ".join("" if v is None else esc_cell(v) for v in row) + " |" for row in rows]
    elif t == "entries":
        for it in attrs.pop("items"):
            meta = {k: v for k, v in it.items() if k in ENTRY_META}
            line = f"- **{it['title']}**"
            body.append(line + (f" <!-- {cjson(meta)} -->" if meta else ""))
            for k, v in it.items():
                if k == "title" or k in ENTRY_META:
                    continue
                if isinstance(v, list):
                    body.append(f"  - {k}:")
                    body += [f"    - {x}" for x in v]
                else:
                    body.append(f"  - {k}: {v}")
    elif t == "equation":
        tex = attrs.pop("tex").split("\n")
        f = fence_for(tex)
        body = [f + "math", *tex, f]
        if "where" in attrs:
            where = attrs.pop("where")
            if not where:
                attrs["_where"] = True
            else:
                body += ["", "| Symbol | Meaning | Unit |", "| --- | --- | --- |"]
                body += [f"| {esc_cell(w['symbol'])} | {esc_cell(w['meaning'])} | {esc_cell(w.get('unit', ''))} |"
                         for w in where]
    elif t == "figure":
        src, alt = attrs.pop("src"), attrs.pop("alt")
        body = [f"![{alt}]({ASSETS_FROM_MD}{src})"]
    elif t in ("diagram", "code"):
        key = "mermaid" if t == "diagram" else "text"
        v = attrs.pop(key)
        if isinstance(v, list):
            attrs["_list"] = True
        lines = v if isinstance(v, list) else v.split("\n")
        info = "mermaid" if t == "diagram" else attrs.pop("lang", "")
        if t == "code" and "lang" not in b:
            attrs["_nolang"] = True
        f = fence_for(lines)
        body = [f + info, *lines, f]
    return [comment(t, attrs)] + body


def _list_items(items, is_ordered, indent):
    out = []
    for i, it in enumerate(items):
        marker = f"{i + 1}." if is_ordered else "-"
        if isinstance(it, str):
            out.append(f"{indent}{marker} {it}")
            continue
        extra = {k: v for k, v in it.items() if k not in ("text", "items")}
        if "items" not in it:
            extra["_obj"] = True
        out.append(f"{indent}{marker} {it['text']}" + (f" <!-- {cjson(extra)} -->" if extra else ""))
        if it.get("items"):
            out += _list_items(it["items"], it.get("ordered", False), indent + " " * (len(marker) + 1))
        elif "items" in it:
            out.append(f"{indent}  <!-- empty -->")
    return out


# ---------------------------------------------------------------- MD -> JSON
HEAD_RE = re.compile(r"^<!-- manual-md (\d+) \| source: (.+?) \| sha256: ([0-9a-f]+) -->$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*\{#([^}\s]+)\}\s*$")
MARKER_RE = re.compile(r"^<!--\s*([a-z]+)(?:\s+(\{.*\}))?\s*-->\s*$")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TRAIL_RE = re.compile(r"\s*<!--\s*(\{.*\})\s*-->\s*$")


def read_header(text):
    first = text.split("\n", 1)[0].strip()
    m = HEAD_RE.match(first)
    if not m:
        raise FormatError("first line is not a manual-md header (was the file made by json_to_md?)")
    return {"format": int(m.group(1)), "source": m.group(2), "sha": m.group(3)}


def set_header_sha(text, sha):
    first, rest = text.split("\n", 1)
    return re.sub(r"sha256: [0-9a-f]+", f"sha256: {sha}", first) + "\n" + rest


def from_md(text):
    """Return (manual, header) from the Markdown form."""
    header = read_header(text)
    lines = text.replace("\r\n", "\n").split("\n")
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        i += 1
    if i == len(lines):
        raise FormatError("front matter (--- ... ---) not found")
    manual, i = {}, i + 1
    while i < len(lines) and lines[i].strip() != "---":
        ln = lines[i]
        if ln.strip():
            k, sep, v = ln.partition(":")
            if not sep:
                raise FormatError(f"line {i + 1}: front matter line is not 'key: value'")
            try:
                manual[k.strip()] = json.loads(v.strip())
            except json.JSONDecodeError as e:
                raise FormatError(f"line {i + 1}: value of {k.strip()!r} is not valid JSON ({e.msg})")
        i += 1
    tokens = _tokens(lines, i + 1)
    sections, appendices, has_app = _build_tree(tokens)
    tail = [k for k in ("changelog",) if k in manual]
    out = {k: v for k, v in manual.items() if k not in tail}
    out["sections"] = sections
    if has_app:
        out["appendices"] = appendices
    for k in tail:
        out[k] = manual[k]
    return out, header


def _tokens(lines, start):
    """Split the body into ('heading', depth, title, id, line) / ('appendices',) / ('block', type, attrs, body, line)."""
    toks, cur, fence = [], None, None
    for n in range(start, len(lines)):
        ln = lines[n]
        if fence:
            cur[3].append(ln)
            m = FENCE_RE.match(ln.strip())
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = None
            continue
        h = HEADING_RE.match(ln)
        if h:
            toks.append(("heading", len(h.group(1)), h.group(2), h.group(3), n + 1))
            cur = None
            continue
        m = MARKER_RE.match(ln.strip()) if not ln.startswith(" ") else None
        if m and m.group(1) in BLOCK_ORDER or (m and m.group(1) in ("block", "section", "appendices")):
            word = m.group(1)
            try:
                attrs = json.loads(m.group(2)) if m.group(2) else {}
            except json.JSONDecodeError as e:
                raise FormatError(f"line {n + 1}: the JSON in this comment is invalid ({e.msg})")
            if word == "appendices":
                toks.append(("appendices", n + 1))
                cur = None
            elif word == "section":
                if not toks or toks[-1][0] != "heading" or len(toks[-1]) > 5:
                    raise FormatError(f"line {n + 1}: '<!-- section -->' must follow its heading directly")
                toks[-1] = toks[-1] + (attrs,)
                cur = None
            else:
                cur = ["block", word, attrs, [], n + 1]
                toks.append(cur)
            continue
        if re.match(r"^#{1,6}\s", ln):
            raise FormatError(f"line {n + 1}: heading without an id; end it with {{#some-id}}")
        if cur is not None and ln.strip() and _ends_block(cur, ln, n > 0 and not lines[n - 1].strip()):
            cur = None
        if cur is None:
            if not ln.strip():
                continue
            # prose without a block comment: a summary (> lines) or a new text block
            kind = "summary" if ln.lstrip().startswith(">") and toks and toks[-1][0] == "heading" else "text"
            cur = ["block", kind, {}, [], n + 1]
            toks.append(cur)
        cur[3].append(ln)
        m = FENCE_RE.match(ln.strip())
        if m:
            fence = m.group(1)
    return toks


def _ends_block(cur, ln, after_blank):
    """True if prose line ln can't belong to the open block cur (it then starts a new text block)."""
    kind, body = cur[1], cur[3]
    has = [x for x in body if x.strip()]
    if kind == "summary":
        return not ln.lstrip().startswith(">")
    if kind in ("text", "callout") or not has or not after_blank:
        return False
    if kind in ("list", "entries"):
        return not (ITEM_RE.match(ln) or ln[:1].isspace() or ln.strip() == "<!-- empty -->")
    if kind in ("table", "equation"):
        return not is_table_line(ln)
    if kind == "figure":
        return not ln.lstrip().startswith("![")
    return True                                   # code, diagram: their fence is already closed


def _build_tree(toks):
    top, app, has_app = [], [], False
    stack = []                                   # (depth, section)
    target = top
    for t in toks:
        if t[0] == "appendices":
            has_app, target, stack = True, app, []
            continue
        if t[0] == "heading":
            _, depth, title, sid, line = t[:5]
            attrs = dict(t[5]) if len(t) > 5 else {}
            s = {"id": sid, "title": title}
            s["_attrs"] = attrs
            s["_blocks_raw"] = []
            while stack and stack[-1][0] >= depth:
                stack.pop()
            (stack[-1][1].setdefault("_subs", []) if stack else target).append(s)
            stack.append((depth, s))
            continue
        _, word, attrs, body, line = t
        if not stack:
            raise FormatError(f"line {line}: content before the first heading")
        stack[-1][1]["_blocks_raw"].append((word, attrs, body, line))

    def finish(s):
        attrs = s.pop("_attrs")
        raw = s.pop("_blocks_raw")
        subs = s.pop("_subs", [])
        sec = {"id": s["id"], "title": s["title"]}
        blocks = []
        for word, battrs, body, line in raw:
            if word == "summary":
                sl = [ln.lstrip()[1:] if ln.lstrip().startswith(">") else ln for ln in body]
                sec["summary"] = rich(paras_of(sl), attrs.pop("_summary_list", False))
            else:
                blocks.append(_parse_block(word, dict(battrs), body, line))
        attrs.pop("_summary_list", None)
        if blocks or attrs.pop("_blocks", False):
            sec["blocks"] = blocks
        if subs or attrs.pop("_sections", False):
            sec["sections"] = [finish(x) for x in subs]
        sec.update(attrs)
        return ordered(sec, SECTION_ORDER)

    return [finish(s) for s in top], [finish(s) for s in app], has_app


def _strip_blank(body):
    while body and not body[-1].strip():
        body = body[:-1]
    while body and not body[0].strip():
        body = body[1:]
    return body


def _fenced(body, line):
    body = _strip_blank(body)
    if not body or not FENCE_RE.match(body[0].strip()):
        raise FormatError(f"line {line}: expected a ``` fence")
    f, info = FENCE_RE.match(body[0].strip()).groups()
    for j in range(1, len(body)):
        m = FENCE_RE.match(body[j].strip())
        if m and m.group(1)[0] == f[0] and len(m.group(1)) >= len(f) and not m.group(2).strip():
            return info.strip(), body[1:j], body[j + 1:]
    raise FormatError(f"line {line}: fence not closed")


def _parse_block(word, attrs, body, line):
    body = _strip_blank(body)
    try:
        if word == "block":
            return attrs
        b = {"type": word}
        if word in ("text", "callout"):
            b["text"] = rich(paras_of(body), attrs.pop("_list", False))
        elif word == "list":
            b["items"] = _parse_items(body, line)
        elif word == "table":
            rows = [split_row(ln) for ln in body if is_table_line(ln)]
            if len(rows) < 2:
                raise FormatError(f"line {line}: a table needs a header row and a separator row")
            cols, sep, data = rows[0], rows[1], rows[2:]
            b["columns"] = cols
            if any(":" in c for c in sep):
                b["align"] = ["center" if c.startswith(":") and c.endswith(":") else
                              "right" if c.endswith(":") else "left" for c in sep]
            for r, c, v in attrs.pop("_cells", []):
                data[r][c] = v
            b["rows"] = data
        elif word == "entries":
            b["items"] = _parse_entries(body, line)
        elif word == "equation":
            _, tex, rest = _fenced(body, line)
            b["tex"] = "\n".join(tex)
            trows = [split_row(ln) for ln in rest if is_table_line(ln)]
            if trows[2:]:
                b["where"] = []
                for r in trows[2:]:
                    w = {"symbol": r[0], "meaning": r[1] if len(r) > 1 else ""}
                    if len(r) > 2 and r[2]:
                        w["unit"] = r[2]
                    b["where"].append(w)
            elif attrs.pop("_where", False):
                b["where"] = []
        elif word == "figure":
            m = re.match(r"^!\[(.*)\]\((.*)\)\s*$", " ".join(ln.strip() for ln in body))
            if not m:
                raise FormatError(f"line {line}: a figure needs one ![alt](path) line")
            b["alt"], src = m.group(1), m.group(2)
            b["src"] = src[len(ASSETS_FROM_MD):] if src.startswith(ASSETS_FROM_MD) else src
        elif word in ("diagram", "code"):
            info, content, _ = _fenced(body, line)
            as_list = attrs.pop("_list", False)
            b["mermaid" if word == "diagram" else "text"] = content if as_list else "\n".join(content)
            if word == "code" and not attrs.pop("_nolang", False):
                b["lang"] = info
        else:
            raise FormatError(f"line {line}: unknown block type '{word}'")
    except (IndexError, KeyError) as e:
        raise FormatError(f"line {line}: can't read this {word} block ({e})")
    b.update(attrs)
    return ordered(b, BLOCK_ORDER[word])


def _parse_items(body, line):
    """Nested Markdown list -> list items (strings, or {text, items} objects)."""
    root = {"items": [], "indent": -1}
    stack = [root]
    last = None
    for ln in body:
        if not ln.strip():
            continue
        if ln.strip() == "<!-- empty -->":
            if last is not None:
                last["items"] = []
            continue
        m = ITEM_RE.match(ln)
        if not m:
            if last is None:
                raise FormatError(f"line {line}: text before the first list item")
            last["text"] += " " + ln.strip()
            continue
        ind, _, txt = len(m.group(1)), m.group(2), m.group(3)
        extra = {}
        t = TRAIL_RE.search(txt)
        if t:
            extra = json.loads(t.group(1))
            txt = txt[:t.start()]
        while stack[-1]["indent"] >= ind:
            stack.pop()
        node = {"text": txt.strip(), "extra": extra, "indent": ind}
        stack[-1].setdefault("items", []).append(node)
        stack.append(node)
        last = node

    def conv(n):
        extra = dict(n["extra"])
        if "items" not in n and not extra:
            return n["text"]
        obj = extra.pop("_obj", False)
        o = {"text": n["text"]}
        o.update(extra)
        if "items" in n or not obj:
            o["items"] = [conv(c) for c in n.get("items", [])]
        return ordered(o, ["text", "ordered", "items"])

    return [conv(n) for n in root["items"]]


def _parse_entries(body, line):
    items, cur, target = [], None, None
    for ln in body:
        if not ln.strip():
            continue
        m = re.match(r"^- \*\*(.*?)\*\*(.*)$", ln)
        if m:
            cur = {"title": m.group(1)}
            t = TRAIL_RE.search(m.group(2))
            if t:
                cur.update(json.loads(t.group(1)))
            items.append(cur)
            target = None
            continue
        if cur is None:
            raise FormatError(f"line {line}: entry text before the first '- **Title**' line")
        m = re.match(r"^\s{1,3}[-*+] ([A-Za-z0-9_]+):(?:\s(.*))?$", ln)
        if m and not ln.startswith("    "):
            key, val = m.group(1), (m.group(2) or "").strip()
            if val:
                cur[key] = val
                target = (cur, key, None)
            else:
                cur[key] = []
                target = (cur, key, "list")
            continue
        m = re.match(r"^\s{3,}[-*+] (.*)$", ln)
        if m and target and target[2] == "list":
            target[0][target[1]].append(m.group(1).strip())
            continue
        if target:                                # wrapped continuation line
            d, k, kind = target
            if kind == "list" and d[k]:
                d[k][-1] += " " + ln.strip()
            elif kind is None:
                d[k] += " " + ln.strip()
            continue
        raise FormatError(f"line {line}: can't read entry line: {ln.strip()[:60]}")
    for it in items:                              # "- key:" with nothing under it = empty text
        for k, v in list(it.items()):
            if v == [] and k not in ENTRY_META:
                it[k] = ""
    return items


# ---------------------------------------------------------------- JSON writer
class _Node:
    __slots__ = ("value", "start", "end", "kids")

    def __init__(self, value, start, end, kids=None):
        self.value, self.start, self.end, self.kids = value, start, end, kids


_WS = re.compile(r"[ \t\n\r]*")
_NUM = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _parse_spans(text, i=0):
    i = _WS.match(text, i).end()
    c = text[i]
    if c == "{":
        start, i, kids, vals = i, i + 1, {}, {}
        i = _WS.match(text, i).end()
        if text[i] == "}":
            return _Node({}, start, i + 1, {}), i + 1
        while True:
            i = _WS.match(text, i).end()
            key, i = scanstring(text, i + 1)
            i = _WS.match(text, i).end() + 1          # ':'
            node, i = _parse_spans(text, i)
            kids[key], vals[key] = node, node.value
            i = _WS.match(text, i).end()
            if text[i] == ",":
                i += 1
                continue
            return _Node(vals, start, i + 1, kids), i + 1
    if c == "[":
        start, i, kids = i, i + 1, []
        i = _WS.match(text, i).end()
        if text[i] == "]":
            return _Node([], start, i + 1, []), i + 1
        while True:
            node, i = _parse_spans(text, i)
            kids.append(node)
            i = _WS.match(text, i).end()
            if text[i] == ",":
                i += 1
                continue
            return _Node([k.value for k in kids], start, i + 1, kids), i + 1
    if c == '"':
        s, j = scanstring(text, i + 1)
        return _Node(s, i, j), j
    for word, val in (("true", True), ("false", False), ("null", None)):
        if text.startswith(word, i):
            return _Node(val, i, i + len(word)), i + len(word)
    m = _NUM.match(text, i)
    return _Node(json.loads(m.group()), i, m.end()), m.end()


def _scalar(v):
    return not isinstance(v, (dict, list))


def _flat_dict(v):
    return all(_scalar(y) or (isinstance(y, list) and all(map(_scalar, y))) for y in v.values())


class _Writer:
    """Write JSON, reusing the original text of every unchanged value."""
    WIDTH = 160

    def __init__(self, old_text):
        self.old = old_text
        self.root = _parse_spans(old_text)[0] if old_text else None

    def _reuse(self, node, ind):
        txt = self.old[node.start:node.end]
        if "\n" not in txt:
            return txt
        line_start = self.old.rfind("\n", 0, node.start) + 1
        old_ind = len(self.old[line_start:node.start]) - len(self.old[line_start:node.start].lstrip(" "))
        delta = 2 * ind - old_ind
        if delta == 0:
            return txt
        out = []
        for k, ln in enumerate(txt.split("\n")):
            if k == 0:
                out.append(ln)
            elif delta > 0:
                out.append(" " * delta + ln)
            else:
                cut = min(-delta, len(ln) - len(ln.lstrip(" ")))
                out.append(ln[cut:])
        return "\n".join(out)

    def dump(self, v, node, ind=0, key=None, col=0):
        if node is not None and same(v, node.value):
            return self._reuse(node, ind)
        sp = "  " * ind
        if _scalar(v):
            return json.dumps(v, ensure_ascii=False)
        inline = json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
        if isinstance(v, dict):
            if key in ("fields[]", "where[]", "changelog[]") and _flat_dict(v):
                return inline
            if not v:
                return "{}"
            kids = node.kids if node is not None and isinstance(node.kids, dict) else {}
            parts = []
            for k, x in v.items():
                kj = json.dumps(k, ensure_ascii=False)
                parts.append(f"{sp}  {kj}: " + self.dump(x, kids.get(k), ind + 1, k, len(sp) + 4 + len(kj)))
            return "{\n" + ",\n".join(parts) + f"\n{sp}}}"
        if key == "rows[]" and all(map(_scalar, v)):
            return inline
        if all(map(_scalar, v)) and col + len(inline) <= self.WIDTH:
            return inline
        if not v:
            return "[]"
        olds = node.kids if node is not None and isinstance(node.kids, list) else []
        used, parts = set(), []
        for idx, x in enumerate(v):
            match = next((j for j, o in enumerate(olds) if j not in used and same(x, o.value)), None)
            if match is None and isinstance(x, dict) and "id" in x:
                match = next((j for j, o in enumerate(olds) if j not in used and isinstance(o.value, dict)
                              and o.value.get("id") == x["id"]), None)
            if match is None and idx < len(olds) and idx not in used and type(olds[idx].value) is type(x):
                match = idx
            if match is not None:
                used.add(match)
            parts.append(f"{sp}  " + self.dump(x, olds[match] if match is not None else None, ind + 1,
                                               (key or "") + "[]", len(sp) + 2))
        return "[\n" + ",\n".join(parts) + f"\n{sp}]"


def write_json_text(manual, old_text=""):
    nl = "\r\n" if "\r\n" in old_text else "\n"
    old = old_text.replace("\r\n", "\n")
    w = _Writer(old)
    out = w.dump(manual, w.root)
    return (out + "\n").replace("\n", nl)

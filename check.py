#!/usr/bin/env python3
"""check.py — catch drift from gramof design. Python 3.8+, no dependencies.

    ./check.py                  every site in sites.txt, plus every mark
    ./check.py ../novaos        one site   (from a site repo: ../gramofdesign/check.py .)
    ./check.py --sync [site…]   copy this repo over each vendored gramofdesign/, then check
    ./check.py --sync-only dir  only refresh a vendored copy (products: they are not checked)
    ./check.py --rules          list the rule ids a site can own in .gramof.json

Exit status 1 when anything fails. The rules are written down in README.md;
this file only enforces them.

A site may own a deliberate drift by listing the rule id and its reason in
.gramof.json at its root:

    { "owns": { "motion": "storytelling animations run 350–1100 ms" } }

Owned rules are reported, not checked. Everything else is the law.
"""
import json, re, shutil, struct, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

GD = Path(__file__).resolve().parent

# ── What a site can own (id → what the check enforces) ──────────────────────
RULES = {
    "fonts":         "the family fonts, from the canonical Google link or gramofdesign/fonts/",
    "weights":       "font-weight only through --weight-* tokens (400/500/600)",
    "type-scale":    "font-size only through tokens or relative units, never px/rem literals",
    "motion":        "transition/animation durations only through tokens",
    "colour":        "no literal colours (hex, rgb, hsl) outside token definitions",
    "element-rules": "no bare or #id-scoped rules on button/input/select/textarea",
    "viewport-zoom": "never block zoom (user-scalable=no, maximum-scale=1)",
    "cdn":           "third-party scripts pinned to an exact version",
    "meta":          "title is the product name; description and Open Graph present",
}

# Deliberate mark exceptions. Anything not listed here follows the plain rule.
GLYPH_EXTRA = {"novaos": {"#f9a8d4"}}                  # the pink moon
WHITE = {"#fff", "#ffffff"}

GOOGLE_FONTS = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600"
                "&family=JetBrains+Mono:wght@400;500&family=Outfit:wght@400;500;600&display=swap")
SELF_FONTS = "gramofdesign/fonts/fonts.css"

HEAD = ['<link rel="icon" href="favicon.ico" sizes="32x32">',
        '<link rel="icon" href="favicon.svg" type="image/svg+xml">',
        '<link rel="apple-touch-icon" href="apple-touch-icon.png">']
MANIFEST = '<link rel="manifest" href="site.webmanifest">'
ICON_REL = re.compile(r'<link\b[^>]*\brel="(?:shortcut icon|icon|apple-touch-icon|apple-touch-icon-precomposed|mask-icon|manifest)"[^>]*>', re.I)
FORBIDDEN_TAGS = {"linearGradient", "radialGradient", "filter", "image", "metadata",
                  "foreignObject", "style", "script", "mask", "pattern"}
SHARED = r"\.(?:btn|segmented|site-tools|switch|check|acc|tag|kofi-panel)\b"
SKIP_DIRS = {"node_modules", "gramofdesign", ".git", "_to_delete", "tests", "test"}

fails = 0
def bad(where, msg):
    global fails
    fails += 1
    print(f"  ✗ {where}: {msg}")

def note(msg):
    print(f"  · {msg}")

def registered():
    return [(GD / l.strip()) for l in (GD / "sites.txt").read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]

def product(site):
    html = site / "index.html"
    m = re.search(r'<html[^>]*\bdata-accent="([\w-]+)"', html.read_text()) if html.exists() else None
    return m.group(1) if m else None

def accents():
    css = (GD / "gramof.css").read_text()
    out = {}
    for name, hexv in re.findall(r":root\[data-accent='([\w-]+)'\]\s*\{\s*--accent:\s*(#[0-9a-fA-F]{3,6})", css):
        out.setdefault(name, hexv.lower())        # first match per product is the light value
    return out

# ── Marks ───────────────────────────────────────────────────────────────────
def check_mark(name, acc):
    p = GD / "marks" / f"{name}.svg"
    where = f"marks/{name}.svg"
    if not p.exists():
        return bad(where, "missing")
    raw = p.read_text()
    if re.search(r"c2pa|<metadata|<\?xml|<!DOCTYPE|data:", raw, re.I):
        bad(where, "metadata, prolog or embedded data — marks are bare SVG")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return bad(where, f"not valid XML ({e})")
    ns = "{http://www.w3.org/2000/svg}"
    tag = lambda e: e.tag.replace(ns, "")
    if root.get("viewBox") != "0 0 32 32":
        bad(where, "viewBox must be 0 0 32 32")
    if root.get("width") or root.get("height"):
        bad(where, "no width/height on <svg>; viewBox only")
    kids = list(root)
    if not kids or tag(kids[0]) != "title" or not (kids[0].text or "").startswith(name):
        bad(where, f"first child must be <title>{name}…</title>")
    sq = kids[1] if len(kids) > 1 else None
    if sq is None or tag(sq) != "rect" or sq.get("width") != "32" or sq.get("height") != "32" \
            or sq.get("rx") != "8" or sq.get("x") not in (None, "0") or sq.get("y") not in (None, "0"):
        bad(where, 'second child must be the squircle: <rect width="32" height="32" rx="8" fill="…">')
    else:
        fill = (sq.get("fill") or "").lower()
        want = acc.get(name)
        if want is None:
            bad(where, f"no accent token for '{name}' in gramof.css")
        elif fill != want:
            bad(where, f"squircle fill {fill or '(none)'} must be the light --accent {want}")
        if sq.get("opacity") or sq.get("stroke"):
            bad(where, "squircle takes no opacity or stroke")
    allowed = WHITE | GLYPH_EXTRA.get(name, set())
    for el in root.iter():
        t = tag(el)
        if t in FORBIDDEN_TAGS:
            bad(where, f"<{t}> not allowed in a mark (flat colour, no raster, no effects)")
        for a in ("fill", "stroke", "stop-color", "color"):
            v = (el.get(a) or "").lower()
            if not v or v == "none" or el is sq:
                continue
            if v.startswith("url(") or v == "currentcolor":
                bad(where, f"{a}={v}: marks use literal colours")
            elif v not in allowed:
                bad(where, f"{a}={v}: glyph colours allowed here are {sorted(allowed)}")
        for a in ("href", "{http://www.w3.org/1999/xlink}href"):
            if el.get(a):
                bad(where, f"<{t}> references {el.get(a)}; marks are self-contained")
    for sw in re.findall(r'stroke-width="([\d.]+)"', raw):
        if not 1.5 <= float(sw) <= 2:
            bad(where, f"stroke-width {sw} outside 1.5–2")

# ── Binary icon helpers ─────────────────────────────────────────────────────
def png_info(p):
    b = p.read_bytes()
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i, info = 8, {"chunks": []}
    while i < len(b):
        n, = struct.unpack(">I", b[i:i + 4]); t = b[i + 4:i + 8].decode("latin1")
        data = b[i + 8:i + 8 + n]; info["chunks"].append(t)
        if t == "IHDR":
            info["w"], info["h"], _, info["ct"] = struct.unpack(">IIBB", data[:10])
        if t in ("tEXt", "iTXt", "zTXt") and re.search(rb"c2pa|xmp", data, re.I):
            info["chunks"].append("meta")
        i += 12 + n
    return info

# ── CSS reading ─────────────────────────────────────────────────────────────
def site_css(site):
    """(label, css text) for every site stylesheet and inline <style> block."""
    out = []
    for f in sorted(site.rglob("*.css")):
        rel = f.relative_to(site)
        if not SKIP_DIRS.intersection(rel.parts):
            out.append((str(rel), f.read_text(errors="replace")))
    for page in sorted(site.glob("*.html")):
        for k, block in enumerate(re.findall(r"<style[^>]*>(.*?)</style>", page.read_text(), re.S)):
            out.append((f"{page.name} <style>", block))
    return out

def declarations(css):
    """Yield (selector, property, value, line) for every declaration."""
    css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), css, flags=re.S)
    stack, buf, line, start = [], "", 1, 1
    for ch in css:
        if ch == "{":
            stack.append(buf.strip()); buf = ""
        elif ch == "}":
            if buf.strip():
                yield from _decls(stack[-1] if stack else "", buf, start)
            if stack: stack.pop()
            buf = ""
        elif ch == ";" and stack:
            yield from _decls(stack[-1], buf, start)
            buf = ""
        else:
            if not buf.strip(): start = line
            buf += ch
        if ch == "\n": line += 1

def _decls(sel, text, line):
    m = re.match(r"\s*([-\w]+)\s*:\s*(.+)", text, re.S)
    if m and not sel.startswith("@"):
        yield sel, m.group(1).lower(), " ".join(m.group(2).split()), line

def selectors(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{", css):
        s = " ".join(m.group(1).split())
        if not s.startswith("@") and not re.fullmatch(r"(from|to|[\d.]+%)(\s*,\s*(from|to|[\d.]+%))*", s):
            depth, part = 0, ""
            for ch in s + ",":
                if ch == "," and depth == 0:
                    yield part.strip(); part = ""; continue
                depth += (ch == "(") - (ch == ")")
                part += ch

TIME = re.compile(r"(?<![\w.-])(\d*\.?\d+)(ms|s)\b")
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(\s*[\d.]")

def check_css(site, owns):
    seen = {}
    def once(rule, where, msg):
        key = (rule, where.split(":")[0])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= 3:
            bad(where, msg)
        elif seen[key] == 4:
            bad(key[1], f"…and more {rule} problems in this file")
    for label, css in site_css(site):
        for sel, prop, val, line in declarations(css):
            if prop.startswith("--"):
                continue                                  # token definitions may hold raw values
            v = re.sub(r"url\([^)]*\)", "", val)
            where = f"{label}:{line}"
            if "type-scale" not in owns and prop == "font-size" and re.search(r"\d(px|rem|pt)\b", v):
                once("type-scale", where, f"font-size: {val} — use --text-* (or a token you define)")
            if "weights" not in owns and prop == "font-weight" and re.search(r"^\d+$|^bold(er)?$|^lighter$", v):
                once("weights", where, f"font-weight: {val} — use --weight-regular/medium/semibold")
            if "weights" not in owns and prop == "font" and re.search(r"\b[1-9]00\b|\bbold\b", v):
                once("weights", where, f"font: {val} — weight must come from --weight-*")
            if "motion" not in owns and re.match(r"(transition|animation)(-duration)?$", prop):
                times = [t for t in TIME.findall(v) if float(t[0]) * (1 if t[1] == "ms" else 1000) > 1]
                if times:
                    once("motion", where, f"{prop}: {val} — durations come from --dur-* (or a token you define)")
            if "colour" not in owns and COLOUR.search(v):
                once("colour", where, f"{prop}: {val} — colours come from tokens")
            if "fonts" not in owns and prop == "font-family" and not re.search(r"var\(--font-|^inherit$", v):
                once("fonts", where, f"font-family: {val} — use --font-sans/display/mono")
        if "fonts" not in owns and re.search(r"@font-face", css):
            bad(label, "@font-face in a site — fonts come from the canonical link or gramofdesign/fonts/")
        if "element-rules" not in owns:
            for s in selectors(css):
                subject = re.split(r"\s*[>+~\s]\s*(?![^(]*\))", s)[-1]
                if "::-webkit-" in subject or "::-moz-" in subject:
                    continue                              # browser-part tweaks, not restyling
                if re.match(r"(button|input|select|textarea)(?![\w-])", subject) and "." not in subject:
                    if "#" in s or "." not in s:
                        once("element-rules", label, f"`{s}` styles form controls broadly — give them a site class")
                if "#" in s and re.search(SHARED, s):
                    once("element-rules", label, f"`{s}` restyles a shared component through an id")

# ── Repo hygiene ────────────────────────────────────────────────────────────
def check_repo(site):
    try:
        top = Path(subprocess.run(["git", "-C", str(site), "rev-parse", "--show-toplevel"],
                                  capture_output=True, text=True, check=True).stdout.strip())
    except Exception:
        return bad("repo", "not a git repository")
    tracked = subprocess.run(["git", "-C", str(top), "ls-files"], capture_output=True, text=True).stdout.split("\n")
    if any(t.endswith(".DS_Store") for t in tracked):
        bad("repo", ".DS_Store is tracked — git rm --cached it")
    gi = top / ".gitignore"
    if not gi.exists() or ".DS_Store" not in gi.read_text():
        bad("repo", ".gitignore must ignore .DS_Store")
    for f in ("README.md", "LICENSE"):
        if not (top / f).exists():
            bad("repo", f"no {f}")
    lic = (top / "LICENSE").read_text() if (top / "LICENSE").exists() else ""
    if lic and "unencumbered software released into the public domain" not in lic:
        bad("LICENSE", "the family is released under the Unlicense")

# ── A site ──────────────────────────────────────────────────────────────────
def check_site(site, acc):
    site = site.resolve()
    html = site / "index.html"
    if not html.exists():
        return bad(str(site), "no index.html")
    name = product(site)
    if not name:
        return bad("index.html", 'no data-accent="…" on <html>; it names the product and its mark')
    print(f"{name}  ({site})")
    check_mark(name, acc)

    owns = {}
    cfg = site / ".gramof.json"
    if cfg.exists():
        try:
            owns = json.loads(cfg.read_text()).get("owns", {})
        except ValueError as e:
            bad(".gramof.json", f"not valid JSON ({e})")
        for rule, why in owns.items():
            if rule not in RULES:
                bad(".gramof.json", f"unknown rule '{rule}' (see ./check.py --rules)")
            elif not str(why).strip():
                bad(".gramof.json", f"owning '{rule}' needs a reason")
            else:
                note(f"owns {rule}: {why}")

    mark = GD / "marks" / f"{name}.svg"
    fsvg = site / "favicon.svg"
    if not fsvg.exists():
        bad("favicon.svg", "missing")
    elif mark.exists() and fsvg.read_bytes() != mark.read_bytes():
        bad("favicon.svg", f"differs from gramofdesign/marks/{name}.svg — copy the mark, never edit here")

    ico = site / "favicon.ico"
    if not ico.exists():
        bad("favicon.ico", "missing")
    else:
        b = ico.read_bytes()
        _, typ, count = struct.unpack("<HHH", b[:6])
        sizes = [(b[6 + 16 * k] or 256, b[7 + 16 * k] or 256) for k in range(count)]
        if typ != 1 or sizes != [(32, 32)]:
            bad("favicon.ico", f"must hold exactly one 32×32 frame, has {sizes}")

    def png(p, size, opaque):
        where = str(p.relative_to(site))
        if not p.exists():
            return bad(where, "missing")
        info = png_info(p)
        if not info:
            return bad(where, "not a PNG")
        if (info["w"], info["h"]) != (size, size):
            bad(where, f"must be {size}×{size}, is {info['w']}×{info['h']}")
        if opaque and (info["ct"] not in (0, 2, 3) or "tRNS" in info["chunks"]):
            bad(where, "must be opaque, full-bleed (no alpha): iOS/Safari round it themselves")
        if "caBX" in info["chunks"] or "meta" in info["chunks"]:
            bad(where, "carries provenance/XMP metadata; strip it")
    png(site / "apple-touch-icon.png", 180, True)

    manifest = (site / "site.webmanifest").exists()
    for s in (192, 512):
        f = site / f"android-chrome-{s}x{s}.png"
        if manifest:
            png(f, s, False)
        elif f.exists():
            bad(f.name, "only installable sites (with site.webmanifest) ship manifest icons")

    keep = {"favicon.svg", "favicon.ico", "apple-touch-icon.png"}
    for f in site.rglob("*"):
        rel = f.relative_to(site)
        if SKIP_DIRS.intersection(rel.parts) or not f.is_file():
            continue
        if re.match(r"(favicon|apple-touch-icon|mstile|safari-pinned-tab)", f.name, re.I) and str(rel) not in keep:
            bad(str(rel), "stray favicon file; the set is favicon.svg, favicon.ico, apple-touch-icon.png")

    for page in sorted(site.glob("*.html")):
        text = page.read_text()
        if "<head" not in text:
            continue
        head = text.split("</head>")[0]
        found = [re.sub(r"\s+", " ", t.strip()) for t in ICON_REL.findall(head)]
        want = HEAD + ([MANIFEST] if manifest else [])
        if found != want:
            bad(page.name, "icon links must be exactly:\n      " + "\n      ".join(want)
                + "\n    found:\n      " + ("\n      ".join(found) or "(none)"))
        if f'data-accent="{name}"' not in text:
            bad(page.name, f'<html data-accent="{name}"> on every page')
        if "getItem('theme')" not in head and 'getItem("theme")' not in head:
            bad(page.name, "no no-flash theme snippet in <head>")
        if 'name="color-scheme"' not in head:
            bad(page.name, '<meta name="color-scheme" content="light dark"> missing')
        links = [re.sub(r"^\./", "", l.replace("&amp;", "&"))
                 for tag in re.findall(r"<link\b[^>]*>", head) if re.search(r'rel="stylesheet"', tag)
                 for l in re.findall(r'href="([^"]+)"', tag)]
        fontlinks = [l for l in links if "fonts.googleapis" in l or l.endswith("fonts.css")]
        if "fonts" not in owns and fontlinks not in ([GOOGLE_FONTS], [SELF_FONTS]):
            bad(page.name, "fonts: link exactly one of\n      " + GOOGLE_FONTS + "\n      " + SELF_FONTS
                + "\n    found: " + (", ".join(fontlinks) or "(none)"))
        if "gramofdesign/gramof.css" not in links:
            bad(page.name, "does not link gramofdesign/gramof.css")
        if "viewport-zoom" not in owns and re.search(r'user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b', head):
            bad(page.name, "viewport blocks zoom")
        if "cdn" not in owns:
            for src in re.findall(r'<script\b[^>]*src="(https?://[^"]+)"', text):
                if not re.search(r"@\d+\.\d+\.\d+", src):
                    bad(page.name, f"unpinned third-party script {src} — pin an exact version")
        if "meta" not in owns:
            title = re.search(r"<title>(.*?)</title>", head, re.S)
            title = title.group(1).strip() if title else ""
            if page.name == "index.html":
                if title != name:
                    bad(page.name, f'<title>{title}</title> — the index title is the product name: "{name}"')
                for tag in ('name="description"', 'property="og:title"', 'property="og:description"', 'property="og:url"'):
                    if tag not in head:
                        bad(page.name, f"missing <meta {tag} …>")
            else:
                if not title.endswith(f" · {name}"):
                    bad(page.name, f'<title>{title}</title> — other pages are titled "<page> · {name}"')
                if 'name="description"' not in head:
                    bad(page.name, 'missing <meta name="description" …>')

    check_css(site, owns)
    check_repo(site)

    vend = site / "gramofdesign"
    if not vend.is_dir():
        bad("gramofdesign/", "no vendored copy")
    else:
        for f in sorted(vend.rglob("*")):
            if not f.is_file() or f.name == ".DS_Store":
                continue
            rel = f.relative_to(vend); canon = GD / rel
            if canon.exists() and canon.read_bytes() != f.read_bytes():
                bad(f"gramofdesign/{rel}", "out of sync with the design repo — ./check.py --sync")
            elif not canon.exists():
                bad(f"gramofdesign/{rel}", "not in the design repo (vendored copies add nothing)")

# ── Sync ────────────────────────────────────────────────────────────────────
def sync(targets):
    print("sync")
    for s in targets:
        vend = s / "gramofdesign"
        if not vend.is_dir():
            print(f"  skip {s}: no gramofdesign/")
            continue
        for f in sorted(vend.rglob("*")):
            canon = GD / f.relative_to(vend)
            if f.is_file() and not canon.exists() and f.name != ".DS_Store":
                f.unlink(); print(f"  removed {s.name}/gramofdesign/{f.relative_to(vend)}")
            elif f.is_file() and canon.is_file() and canon.read_bytes() != f.read_bytes():
                shutil.copyfile(canon, f); print(f"  synced  {s.name}/gramofdesign/{f.relative_to(vend)}")
        # keep the vendored folders that a site carries complete
        for sub in ("marks", "icons", "fonts"):
            if (vend / sub).is_dir():
                for c in (GD / sub).iterdir():
                    if c.is_file() and not (vend / sub / c.name).exists():
                        shutil.copyfile(c, vend / sub / c.name); print(f"  added   {s.name}/gramofdesign/{sub}/{c.name}")

def main():
    args = sys.argv[1:]
    if args[:1] == ["--rules"]:
        for k, v in RULES.items():
            print(f"{k:14} {v}")
        return
    acc = accents()
    if args[:1] == ["--sync-only"]:
        sync([Path(a).resolve() for a in args[1:]] or [p.resolve() for p in registered()])
        return
    if args[:1] == ["--sync"]:
        targets = [Path(a).resolve() for a in args[1:]] or [p.resolve() for p in registered()]
        sync(targets)
        args = args[1:]
    if args:
        sites = [Path(a) for a in args]
    else:
        sites = registered()
        print("marks")
        used = {product(s) for s in sites}
        for p in sorted((GD / "marks").glob("*.svg")):
            if p.stem not in used:
                bad(f"marks/{p.name}", "no site in sites.txt uses this mark")
    for s in sites:
        check_site(s, acc)
    print(f"\n{'✓ all clear' if not fails else f'✗ {fails} problem(s)'}")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()

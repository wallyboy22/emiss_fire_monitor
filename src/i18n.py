"""Idiomas das páginas (pt, en, es, fr, id, zh).

- i18n/traducoes.csv: tabela extraída das páginas (i18n/extrair_textos.py) e traduzida;
  i18n/extra.csv: textos curtos que o extrator não pega (mesmas colunas de idioma).
- No build, os literais de string do JS que estão na tabela viram TR('...'); trechos de HTML
  montados no JS têm só os textos entre as tags embrulhados.
- No navegador, TR() devolve a tradução do idioma escolhido, os dados (biomas, classes) são
  traduzidos ao carregar e um passe no DOM traduz o texto fixo da página.
O idioma fica em localStorage ('emf-lang') ou em ?lang=xx; trocar recarrega a página.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ["pt", "en", "es", "fr", "id", "zh"]
COLS = {"en": "en", "es": "es", "fr": "fr", "id": "ind", "zh": "zh"}
LOCALES = {"pt": "pt-BR", "en": "en-US", "es": "es-ES", "fr": "fr-FR", "id": "id-ID", "zh": "zh-CN"}
NAMES = {"pt": "Português", "en": "English", "es": "Español", "fr": "Français", "id": "Bahasa Indonesia", "zh": "中文"}


def _clean(pt, tr):
    """Tira a marca [REVISAR] e devolve os espaços das pontas iguais aos do original."""
    if tr is None:
        return None
    t = tr.replace("[REVISAR]", "").strip()
    if not t and pt.strip():
        return None if pt != " de " else ""
    lead = " " if pt[:1] == " " else ""
    trail = " " if pt[-1:] == " " else ""
    return lead + t + trail


def load(paths=None):
    paths = paths or [ROOT / "i18n" / "traducoes.csv", ROOT / "i18n" / "extra.csv"]
    out, manual = {}, set()
    for p in paths:
        if not Path(p).exists():
            continue
        for r in csv.DictReader(Path(p).open(encoding="utf-8-sig")):
            pt = r["pt"]
            if not pt:
                continue
            row = [_clean(pt, r.get(COLS[lg])) for lg in LANGS[1:]]
            if pt == " de ":  # mês de ano: só o português e o espanhol usam "de"
                row = [" " if lg != "es" else " de " for lg in LANGS[1:]]
            if any(v is not None for v in row):
                out[pt] = [v if v is not None else pt for v in row]
            if (r.get("auto") or "").strip().lower() == "nao":
                manual.add(pt)
    return out, manual


def auto_keys(d, manual):
    """Textos que o build embrulha sozinho (os 'manuais' são chaves no código e vão com TR() explícito)."""
    return set(d) - manual


def runtime(d):
    """Script do <head>: idioma, TR(), tradução dos dados e passe no DOM."""
    return ("<script>" + """
var I18N = %s, LANGS = %s, LOCALES = %s;
var LANG = 'pt';
try { var q = new URLSearchParams(location.search).get('lang'); if (q && LANGS.indexOf(q) >= 0) localStorage.setItem('emf-lang', q);
  LANG = localStorage.getItem('emf-lang') || 'pt'; } catch (e) {}
if (LANGS.indexOf(LANG) < 0) LANG = 'pt';
var LI = LANGS.indexOf(LANG) - 1, LOC = LOCALES[LANG];
document.documentElement.setAttribute('lang', LOC);
function TR(s) { if (LI < 0 || typeof s !== 'string') return s; var r = I18N[s]; return r ? r[LI] : s; }
function i18nDeep(o) {
  if (LI < 0) return o;
  if (typeof o === 'string') return TR(o);
  if (Array.isArray(o)) { if (o.length && typeof o[0] === 'number') return o; return o.map(i18nDeep); }
  if (o && typeof o === 'object') { var r = {}; for (var k in o) r[/[A-ZÀ-ÿ ]/.test(k) ? TR(k) : k] = i18nDeep(o[k]); return r; }
  return o;
}
var I18N_MON = [], I18N_MES = [];
(function () { for (var m = 0; m < 12; m++) { var dt = new Date(2020, m, 15);
  I18N_MES.push(dt.toLocaleDateString(LOC, { month: 'long' }));
  I18N_MON.push(dt.toLocaleDateString(LOC, { month: 'short' }).replace('.', '')); } })();
(function () {
  if (LI < 0) return;
  var ATTR = ['title', 'aria-label', 'alt', 'placeholder'];
  function tr(raw) { var n = raw.replace(/\\s+/g, ' ').trim(); if (!n || !(n in I18N)) return null;
    var m = raw.match(/^\\s*/)[0], e = raw.match(/\\s*$/)[0]; return m + I18N[n][LI] + e; }
  function walk(root) {
    if (root.nodeType === 3) { var t = tr(root.data); if (t !== null) root.data = t; return; }
    if (root.nodeType !== 1 || root.tagName === 'SCRIPT' || root.tagName === 'STYLE') return;
    for (var i = 0; i < ATTR.length; i++) { var v = root.getAttribute(ATTR[i]); if (v) { var t2 = tr(v); if (t2 !== null) root.setAttribute(ATTR[i], t2); } }
    if (root.tagName === 'META' && root.getAttribute('name') === 'description') { var c = tr(root.getAttribute('content') || ''); if (c !== null) root.setAttribute('content', c); }
    for (var ch = root.firstChild; ch; ch = ch.nextSibling) walk(ch);
  }
  window.i18nWalk = walk;
  document.addEventListener('DOMContentLoaded', function () {
    walk(document.documentElement);
    new MutationObserver(function (ms) { ms.forEach(function (m) { m.addedNodes.forEach(walk); }); })
      .observe(document.documentElement, { childList: true, subtree: true });
  });
})();
""" % (json.dumps(d, ensure_ascii=False, separators=(",", ":")), json.dumps(LANGS), json.dumps(LOCALES)) + "</script>")


def select_html():
    opts = "".join(f'<option value="{lg}">{lg.upper()}</option>' for lg in LANGS)
    return (f'<select class="site-btn site-lang" id="selLang" aria-label="Idioma / Language">{opts}</select>'
            "<script>(function () { var s = document.getElementById('selLang'); s.value = LANG;"
            + "var N = " + json.dumps(NAMES, ensure_ascii=False) + "; for (var i = 0; i < s.options.length; i++) s.options[i].title = N[s.options[i].value];"
            + "s.addEventListener('change', function () { try { localStorage.setItem('emf-lang', s.value); } catch (e) {}"
            + " var u = new URL(location.href); u.searchParams.delete('lang'); history.replaceState(null, '', u.toString()); location.reload(); }); })();</script>")


# ---------------------------------------------------------------- embrulho dos literais do JS
def _literals(src):
    """(início, fim, aspas) de cada literal de string, pulando comentários e regex."""
    i, n, out, prev = 0, len(src), [], "("
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "'\"`":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 2
                    continue
                if c == "`" and src.startswith("${", j):
                    depth, j = 1, j + 2
                    while j < n and depth:
                        depth += {"{": 1, "}": -1}.get(src[j], 0)
                        j += 1
                    continue
                j += 1
            out.append((i, j + 1, c))
            i, prev = j + 1, "x"
            continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%<>~^":
            j, cls = i + 1, False
            while j < n and (src[j] != "/" or cls):
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                elif src[j] == "\n":
                    break
                j += 1
            i, prev = j + 1, "x"
            continue
        if c.isalpha() or c in "_$":
            k = i
            while k < n and (src[k].isalnum() or src[k] in "_$"):
                k += 1
            prev = "(" if src[i:k] in ("return", "typeof", "case", "in", "of") else "x"
            i = k
            continue
        if not c.isspace():
            prev = c
        i += 1
    return out


def _decode(raw):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), raw)


def _norm(s):
    return re.sub(r"\s+", " ", s)


def wrap_js(src, keys):
    out, last, n_wrapped = [], 0, 0
    for a, b, q in _literals(src):
        if q == "`":
            continue
        raw = src[a + 1:b - 1]
        text = _norm(_decode(raw))
        rep = None
        if text in keys and "<" not in text:
            rep = f"TR({src[a:b]})"
        elif "<" in raw or ">" in raw:
            # só os textos entre tags completas; pontas com pedaço de tag ficam como estão
            head = re.match(r"^[^<]*>", raw) if not raw.lstrip().startswith("<") else None
            h = head.end() if head else 0
            tail = re.search(r"<[^>]*$", raw[h:])
            t = h + tail.start() if tail else len(raw)
            parts, changed = [], False
            for chunk in re.split(r"(<[^<>]*>)", raw[h:t]):
                core = _norm(_decode(chunk)).strip()
                if chunk.startswith("<") or not core or core not in keys:
                    parts.append(("lit", chunk))
                    continue
                lead = chunk[:len(chunk) - len(chunk.lstrip())]
                trail = chunk[len(chunk.rstrip()):]
                parts += [("lit", lead), ("t", chunk.strip()), ("lit", trail)]
                changed = True
            if changed:
                pieces = [("lit", raw[:h])] + parts + [("lit", raw[t:])]
                expr = " + ".join(f"TR({q}{v}{q})" if k == "t" else f"{q}{v}{q}" for k, v in pieces if v or k == "t")
                rep = "(" + expr + ")"
        if rep is None:
            continue
        # chave de objeto ({ 'x': ... }) vira chave calculada
        before = src[:a].rstrip()[-1:]
        after = src[b:].lstrip()[:1]
        if after == ":" and before in "{,":
            rep = f"[{rep}]"
        out.append(src[last:a] + rep)
        last = b
        n_wrapped += 1
    out.append(src[last:])
    return "".join(out).replace("'pt-BR'", "LOC"), n_wrapped


def wrap_scripts(html, keys):
    """Embrulha os literais dos <script> da página (menos o Chart.js e os dados)."""
    total = 0

    def sub(m):
        nonlocal total
        body = m.group(1)
        if "__CHART_JS__" in body or "Chart.js v" in body[:4000]:
            return m.group(0)
        new, k = wrap_js(body, keys)
        total += k
        return "<script>" + new + "</script>"
    out = re.sub(r"<script>([\s\S]*?)</script>", sub, html)
    return out, total

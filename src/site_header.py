"""Cabeçalho comum às páginas (painel e destaques): aviso, logos, abas e botão de tema.

As páginas definem os tokens de cor (--page, --surface, --ink, --ink-2, --muted, --grid, --axis,
--accent, --on-accent, --accent-weak) para os temas claro e escuro; o cabeçalho só os consome.
O tema escolhido fica em localStorage ('emf-theme') e vale para as duas páginas.
"""
import base64
from pathlib import Path

LOGO_DIR = Path(__file__).resolve().parent.parent / "assets" / "logos"
THEME_KEY = "emf-theme"

NOTICE = ('Página <strong>não oficial e exploratória</strong>. Todo o conteúdo pertence e está reservado ao IPAM. '
          'Site oficial: <a href="https://ipam.org.br" target="_blank" rel="noopener">ipam.org.br</a>')

CSS = """
.site-notice { background: var(--surface); border-bottom: 1px solid var(--grid); color: var(--ink-2); font-size: 12.5px;
  text-align: center; padding: 6px 16px; line-height: 1.4; }
.site-notice a { color: var(--accent); font-weight: 700; }
.site-top { border-bottom: 1px solid var(--grid); background: var(--page); }
.site-top .in { max-width: 1500px; margin: 0 auto; padding: 10px 16px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.site-brand { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--ink); white-space: nowrap; }
.site-logos { display: flex; align-items: center; gap: 10px; background: #fff; border-radius: 10px; padding: 4px 10px; border: 1px solid var(--grid); }
.site-logos img { display: block; width: auto; }
.site-logos .mbf { height: 26px; }
.site-logos .ipam { height: 34px; }
.site-logos i { width: 1px; align-self: stretch; background: #ddd5c8; }
.site-name { font-weight: 700; font-size: 15px; line-height: 1.15; }
.site-name small { display: block; font-size: 10.5px; font-weight: 650; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
.site-nav { display: flex; gap: 4px; flex: 1; flex-wrap: wrap; }
.site-nav a { padding: 6px 13px; border-radius: 999px; text-decoration: none; color: var(--ink-2); font-weight: 600; font-size: 14px; white-space: nowrap; }
.site-nav a:hover { background: var(--accent-weak); }
.site-nav a[aria-current="page"] { background: var(--accent); color: var(--on-accent); }
.site-nav a:focus-visible, .site-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.site-btn { border: 1px solid var(--axis); background: var(--surface); color: var(--ink); border-radius: 999px; padding: 6px 13px;
  font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
@media (max-width: 720px) { .site-name { display: none; } .site-nav { order: 3; flex-basis: 100%; } .site-btn { margin-left: auto; } }
@media print { .site-notice, .site-top { display: none !important; } }
"""


def _logo(name):
    data = (LOGO_DIR / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def logos_html():
    return ('<span class="site-logos"><img class="mbf" src="' + _logo("mapbiomas_fogo.png") + '" alt="MapBiomas Fogo">'
            '<i></i><img class="ipam" src="' + _logo("ipam.png") + '" alt="IPAM"></span>')


def html(pages, active):
    """pages: [(href, rótulo, id)]; active: id da aba atual (o painel troca a aba ativa pelo JS)."""
    nav = "".join(f'<a href="{h}" id="{i}"' + (' aria-current="page"' if i == active else '') + f'>{t}</a>'
                  for h, t, i in pages)
    return (f'<div class="site-notice">{NOTICE}</div>'
            '<div class="site-top" role="banner"><div class="in"><a class="site-brand" href="index.html#painel">' + logos_html()
            + '<span class="site-name">Monitor de emissões por fogo<small>exploratório</small></span></a>'
            f'<nav class="site-nav" aria-label="Páginas">{nav}</nav>'
            '<button type="button" class="site-btn" id="btnTheme"></button></div></div>')


# tema: lê a escolha salva antes de desenhar; o botão alterna e avisa a página pelo evento 'emf-theme'
JS_HEAD = ("<script>(function(){var t='light';try{t=localStorage.getItem('" + THEME_KEY + "')||'light'}catch(e){}"
           "document.documentElement.setAttribute('data-theme',t)})();</script>")
JS_BODY = """<script>(function () {
  var b = document.getElementById('btnTheme'), r = document.documentElement;
  function label() { b.textContent = r.getAttribute('data-theme') === 'dark' ? '☀ Claro' : '☾ Escuro';
    b.setAttribute('aria-label', r.getAttribute('data-theme') === 'dark' ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'); }
  label();
  b.addEventListener('click', function () {
    var t = r.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    r.setAttribute('data-theme', t);
    try { localStorage.setItem('""" + THEME_KEY + """', t); } catch (e) {}
    label(); document.dispatchEvent(new CustomEvent('emf-theme', { detail: t }));
  });
})();</script>"""

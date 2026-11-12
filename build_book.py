"""
Genera index.html interactivo, raw_otra_coronacion_de_gloria.md y book_content.json
a partir de las fuentes LaTeX del libro de Max Schulkin.

Fuente única de verdad: ../otracoronacion/otra_coronacion_latex/main.tex
(otra ruta: variable de entorno OCG_LATEX_DIR)
Pipeline: LaTeX --(conversor propio)--> markdown --(Python-Markdown)--> index.html

Requisitos: paquete python `markdown`.
Uso: python build_book.py
"""
import os, re, json, html as html_module, unicodedata
import markdown as md_lib

BASE   = os.path.dirname(os.path.abspath(__file__))
LATEX_DIR = os.environ.get('OCG_LATEX_DIR',
                           os.path.join(BASE, '..', 'otracoronacion', 'otra_coronacion_latex'))
MD_OUT = os.path.join(BASE, 'raw_otra_coronacion_de_gloria.md')
JSON_OUT = os.path.join(BASE, 'book_content.json')
HTML_OUT = os.path.join(BASE, 'index.html')

# ═══════════════════════════════════════════════════════════════
# 1. LaTeX → MARKDOWN
#    Cubre solo el subconjunto que usa el libro: \capitulo, \chapter*, secciones,
#    itemize/enumerate (anidadas, etiquetas a) e i.), tabularx con booktabs,
#    \emph \textbf \textsubscript \url \footnote \cite y thebibliography.
# ═══════════════════════════════════════════════════════════════

def read_sources(latex_dir):
    """Devuelve el texto concatenado de los \\input del cuerpo de main.tex, en orden."""
    main = open(os.path.join(latex_dir, 'main.tex'), encoding='utf-8').read()
    main = main[main.index(r'\begin{document}'):]
    names = re.findall(r'(?m)^[^%\n]*\\input\{([^}]+)\}', main)
    return [open(os.path.join(latex_dir, n + '.tex'), encoding='utf-8').read() for n in names]


class Converter:
    def __init__(self, bib_keys):
        self.ref_num = {k: i + 1 for i, k in enumerate(bib_keys)}
        self.footnotes = []   # definiciones markdown [^n]: ...
        self.ol_types = []    # tipo de cada <ol> en orden de aparición (None, 'a', 'i')
        self.cap = 0

    # ── inline ────────────────────────────────────────────────
    def cite(self, m):
        opt, keys = m.group(1), m.group(2).split(',')
        links = [f'<a href="#ref-{self.ref_num[k.strip()]}">{self.ref_num[k.strip()]}</a>'
                 for k in keys]
        extra = f', {opt}' if opt else ''
        return '<span class="cite">[' + ', '.join(links) + extra + ']</span>'

    def inline(self, s):
        urls = []
        def url(m):
            u = re.sub(r'\\([_%#&$])', r'\1', m.group(1))
            urls.append(f'<a href="{html_module.escape(u)}">{html_module.escape(u)}</a>')
            return f'\x00{len(urls) - 1}\x00'
        s = re.sub(r'\\url\{([^}]*)\}', url, s)
        s = s.replace('<', '&lt;').replace('>', '&gt;').replace(r'\&', '&amp;')
        s = re.sub(r'\\cite(?:\[([^\]]*)\])?\{([^}]*)\}', self.cite, s)
        tags = {'emph': 'em', 'textbf': 'strong', 'textsubscript': 'sub'}
        def cmd(m):
            name, body = m.group(1), m.group(2)
            if name == 'footnote':
                self.footnotes.append(tidy(body))
                return f'[^{len(self.footnotes)}]'
            return f'<{tags[name]}>{body}</{tags[name]}>'
        pat = re.compile(r'\\(emph|textbf|textsubscript|footnote)\{([^{}]*)\}')
        def tidy(t):
            t = re.sub(r'\\(small|noindent)\b\s*', '', t)
            t = re.sub(r'\\([%$_#])', r'\1', t).replace('~', '\u00a0').replace('\\\\', '<br>')
            t = t.replace('{', '').replace('}', '')
            return re.sub(r'\s+', ' ', t).strip()
        while pat.search(s):   # de adentro hacia afuera (anidamiento)
            s = pat.sub(cmd, s)
        s = tidy(s)
        return re.sub('\x00(\\d+)\x00', lambda m: urls[int(m.group(1))], s)

    # ── bloques ───────────────────────────────────────────────
    def heading(self, m):
        cmd, title = m.group(1), self.inline(m.group(2))
        if cmd == 'capitulo':
            self.cap += 1
            return f'\n\n# Capítulo {self.cap}: {title}\n\n'
        level = {'chapter*': 1, 'section': 2, 'subsection': 3, 'subsubsection': 4}[cmd]
        return f'\n\n{"#" * level} {title}\n\n'

    def table(self, m):
        body = m.group(1).replace(r'\toprule', '').replace(r'\bottomrule', '')
        head, rows = body.split(r'\midrule')
        def cells(row):
            return '| ' + ' | '.join(self.inline(c) for c in re.split(r'(?<!\\)&', row)) + ' |'
        head_rows = [r for r in head.split('\\\\') if r.strip()]
        body_rows = [r for r in rows.split('\\\\') if r.strip()]
        n = len(re.split(r'(?<!\\)&', head_rows[0]))
        lines = [cells(head_rows[0]), '|' + ' --- |' * n] + [cells(r) for r in body_rows]
        return '\n\n' + '\n'.join(lines) + '\n\n'

    def paragraphs(self, s):
        out = []
        for chunk in re.split(r'\n\s*\n', s):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.startswith(('#', '|')):   # heading o tabla ya convertidos
                out.append(chunk)
            else:
                p = self.inline(chunk)
                out.append(re.sub(r'^(\d+)\. ', r'\1\\. ', p))  # que no se lea como lista
        return out

    LIST = re.compile(r'\\begin\{(itemize|enumerate)\}(?:\[label=\\(alph|roman)\*[.)]\])?'
                      r'|\\end\{(?:itemize|enumerate)\}|\\item\b')

    def render(self, s):
        """Bloques markdown de s, con listas (posiblemente anidadas)."""
        out, i = [], 0
        while True:
            m = self.LIST.search(s, i)
            if not m:
                break
            assert m.group(0).startswith(r'\begin'), f'lista mal formada: {s[m.start():m.start()+80]!r}'
            out += self.paragraphs(s[i:m.start()])
            j, depth, items, item_start = m.end(), 1, [], None
            while depth:
                t = self.LIST.search(s, j)
                tok = t.group(0)
                if tok.startswith(r'\begin'):
                    depth += 1
                elif tok.startswith(r'\end'):
                    depth -= 1
                elif depth == 1:
                    if item_start is not None:
                        items.append(s[item_start:t.start()])
                    item_start = t.end()
                j = t.end()
                if depth == 0 and item_start is not None:
                    items.append(s[item_start:t.start()])
            ordered = m.group(1) == 'enumerate'
            if ordered:
                self.ol_types.append({'alph': 'a', 'roman': 'i'}.get(m.group(2)))
            blocks = []
            for n, item in enumerate(items, 1):
                marker = f'{n}. ' if ordered else '- '
                sub = '\n\n'.join(self.render(item)).split('\n')
                blocks.append('\n'.join([marker + sub[0]] + [('    ' + l) if l else '' for l in sub[1:]]))
            # con sublistas, Python-Markdown necesita líneas en blanco entre ítems
            out.append(('\n\n' if any('\n' in b for b in blocks) else '\n').join(blocks))
            i = j
        return out + self.paragraphs(s[i:])

    def convert(self, body):
        body = re.sub(r'\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}', '', body)
        body = re.sub(r'\\begin\{center\}\s*(?:\\small)?\s*\\begin\{tabularx\}\{[^}]*\}\{[^}]*\}'
                      r'(.*?)\\end\{tabularx\}\s*\\end\{center\}', self.table, body, flags=re.S)
        body = re.sub(r'(?m)^\\(capitulo|chapter\*|section|subsection|subsubsection)\{(.*)\}\s*$',
                      self.heading, body)
        md = '\n\n'.join(self.render(body))
        notes = '\n\n'.join(f'[^{i}]: {n}'
                            for i, n in enumerate(self.footnotes, 1))
        return md + ('\n\n' + notes if notes else '')


def latex_to_markdown(latex_dir):
    """Devuelve (markdown, tipos de <ol> en orden). Las referencias van como HTML con ids."""
    parts = read_sources(latex_dir)
    bib_src = next(p for p in parts if r'\begin{thebibliography}' in p)
    body = '\n\n'.join(p for p in parts if p is not bib_src)
    items = re.findall(r'\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})',
                       bib_src, flags=re.S)
    conv = Converter([k for k, _ in items])
    md = conv.convert(body)
    refs = '\n'.join(f'<li id="ref-{i}">{conv.inline(t)}</li>' for i, (_, t) in enumerate(items, 1))
    md = md.replace('\n\n[^1]:', f'\n\n# Referencias\n\n<ol class="refs">\n{refs}\n</ol>\n\n[^1]:', 1) \
        if conv.footnotes else md + f'\n\n# Referencias\n\n<ol class="refs">\n{refs}\n</ol>'
    return md.strip() + '\n', conv.ol_types


def apply_ol_types(body_html, ol_types):
    """Python-Markdown no expresa a) / i.: se asigna el tipo a cada <ol> en orden."""
    it = iter(ol_types)
    def sub(m):
        t = next(it, None)
        return f'<ol type="{t}">' if t else '<ol>'
    count = body_html.count('<ol>')
    out = re.sub(r'<ol>', sub, body_html, count=len(ol_types))
    # el bloque de notas al pie agrega un <ol> propio al final
    assert count - (1 if 'class="footnote"' in body_html else 0) == len(ol_types), \
        f'listas ordenadas: {count} en HTML vs {len(ol_types)} en LaTeX'
    return out

# ═══════════════════════════════════════════════════════════════
# 3. book_content.json (estructura {style, text} desde el markdown)
# ═══════════════════════════════════════════════════════════════

def build_book_content_json(md):
    out = [{'style': 'Title', 'text': 'Otra coronación de gloria'}]
    for line in md.split('\n'):
        line = line.strip()
        if not line or re.match(r'^\|[\s|-]+\|$', line) or line in ('<ol class="refs">', '</ol>'):
            continue
        m = re.match(r'^(#+) (.*)', line)
        style = f'Heading {len(m.group(1))}' if m else 'normal'
        text = m.group(2) if m else re.sub(r'^(?:[-*]|\d+\.|\[\^\d+\]:)\s+', '', line)
        text = html_module.unescape(re.sub(r'<[^>]+>', '', text)).replace('\\.', '.').strip(' |')
        if text:
            out.append({'style': style, 'text': text})
    return out

# ═══════════════════════════════════════════════════════════════
# 4. SIDEBAR TOC
# ═══════════════════════════════════════════════════════════════

def render_toc(tokens):
    parts = ['<ul class="toc-root">']
    for tok in tokens:
        title, tid = tok['name'], tok['id']
        children = tok.get('children', [])
        if tok['level'] == 1:
            parts.append(f'<li class="toc-ch"><a href="#{tid}" class="toc-ch-link">{html_module.escape(title)}</a>')
            if children:
                parts.append('<ul class="toc-secs">')
                for sec in children:
                    parts.append(
                        f'<li><a href="#{sec["id"]}" class="toc-sec-link">'
                        f'{html_module.escape(sec["name"])}</a></li>')
                parts.append('</ul>')
            parts.append('</li>')
        else:  # frontmatter (H2 antes del primer H1)
            parts.append(
                f'<li class="toc-ch"><a href="#{tid}" class="toc-ch-link toc-front">'
                f'{html_module.escape(title)}</a></li>')
    parts.append('</ul>')
    return ''.join(parts)

# ═══════════════════════════════════════════════════════════════
# 5. CSS
# ═══════════════════════════════════════════════════════════════

CSS = """
:root{
  --bg:#faf8f4;--surface:#fff;--text:#1a1a1a;--muted:#6b6b6b;
  --accent:#1a3a5c;--accent2:#e8f0f8;--border:#e0dcd6;--sw:300px}
[data-theme="dark"]{
  --bg:#111;--surface:#1c1c1c;--text:#e8e4dc;--muted:#8a8680;
  --accent:#89b4e0;--accent2:#1a2a3a;--border:#2c2c2c}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'Libre Baskerville',Georgia,serif;background:var(--bg);color:var(--text);display:flex;min-height:100vh;transition:background .25s,color .25s}

#pgbar{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:200;transition:width .08s linear}

#sidebar{position:fixed;top:0;left:0;width:var(--sw);height:100vh;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;z-index:100;transition:transform .28s,background .25s}
#sb-head{padding:1.4rem 1.4rem .9rem;border-bottom:1px solid var(--border);flex-shrink:0}
#sb-head .b-title{font-size:.88rem;font-weight:700;color:var(--accent);line-height:1.3}
#sb-head .b-author{font-family:'Inter',system-ui,sans-serif;font-size:.72rem;color:var(--muted);margin-top:.3rem}
#toc-scroll{flex:1;overflow-y:auto;padding:.8rem 0 2rem}
#toc-scroll::-webkit-scrollbar{width:3px}
#toc-scroll::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

.toc-root{list-style:none}
.toc-ch{margin-bottom:.05rem}
.toc-ch-link{display:block;padding:.5rem 1.2rem;font-family:'Inter',system-ui,sans-serif;font-size:.77rem;font-weight:600;color:var(--text);text-decoration:none;border-left:3px solid transparent;transition:background .13s,color .13s,border-color .13s}
.toc-ch-link:hover,.toc-ch-link.active{background:var(--accent2);color:var(--accent);border-left-color:var(--accent)}
.toc-front{font-weight:400;color:var(--muted)}
.toc-secs{list-style:none}
.toc-sec-link{display:block;padding:.3rem 1.2rem .3rem 2.3rem;font-family:'Inter',system-ui,sans-serif;font-size:.7rem;color:var(--muted);text-decoration:none;transition:color .13s}
.toc-sec-link:hover,.toc-sec-link.active{color:var(--accent)}

#main{margin-left:var(--sw);flex:1;min-width:0}
#toolbar{position:sticky;top:0;background:var(--surface);border-bottom:1px solid var(--border);padding:.65rem 1.8rem;display:flex;align-items:center;gap:.8rem;z-index:50;transition:background .25s}
#menu-btn{display:none;background:none;border:none;cursor:pointer;color:var(--text);font-size:1.3rem;padding:.2rem}
#reading-time{font-family:'Inter',system-ui,sans-serif;font-size:.72rem;color:var(--muted);margin-right:auto}
.tb-btn{background:none;border:1px solid var(--border);border-radius:6px;padding:.3rem .65rem;cursor:pointer;font-family:'Inter',system-ui,sans-serif;font-size:.72rem;color:var(--text);transition:border-color .13s,background .13s}
.tb-btn:hover{border-color:var(--accent);background:var(--accent2)}

#content{max-width:720px;margin:0 auto;padding:2.5rem 1.8rem 8rem}

.portada{min-height:60vh;display:flex;flex-direction:column;justify-content:center;text-align:center;padding:3rem 0 4rem;border-bottom:1px solid var(--border);margin-bottom:4rem}
.portada h1{font-size:clamp(1.8rem,4vw,3rem);font-weight:700;color:var(--accent);line-height:1.2;margin-bottom:1.2rem}
.portada .sub{font-style:italic;font-size:1.05rem;color:var(--muted);line-height:1.7;margin-bottom:.6rem}
.portada .attr{font-style:italic;font-size:.9rem;color:var(--muted);margin-bottom:1.8rem}
.portada .divider{width:50px;height:2px;background:var(--accent);margin:.8rem auto 1.6rem}
.portada .author{font-family:'Inter',system-ui,sans-serif;font-size:.85rem;font-weight:500;text-transform:uppercase;letter-spacing:.07em}

h1{font-size:clamp(1.4rem,2.8vw,2rem);font-weight:700;color:var(--accent);line-height:1.25;margin:4rem 0 1.5rem;padding-top:.5rem;border-top:1px solid var(--border)}
h1:first-of-type{border-top:none;margin-top:0}
h2{font-size:1.18rem;font-weight:700;color:var(--text);line-height:1.35;margin:2.5rem 0 1rem}
h3{font-family:'Inter',system-ui,sans-serif;font-size:.97rem;font-weight:600;color:var(--text);margin:1.8rem 0 .75rem}
h4,h5,h6{font-family:'Inter',system-ui,sans-serif;font-size:.88rem;font-weight:600;color:var(--muted);margin:1.4rem 0 .6rem}

p{font-size:var(--fs,1rem);line-height:1.85;margin-bottom:1.15em;text-align:justify;hyphens:auto}
blockquote{border-left:3px solid var(--accent);padding:.6rem 1.2rem;margin:1.5rem 0;font-style:italic;color:var(--muted)}
blockquote p{margin-bottom:0}
.cite{font-size:.75em;vertical-align:super;line-height:0;white-space:nowrap}
.cite a,.refs a,.footnote a{color:var(--accent)}
.refs{font-size:.85rem;overflow-wrap:anywhere}
.footnote{font-size:.85rem;color:var(--muted)}
.callout{background:var(--sidebar-bg,#f0f4f8);border-left:4px solid var(--accent);padding:.8rem 1.2rem;margin:1.5rem 0;border-radius:0 6px 6px 0;font-size:.92rem;line-height:1.7}

ul,ol{margin:1rem 0 1rem 1.8rem;font-size:var(--fs,1rem);line-height:1.85}
li{margin-bottom:.4rem}
ul ul,ol ol,ul ol,ol ul{margin:.3rem 0 .3rem 1.4rem}

table{border-collapse:collapse;width:100%;margin:1.8rem 0;font-size:.88rem;font-family:'Inter',system-ui,sans-serif;display:block;overflow-x:auto}
th,td{border:1px solid var(--border);padding:.5rem .8rem;text-align:left;vertical-align:top;white-space:normal}
th{background:var(--accent2);font-weight:600;color:var(--accent)}
tr:nth-child(even) td{background:var(--accent2)}
[data-theme="dark"] tr:nth-child(even) td{background:#222}

img{max-width:100%;height:auto;display:block;margin:1.5rem auto;border-radius:4px}

#content.fs-sm p,#content.fs-sm li,#content.fs-sm td{--fs:.88rem}
#content.fs-md p,#content.fs-md li,#content.fs-md td{--fs:1rem}
#content.fs-lg p,#content.fs-lg li,#content.fs-lg td{--fs:1.14rem}
#content.fs-xl p,#content.fs-xl li,#content.fs-xl td{--fs:1.28rem}

@media(max-width:768px){
  #sidebar{transform:translateX(-100%)}
  #sidebar.open{transform:translateX(0);box-shadow:0 0 40px rgba(0,0,0,.2)}
  #main{margin-left:0}
  #menu-btn{display:block}
  #content{padding:1.5rem 1.1rem 6rem}}
#overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:99}
#overlay.show{display:block}
"""

# ═══════════════════════════════════════════════════════════════
# 6. JS
# ═══════════════════════════════════════════════════════════════

JS = r"""
const pgbar = document.getElementById('pgbar');
window.addEventListener('scroll', () => {
  const h = document.documentElement;
  pgbar.style.width = (h.scrollTop / (h.scrollHeight - h.clientHeight) * 100) + '%';
}, {passive:true});

const wc = document.getElementById('content').innerText.split(/\s+/).length;
document.getElementById('reading-time').textContent = 'Tiempo de lectura: ~' + Math.ceil(wc/200) + ' min';

const tocEl   = document.getElementById('toc-scroll');
const tocLinks = Array.from(document.querySelectorAll('#toc-scroll a[href^="#"]'));
const headEls  = tocLinks.map(a => document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);

function setActive(id) {
  tocLinks.forEach(a => a.classList.remove('active'));
  const a = document.querySelector('#toc-scroll a[href="#' + id + '"]');
  if (!a) return;
  a.classList.add('active');
  const linkTop = a.offsetTop;
  const sh = tocEl.clientHeight;
  if (linkTop < tocEl.scrollTop + 60 || linkTop > tocEl.scrollTop + sh - 60) {
    tocEl.scrollTop = linkTop - sh / 2;
  }
}

let ticking = false;
window.addEventListener('scroll', () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => {
    const sy = window.scrollY + window.innerHeight * 0.25;
    let active = headEls[0];
    for (const el of headEls) { if (el.offsetTop <= sy) active = el; else break; }
    if (active) setActive(active.id);
    ticking = false;
  });
}, {passive:true});

const content = document.getElementById('content');
const sizes = ['fs-sm','fs-md','fs-lg','fs-xl'];
let si = 1; content.classList.add(sizes[si]);
document.getElementById('fs-down').addEventListener('click', () => {
  content.classList.remove(sizes[si]); si = Math.max(0, si-1); content.classList.add(sizes[si]);
});
document.getElementById('fs-up').addEventListener('click', () => {
  content.classList.remove(sizes[si]); si = Math.min(sizes.length-1, si+1); content.classList.add(sizes[si]);
});

const themeBtn = document.getElementById('theme-btn');
let dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const applyTheme = () => { document.documentElement.dataset.theme = dark ? 'dark' : ''; themeBtn.textContent = dark ? '☀️' : '🌙'; };
applyTheme();
themeBtn.addEventListener('click', () => { dark = !dark; applyTheme(); });

const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('overlay');
document.getElementById('menu-btn').addEventListener('click', () => {
  sidebar.classList.toggle('open'); overlay.classList.toggle('show');
});
overlay.addEventListener('click', () => { sidebar.classList.remove('open'); overlay.classList.remove('show'); });
document.querySelectorAll('#toc-scroll a').forEach(a => a.addEventListener('click', () => {
  sidebar.classList.remove('open'); overlay.classList.remove('show');
}));
"""

# ═══════════════════════════════════════════════════════════════
# 7. PORTADA
# ═══════════════════════════════════════════════════════════════

PORTADA_HTML = """<div id="portada" class="portada">
  <h1>Otra coronación de gloria</h1>
  <div class="divider"></div>
  <p class="sub">Con los dirigentes a la cabeza<br>o con la cabeza de los dirigentes.</p>
  <p class="attr"><em>– J.&#8239;D. Perón</em></p>
  <p class="author">Maximiliano Aaron Schulkin</p>
</div>"""

# ═══════════════════════════════════════════════════════════════
# 8. MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    clean, ol_types = latex_to_markdown(LATEX_DIR)

    with open(MD_OUT, 'w', encoding='utf-8') as f:
        f.write(clean)

    book_json = build_book_content_json(clean)
    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(book_json, f, ensure_ascii=False)

    proc = md_lib.Markdown(extensions=['extra', 'sane_lists', 'toc', 'smarty'])
    body_html = apply_ol_types(proc.convert(clean), ol_types)
    toc_sidebar_html = render_toc(proc.toc_tokens)

    HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Otra coronación de gloria — Max Schulkin</title>
<meta name="description" content="Plan de 20 años para transformar Argentina en un país autosuficiente. Por Maximiliano Schulkin.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div id="pgbar"></div>
<nav id="sidebar">
  <div id="sb-head">
    <div class="b-title">Otra coronación de gloria</div>
    <div class="b-author">Max Schulkin</div>
  </div>
  <div id="toc-scroll">{toc_sidebar_html}</div>
</nav>
<div id="overlay"></div>
<div id="main">
  <div id="toolbar">
    <button id="menu-btn" aria-label="Menú">☰</button>
    <span id="reading-time"></span>
    <button class="tb-btn" id="fs-down">A&minus;</button>
    <button class="tb-btn" id="fs-up">A+</button>
    <button class="tb-btn" id="theme-btn">🌙</button>
  </div>
  <div id="content">
    {PORTADA_HTML}
    {body_html}
  </div>
</div>
<script>{JS}</script>
</body>
</html>"""

    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(HTML)

    print(f'OK')
    print(f'  md   → {MD_OUT} ({len(clean):,} chars)')
    print(f'  json → {JSON_OUT} ({len(book_json)} entries)')
    print(f'  html → {HTML_OUT} ({len(HTML):,} chars)')
    print(f'  toc  → {len(proc.toc_tokens)} top-level entries')


if __name__ == '__main__':
    main()

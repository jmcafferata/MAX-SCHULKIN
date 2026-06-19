"""
Genera index.html interactivo, raw_otra_coronacion_de_gloria.md y book_content.json
a partir del .docx del libro de Max Schulkin.

Fuente única de verdad: raw_otra_coronacion_de_gloria.docx
Pipeline: docx --(pandoc)--> markdown --(limpieza)--> render --> index.html

Requisitos: pandoc en PATH, paquetes python `markdown` y `python-docx`.
Uso: python build_book.py
"""
import os, re, json, base64, html as html_module, subprocess, tempfile, shutil
import markdown as md_lib

BASE   = os.path.dirname(os.path.abspath(__file__))
DOCX   = os.path.join(BASE, 'raw_otra_coronacion_de_gloria.docx')
MD_OUT = os.path.join(BASE, 'raw_otra_coronacion_de_gloria.md')
JSON_OUT = os.path.join(BASE, 'book_content.json')
HTML_OUT = os.path.join(BASE, 'index.html')

# ═══════════════════════════════════════════════════════════════
# 1. DOCX → MARKDOWN (pandoc) + extracción de imágenes
# ═══════════════════════════════════════════════════════════════

def docx_to_markdown(docx_path):
    """Convierte el docx a markdown con pandoc y devuelve (md, {nombre: bytes})."""
    tmp = tempfile.mkdtemp(prefix='ocg_')
    try:
        md = subprocess.run(
            ['pandoc', docx_path, '-t', 'markdown', '--wrap=none',
             f'--extract-media={tmp}'],
            check=True, capture_output=True, text=True, encoding='utf-8'
        ).stdout
        media = {}
        media_dir = os.path.join(tmp, 'media')
        if os.path.isdir(media_dir):
            for name in os.listdir(media_dir):
                with open(os.path.join(media_dir, name), 'rb') as fh:
                    media[name] = fh.read()
        return md, media
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ═══════════════════════════════════════════════════════════════
# 2. LIMPIEZA Y NORMALIZACIÓN DEL MARKDOWN
# ═══════════════════════════════════════════════════════════════

MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif'}

def clean_markdown(raw, media):
    # 2.1 Spans de dirección RTL que pandoc añade a comillas: [X]{dir="rtl"} → X
    raw = re.sub(r'\[(.)\]\{dir="[^"]*"\}', r'\1', raw)

    # 2.2 Títulos de capítulo: en el docx usan un estilo propio que pandoc no mapea
    #     a heading, sino a un span ancla .anchor seguido del texto del título.
    #     Forma inline:    []{#id .anchor}Capítulo N: ...
    raw = re.sub(r'(?m)^\[\]\{#\S+ \.anchor\}(.+)$', r'# \1', raw)
    #     Forma en línea propia: []{#id .anchor}\n\nTítulo
    raw = re.sub(r'(?m)^\[\]\{#\S+ \.anchor\}\n\n(.+)$', r'# \1', raw)
    #     Cualquier ancla vacía remanente
    raw = re.sub(r'(?m)^\[\]\{#\S+ \.anchor\}\s*$\n?', '', raw)

    # 2.3 Eliminar el índice interno del docx (líneas "Texto [pág](#ancla)")
    raw = re.sub(r'(?m)^.*\[\d+\]\(#[^)]*\)\s*$\n?', '', raw)

    # 2.4 Incrustar imágenes como data URI (self-contained, sin carpeta media/)
    def embed_image(m):
        path = m.group(1)
        name = os.path.basename(path)
        data = media.get(name)
        if data is None:
            return ''
        ext = os.path.splitext(name)[1].lower()
        mime = MIME.get(ext, 'application/octet-stream')
        b64 = base64.b64encode(data).decode('ascii')
        return f'![](data:{mime};base64,{b64})'
    raw = re.sub(r'!\[[^\]]*\]\(([^)]+)\)(\{[^}]*\})?', embed_image, raw)

    # 2.45 Tablas grid de pandoc (+---+) → HTML (Python-Markdown no las parsea).
    #      Se promueve la primera fila a encabezado y se delega el render a pandoc.
    def convert_grid_table(m):
        lines = m.group(0).rstrip('\n').split('\n')
        borders = [i for i, ln in enumerate(lines) if ln.startswith('+')]
        if len(borders) >= 2:  # 2º borde = separador de encabezado
            b = borders[1]
            lines[b] = lines[b].replace('-', '=')
        block = '\n'.join(lines) + '\n'
        html = subprocess.run(
            ['pandoc', '-f', 'markdown', '-t', 'html'],
            input=block, capture_output=True, text=True, encoding='utf-8'
        ).stdout.strip()
        return '\n\n' + html + '\n\n'
    raw = re.sub(r'(?m)^\+[-=+]+\+\n(?:[|+].*\n)+', convert_grid_table, raw)

    # 2.5 Portada: separar el bloque del título del resto del cuerpo.
    #     El cuerpo aprovechable empieza en "**Agradecimientos**".
    agr = raw.find('**Agradecimientos**')
    if agr > 0:
        raw = raw[agr:]

    # 2.6 Convertir labels en negrita a headings reales
    raw = raw.replace('**Agradecimientos**', '## Agradecimientos', 1)
    raw = raw.replace('**Sobre el autor**',  '## Sobre el autor', 1)

    # 2.7 Normalizar indentación de listas anidadas para Python Markdown (4 espacios)
    def fix_list_indent(text):
        def replacer(m):
            n = len(m.group(1)); marker = m.group(2)
            level = (n - 1) // 3 + 1
            return ' ' * (level * 4) + marker + ' '
        return re.sub(r'(?m)^( {1,11})([-*+]|\d+\.) ', replacer, text)
    raw = fix_list_indent(raw)

    # 2.8 Tablas de una sola columna (cajas de nota) → divs callout
    def replace_callout_table(m):
        return f'\n<div class="callout">{m.group(1).strip()}</div>\n\n'
    raw = re.sub(r'(?m)^\| (.+?) \|\n\| :---+[^|\n]* \|\n(?!\|)', replace_callout_table, raw)

    # 2.9 Compactar saltos de línea múltiples
    raw = re.sub(r'\n{3,}', '\n\n', raw).strip() + '\n'
    return raw

# ═══════════════════════════════════════════════════════════════
# 3. book_content.json (estructura {style, text} desde el docx)
# ═══════════════════════════════════════════════════════════════

def build_book_content_json(docx_path):
    import docx
    doc = docx.Document(docx_path)
    style_map = {'Body A': 'normal', 'Normal': 'normal', 'List Paragraph': 'normal',
                 'Title A': 'Title', 'Title': 'Title', 'Heading': 'Heading 1'}
    out = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        name = p.style.name if p.style else 'Normal'
        if name.startswith('TOC'):
            continue
        style = style_map.get(name, name)
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
  <h1>Otra Coronación de Gloria</h1>
  <div class="divider"></div>
  <p class="sub">Con los dirigentes a la cabeza<br>o con la cabeza de los dirigentes</p>
  <p class="attr"><em>– Juan D. Perón</em></p>
  <p class="author">Maximiliano Schulkin</p>
</div>"""

# ═══════════════════════════════════════════════════════════════
# 8. MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    raw_md, media = docx_to_markdown(DOCX)
    clean = clean_markdown(raw_md, media)

    with open(MD_OUT, 'w', encoding='utf-8') as f:
        f.write(clean)

    book_json = build_book_content_json(DOCX)
    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(book_json, f, ensure_ascii=False)

    proc = md_lib.Markdown(extensions=['extra', 'sane_lists', 'toc', 'smarty'])
    body_html = proc.convert(clean)
    toc_sidebar_html = render_toc(proc.toc_tokens)

    HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Otra Coronación de Gloria — Max Schulkin</title>
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
    <div class="b-title">Otra Coronación de Gloria</div>
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

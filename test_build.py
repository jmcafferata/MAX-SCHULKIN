"""
Genera index.html interactivo a partir del markdown del libro de Max Schulkin.
Fuente: raw_otra_coronacion_de_gloria.md
"""
import re, html as html_module, markdown as md_lib

with open(r"C:\Users\JM\Desktop\MAX SCHULKIN\raw_otra_coronacion_de_gloria.md", encoding="utf-8") as f:
    raw = f.read()

raw = re.sub(r"(?m)^ {4,}(\*- Juan D\. Perón\*)\s*$", r"\n> \1", raw)
raw = raw.replace("\n**Agradecimientos**\n", "\n## Agradecimientos {#agradecimientos}\n")
raw = raw.replace("\n**Sobre el autor**\n",  "\n## Sobre el autor {#sobre-el-autor}\n")

toc_start = raw.find("[**Introducción\t")
intro_mk   = "# **Introducción** {#introducción}"
intro_pos  = raw.find(intro_mk)
if toc_start > 0 and intro_pos > toc_start:
    raw = raw[:toc_start] + raw[intro_pos:]
raw = re.sub(r"(?m)^#{1,6}\s*\n", "\n", raw)

proc = md_lib.Markdown(extensions=["extra", "sane_lists", "toc"])
body_html = proc.convert(raw)

print(f"Body HTML: {len(body_html):,} chars")
print(f"TOC tokens: {len(proc.toc_tokens)}")

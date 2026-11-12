"""Smoke test del pipeline: LaTeX → markdown → HTML."""
import re
import markdown as md_lib
import build_book


def test():
    src = '\n'.join(build_book.read_sources(build_book.LATEX_DIR))
    clean, ol_types = build_book.latex_to_markdown(build_book.LATEX_DIR)
    proc = md_lib.Markdown(extensions=['extra', 'sane_lists', 'toc', 'smarty'])
    body_html = build_book.apply_ol_types(proc.convert(clean), ol_types)  # valida las listas

    assert not re.search(r'\\[a-zA-Z]', body_html), 'comandos LaTeX sin convertir'
    assert body_html.count('<table>') == src.count(r'\begin{tabularx}'), 'tablas'
    assert body_html.count('<h1') == src.count(r'\capitulo{') + src.count(r'\chapter*{') + 1, 'capítulos'
    assert body_html.count('<li id="ref-') == src.count(r'\bibitem{'), 'referencias'
    assert body_html.count('class="cite"') == src.count(r'\cite'), 'citas'
    ids = set(re.findall(r'id="([^"]+)"', body_html))
    broken = [h for h in re.findall(r'href="#([^"]+)"', body_html) if h not in ids]
    assert not broken, f'anclas rotas: {broken[:5]}'

    print(f'H1: {body_html.count("<h1")}  H2: {body_html.count("<h2")}  '
          f'tablas: {body_html.count("<table>")}  citas: {body_html.count("class=\"cite\"")}')
    print('OK')


if __name__ == '__main__':
    test()

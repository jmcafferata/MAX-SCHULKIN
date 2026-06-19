"""Smoke test del pipeline: docx → markdown limpio → HTML."""
import os
import build_book

BASE = os.path.dirname(os.path.abspath(__file__))


def test():
    raw_md, media = build_book.docx_to_markdown(build_book.DOCX)
    clean = build_book.clean_markdown(raw_md, media)

    import markdown as md_lib
    proc = md_lib.Markdown(extensions=['extra', 'sane_lists', 'toc', 'smarty'])
    body_html = proc.convert(clean)

    assert 'dir="rtl"' not in clean, 'spans RTL no eliminados'
    assert '.anchor}' not in clean, 'anclas de pandoc no eliminadas'
    assert '<table>' in body_html, 'tablas no renderizadas'
    assert body_html.count('<h1') >= 10, 'faltan títulos de capítulo'

    print(f'Clean MD: {len(clean):,} chars')
    print(f'Body HTML: {len(body_html):,} chars')
    print(f'H1: {body_html.count("<h1")}  H2: {body_html.count("<h2")}  tablas: {body_html.count("<table>")}')
    print(f'TOC tokens: {len(proc.toc_tokens)}')
    print('OK')


if __name__ == '__main__':
    test()

#!/usr/bin/env python3
"""
Valida as páginas antes de publicar.

POR QUE EXISTE: em 10/09/2026 uma troca de <a> por <span> colocou um <div>
dentro do <span>. O HTML "fechava" todas as tags, então a checagem de
aninhamento passou — mas <span> é conteúdo de FRASE e não aceita <div>. O
navegador fecha o <span> sozinho e reposiciona o resto do bloco: a coluna de
texto do hero sumiu EM PRODUÇÃO. Contar tag aberta e fechada não basta; é
preciso checar o modelo de conteúdo.

Uso:  python3 i18n/validar.py     (sai 1 se achar problema)
"""
import glob, io, json, os, re, sys
from html.parser import HTMLParser

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAZIAS = {'br', 'img', 'input', 'meta', 'link', 'hr', 'source', 'path', 'circle',
          'rect', 'use', 'area', 'col', 'stop', 'ellipse', 'line', 'polygon', 'polyline'}
# Conteúdo de frase: não pode conter conteúdo de fluxo.
FRASE = {'span', 'em', 'strong', 'b', 'i', 'small', 'label', 'abbr', 'code', 'sub', 'sup'}
# <a> fica de fora: seu modelo é transparente e ele PODE conter <div>.
FLUXO = {'div', 'p', 'section', 'article', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4',
         'h5', 'h6', 'table', 'form', 'header', 'footer', 'nav', 'aside', 'main',
         'figure', 'blockquote', 'pre', 'hr'}


class Validador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha = []
        self.erros = []

    def handle_starttag(self, tag, attrs):
        if tag in FLUXO:
            for pai, linha in reversed(self.pilha):
                if pai == 'a':
                    break  # transparente: aceita fluxo
                if pai in FRASE:
                    self.erros.append(
                        '<%s> na linha %d está dentro de <%s> aberto na linha %d '
                        '— o navegador vai fechar o <%s> e remontar o bloco'
                        % (tag, self.getpos()[0], pai, linha, pai))
                    break
        if tag not in VAZIAS:
            self.pilha.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VAZIAS:
            return
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                return
        self.erros.append('</%s> na linha %d fecha algo que não foi aberto'
                          % (tag, self.getpos()[0]))


def main():
    os.chdir(RAIZ)
    paginas = sorted(glob.glob('*.html') + glob.glob('*/index.html'))
    problemas = 0

    for f in paginas:
        html = io.open(f, encoding='utf-8').read()
        v = Validador()
        v.feed(html)
        erros = list(v.erros)
        if v.pilha:
            erros.append('não fechadas: %s' % ', '.join(t for t, _ in v.pilha[:5]))

        # canonical e title únicos
        for nome, padrao in (('canonical', r'rel="canonical"'), ('<title>', r'<title>')):
            n = len(re.findall(padrao, html))
            if n != 1:
                erros.append('%s aparece %d vez(es), deveria ser 1' % (nome, n))

        # JSON-LD precisa ser JSON válido
        for bloco in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                json.loads(bloco)
            except ValueError as e:
                erros.append('JSON-LD inválido: %s' % e)

        print('  %-26s %s' % (f, 'ok' if not erros else 'PROBLEMA'))
        for e in erros:
            print('       %s' % e)
        problemas += len(erros)

    print('\n  %d páginas · %s' % (len(paginas),
          'tudo certo' if not problemas else '%d problema(s)' % problemas))
    sys.exit(1 if problemas else 0)


if __name__ == '__main__':
    main()

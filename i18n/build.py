#!/usr/bin/env python3
"""
Gera /es/ e /en/ a partir das páginas em português.

POR QUE ASSIM, e não HTML duplicado à mão:
o site é HTML estático, sem build. Manter três cópias de index.html
sincronizadas na unha garante que uma hora as três divergem — alguém corrige um
preço em pt e esquece o es. Aqui o português é a ÚNICA fonte de conteúdo e
estrutura; o que existe por idioma é só um dicionário de texto, revisável.

A substituição acontece SOMENTE em nós de texto (o que está entre > e <) e em
atributos declarados em ATTRS. Nunca em URL, classe, id ou nome de arquivo —
foi por isso que não se usou "procurar e trocar" no HTML inteiro.

Uso:
    python3 i18n/build.py            # gera es e en
    python3 i18n/build.py --check    # só relata o que falta traduzir
"""
import io, json, os, re, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDIOMAS = {
    'es': {'lang': 'es',    'og': 'es_ES', 'nome': 'Español'},
    'en': {'lang': 'en-US', 'og': 'en_US', 'nome': 'English'},
}
PAGINAS = ['index.html']
BASE = 'https://www.rellav.com.br'

# Atributos cujo VALOR é texto visível ou indexável.
ATTRS = ('content', 'alt', 'title', 'aria-label', 'placeholder')

# Trechos que NÃO se traduzem: marca, nomes próprios, termos técnicos.
NAO_TRADUZIR = {
    'Rellav', 'WhatsApp', 'TOTVS', 'TOTVS / Protheus', 'Sankhya', 'Omie', 'Bling',
    'SAP Business One', 'Tiny ERP', 'WinThor', 'ERP', 'LGPD', 'App Store',
    'Google Play', 'GET IT ON', 'contato@rellav.com.br', 'CNPJ', 'SKU', 'API',
    'SLA', 'Starter', 'Enterprise', 'FAQ', 'Curva A, B e C', 'Docs',
    'SANKHYA', 'OMIE', 'BLING', 'Rellav ✦', 'Rellav App', 'offline-first',
    # valores técnicos de meta tag — não são texto visível
    'website', 'summary_large_image', 'pt_BR', 'es_ES', 'en_US',
    'width=device-width, initial-scale=1.0',
    # nomes próprios das lojas-exemplo e seus domínios
    'Vovó Crocante', 'Loja Vovó Crocante', 'Atacado Boa Praça', 'Nature Alimentos',
    # rótulos do seletor de idioma: são códigos, iguais em qualquer idioma
    'PT', 'ES', 'EN',
}

# Padrões que nunca são texto traduzível.
PULAR = re.compile(r'^[\w.-]+\.(app|com|com\.br|dev)$|^G-[A-Z0-9]+$|^\d[\d.,]*$')

def carregar(idioma):
    p = os.path.join(RAIZ, 'i18n', 'strings.%s.json' % idioma)
    with io.open(p, encoding='utf-8') as fh:
        return json.load(fh)

def traduzir_html(html, dic, cfg, pagina):
    faltando = []

    def troca(txt):
        bruto = txt.strip()
        if not bruto or bruto in NAO_TRADUZIR or PULAR.match(bruto):
            return txt
        if not re.search(r'[A-Za-zÀ-ÿ]', bruto):
            return txt
        if bruto in dic:
            return txt.replace(bruto, dic[bruto], 1)
        faltando.append(bruto)
        return txt

    # 1) nós de texto — tudo entre > e <, fora de script/style
    partes = re.split(r'(<script\b.*?</script>|<style\b.*?</style>)', html, flags=re.S | re.I)
    for i, parte in enumerate(partes):
        if parte.lower().startswith(('<script', '<style')):
            continue
        partes[i] = re.sub(r'(?<=>)([^<>]+)(?=<)', lambda m: troca(m.group(1)), parte)
    html = ''.join(partes)

    # 2) atributos indexáveis
    def attr(m):
        nome, valor = m.group(1), m.group(2)
        if nome not in ATTRS:
            return m.group(0)
        if valor.startswith(('http', '/', '#', 'data:', 'mailto:')):
            return m.group(0)
        return '%s="%s"' % (nome, troca(valor))
    html = re.sub(r'([a-zA-Z-]+)="([^"]*)"', attr, html)

    # 3) idioma do documento
    html = re.sub(r'<html lang="[^"]*"', '<html lang="%s"' % cfg['lang'], html, count=1)
    html = re.sub(r'<meta property="og:locale" content="[^"]*">',
                  '<meta property="og:locale" content="%s">' % cfg['og'], html, count=1)
    return html, faltando

def traduzir_jsonld(html, dic, cfg):
    """
    Traduz os blocos JSON-LD.

    POR QUE PRECISA: a substituição de texto pula <script> de propósito (mexer
    em JavaScript por regex quebra código). Só que o JSON-LD NÃO é código — é
    conteúdo, e o Google exige que o dado estruturado corresponda ao que está
    visível na página. Sem este passo, /es/ e /en/ saíam com FAQPage em
    português: nenhum rich result, e divergência entre schema e página.
    """
    import json as _json

    def anda(v):
        if isinstance(v, str):
            return dic.get(v, v)
        if isinstance(v, list):
            return [anda(x) for x in v]
        if isinstance(v, dict):
            return {k: (v[k] if k in ('@context', '@type', '@id', 'url', 'logo',
                                      'telephone', 'operatingSystem')
                        else anda(v[k])) for k in v}
        return v

    def troca_bloco(m):
        try:
            dado = _json.loads(m.group(1))
        except ValueError:
            return m.group(0)
        dado = anda(dado)
        if isinstance(dado, dict) and dado.get('@type') in ('SoftwareApplication', 'FAQPage'):
            dado['inLanguage'] = cfg['lang']
        return '<script type="application/ld+json">%s</script>' % _json.dumps(
            dado, ensure_ascii=False, separators=(',', ':'))

    return re.sub(r'<script type="application/ld\+json">(.*?)</script>',
                  troca_bloco, html, flags=re.S)

def canonical_e_hreflang(html, idioma, pagina):
    """Canonical do próprio idioma + hreflang recíproco entre as três versões."""
    slug = '' if pagina == 'index.html' else pagina.replace('/index.html', '')
    def url(pref):
        # trailingSlash:false no vercel.json: a URL canônica NÃO tem barra final
        # (exceto a raiz). Apontar para /es/ faria canonical e hreflang mirarem
        # uma URL que redireciona — o mesmo erro que havia com o www.
        caminho = ('/' + pref if pref else '') + ('/' + slug if slug else '')
        return BASE + (caminho or '/')
    proprio = url(idioma)
    html = re.sub(r'<link rel="canonical" href="[^"]*">',
                  '<link rel="canonical" href="%s">' % proprio, html, count=1)
    # O index.html em português JÁ traz o próprio bloco de alternates. Sem
    # remover, a página gerada sai com DOIS conjuntos de hreflang — e hreflang
    # duplicado ou conflitante é descartado pelo Google.
    html = re.sub(r'\s*<link rel="alternate" hreflang="[^"]*" href="[^"]*">', '', html)
    html = re.sub(r'\n\s*<!-- hreflang recíproco:.*?-->', '', html, flags=re.S)
    alt = (
        '\n  <!-- hreflang recíproco: cada versão aponta para TODAS, inclusive para si.\n'
        '       Sem a auto-referência o Google descarta o conjunto. x-default vai para\n'
        '       o português, que é o mercado principal. -->\n'
        '  <link rel="alternate" hreflang="pt-BR" href="%s">\n'
        '  <link rel="alternate" hreflang="es" href="%s">\n'
        '  <link rel="alternate" hreflang="en-US" href="%s">\n'
        '  <link rel="alternate" hreflang="x-default" href="%s">\n'
    ) % (url(''), url('es'), url('en'), url(''))
    return html.replace('</head>', alt + '</head>', 1)

# Páginas internas que ainda existem só em português.
# LEGAIS continuam linkadas (privacidade, termos e exclusão de conta são
# exigências — a de exclusão é requisito da Google Play) e vão marcadas com
# hreflang/lang, para que navegador e buscador saibam que o destino muda de
# idioma. As de MARKETING saem do menu: mandar quem lê espanhol para uma
# página em português é pior do que não oferecer o link, e ainda sinaliza
# conteúdo fora do idioma declarado.
SO_EM_PT_LEGAIS   = ('/privacidade', '/termos', '/excluir-conta')
SO_EM_PT_MARKETING = ('/industrias', '/distribuidoras', '/representantes',
                      '/integracoes', '/docs')

def ajustar_links(html, idioma):
    for destino in SO_EM_PT_LEGAIS:
        html = html.replace('href="%s"' % destino,
                            'href="%s" hreflang="pt-BR" lang="pt-BR"' % destino)
    # tira do menu suspenso e da navegação os itens que não existem no idioma
    for destino in SO_EM_PT_MARKETING:
        html = re.sub(r'<li><a href="%s"[^>]*>.*?</a></li>' % re.escape(destino),
                      '', html, flags=re.S)
        html = re.sub(r'<a href="%s"[^>]*class="ndm-item"[^>]*>.*?</a>' % re.escape(destino),
                      '', html, flags=re.S)
        html = re.sub(r'<a href="%s"[^>]*class="foot-link"[^>]*>.*?</a>' % re.escape(destino),
                      '', html, flags=re.S)
        # rodapé inferior: links com style inline, separados por " · "
        html = re.sub(r'\s*·?\s*<a href="%s"[^>]*style="[^"]*"[^>]*>[^<]*</a>' % re.escape(destino),
                      '', html)
    # menu suspenso que ficou vazio some junto
    html = re.sub(r'<li class="nav-drop">\s*<button[^>]*>.*?</button>\s*'
                  r'<div class="nav-drop-menu">\s*</div>\s*</li>', '', html, flags=re.S)
    # separadores que ficaram sem link dos dois lados
    html = re.sub(r'(reservados\.|reserved\.)\s*·\s*(?=</p>)', r'\\1', html)
    html = re.sub(r'·\s*·', '·', html)
    return html

def seletor_idioma(html, idioma):
    """Troca de idioma no topo. Cada item é um link real e rastreável."""
    itens = []
    for cod, rotulo, href in (('pt', 'PT', '/'), ('es', 'ES', '/es'), ('en', 'EN', '/en')):
        atual = ' aria-current="true"' if cod == idioma else ''
        itens.append('<a href="%s" hreflang="%s"%s>%s</a>' % (
            href, {'pt': 'pt-BR', 'es': 'es', 'en': 'en-US'}[cod], atual, rotulo))
    bloco = ('<div class="lang-switch" role="group" aria-label="Idioma">%s</div>'
             % ''.join(itens))
    css = ('<style>.lang-switch{display:inline-flex;gap:2px;margin-left:14px;'
           'border:1px solid rgba(0,0,0,.12);border-radius:6px;overflow:hidden}'
           '.lang-switch a{padding:4px 9px;font-size:.72rem;font-weight:700;'
           'letter-spacing:.04em;color:#666;text-decoration:none;line-height:1.4}'
           '.lang-switch a[aria-current]{background:#87BD24;color:#fff}'
           '.lang-switch a:not([aria-current]):hover{background:rgba(0,0,0,.05);color:#111}'
           '</style>')
    html = html.replace('</head>', css + '</head>', 1)
    # O português já traz o seletor no fonte. Aqui ele é SUBSTITUÍDO (para o
    # aria-current mudar de idioma), nunca duplicado.
    # São DOIS seletores: um no topo (.lang-switch) e um no rodapé (.lang-foot),
    # este último sempre visível porque o do topo some abaixo de 1280px.
    # Só o do RODAPÉ. No menu não cabe: o .nav-inner tem max-width fixo de
    # 1160px e já está no limite com logo, seis itens, "Entrar" e o botão.
    rodape = bloco.replace('class="lang-switch"', 'class="lang-foot"')
    return re.sub(r'<div class="lang-foot".*?</div>', rodape, html, count=1, flags=re.S)

def main():
    checar = '--check' in sys.argv
    total_falta = 0
    for idioma, cfg in IDIOMAS.items():
        dic = carregar(idioma)
        for pagina in PAGINAS:
            origem = os.path.join(RAIZ, pagina)
            with io.open(origem, encoding='utf-8') as fh:
                html = fh.read()
            saida_html, faltando = traduzir_html(html, dic, cfg, pagina)
            saida_html = traduzir_jsonld(saida_html, dic, cfg)
            saida_html = canonical_e_hreflang(saida_html, idioma, pagina)
            saida_html = ajustar_links(saida_html, idioma)
            saida_html = seletor_idioma(saida_html, idioma)
            unicos = sorted(set(faltando))
            total_falta += len(unicos)
            print('  %s/%s  traduzidas=%d  faltando=%d' % (idioma, pagina, len(dic), len(unicos)))
            for f in unicos[:10]:
                print('      falta: %s' % f[:90])
            if checar:
                continue
            destino = os.path.join(RAIZ, idioma, pagina)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with io.open(destino, 'w', encoding='utf-8') as fh:
                fh.write(saida_html)
    if not checar:
        print('\n  gerado. Rode de novo sempre que o português mudar.')
    sys.exit(1 if total_falta else 0)

if __name__ == '__main__':
    main()

"""PLN baseado em regras: limpeza, tokens, stopwords e classificacao tematica."""
import re
import unicodedata
from collections import Counter
from html.parser import HTMLParser

ALGORITHM = 'titulo-regras-pt-v1'
STOPWORDS = frozenset('a o as os de da do das dos e em para por com um uma uns umas '
                     'no na nos nas ao aos que se seu sua seus suas modelo kit'.split())
CATEGORIES = {
    'teclado': {'teclado','teclados','keyboard','keyboards'},
    'mouse': {'mouse','mouses','mice'},
    'mousepad': {'mousepad','mousepads'},
    'headset': {'headset','headsets','headphone','headphones','fone','fones'},
    'monitor': {'monitor','monitores'},
    'webcam': {'webcam','webcams'},
    'microfone': {'microfone','microfones','microphone'},
    'cadeira': {'cadeira','cadeiras'},
    'controle': {'controle','controles','joystick','gamepad'},
    'armazenamento': {'ssd','hd','hdd','pendrive','pendrives'},
    'memoria': {'memoria','memorias','ram','ddr4','ddr5'},
    'roteador': {'roteador','roteadores','router'},
    'impressora': {'impressora','impressoras'},
    'notebook': {'notebook','notebooks','laptop'},
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.ignored += 1
        self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.ignored:
            self.ignored -= 1
        self.parts.append(' ')

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def tokens(text):
    parser = PlainText()
    parser.feed(text)
    plain = unicodedata.normalize('NFKD', ' '.join(parser.parts).casefold())
    plain = ''.join(c for c in plain if not unicodedata.combining(c))
    words = re.findall(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', plain)
    return [w for w in words if w not in STOPWORDS and (len(w) > 1 or w.isdigit())]


def analyze(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise ValueError('Titulo deve ter entre 1 e 500 caracteres')
    words = tokens(text)
    vocabulary = set(words)
    matched = [name for name, aliases in CATEGORIES.items() if vocabulary & aliases]
    if 'mousepad' in matched or ('mouse' in vocabulary and 'pad' in vocabulary):
        standalone_mouse = any(word in CATEGORIES['mouse'] and
            not (index+1 < len(words) and words[index+1] == 'pad')
            for index, word in enumerate(words))
        if not standalone_mouse:
            matched = [name for name in matched if name != 'mouse']
        if 'mousepad' not in matched:
            matched.append('mousepad')
    matched.sort()
    return {'normalized_text':' '.join(words), 'tokens':words,
            'keywords':[word for word, _ in Counter(words).most_common(8)],
            'category':matched[0] if len(matched) == 1 else 'multicategoria' if matched else 'outros',
            'matched_categories':matched, 'algorithm':ALGORITHM}


def query_tokens(text):
    if not isinstance(text, str) or len(text) > 80:
        raise ValueError('Consulta excede 80 caracteres')
    return list(dict.fromkeys(tokens(text)))[:8]

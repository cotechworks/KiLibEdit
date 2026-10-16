"""Lossless, span-based editing of KiCad symbol property values."""
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
from datetime import datetime


@dataclass
class Node:
    start: int
    end: int
    value: str = ''
    children: object = None


def parse(text):
    roots, stack = [], []
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace() or c == '\ufeff':
            i += 1
            continue
        if c == ';':
            end = text.find('\n', i)
            i = len(text) if end < 0 else end + 1
            continue
        target = stack[-1].children if stack else roots
        if c == '(':
            n = Node(i, 0, children=[])
            target.append(n)
            stack.append(n)
            i += 1
        elif c == ')':
            if not stack:
                raise ValueError('対応する開き括弧がありません')
            stack.pop().end = i + 1
            i += 1
        else:
            start = i
            value = ''
            if c == '"':
                i += 1
                while i < len(text) and text[i] != '"':
                    if text[i] == '\\':
                        i += 1
                        if i >= len(text):
                            raise ValueError('文字列のエスケープが不完全です')
                        value += {'n': '\n', 'r': '\r', 't': '\t'}.get(text[i], text[i])
                    else:
                        value += text[i]
                    i += 1
                if i >= len(text):
                    raise ValueError('文字列が閉じられていません')
                i += 1
            else:
                while i < len(text) and not text[i].isspace() and text[i] not in '();':
                    i += 1
                value = text[start:i]
            target.append(Node(start, i, value))
    if stack or len(roots) != 1 or roots[0].children is None:
        raise ValueError('S式の構造が不正です')
    return roots[0]


def tag(node):
    return node.children[0].value if node.children else ''


def quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"'


class Library:
    def __init__(self, text):
        self.text = text
        self.root = parse(text)
        if tag(self.root) != 'kicad_symbol_lib':
            raise ValueError('KiCadシンボルライブラリではありません')
        self.symbols = [n for n in self.root.children if tag(n) == 'symbol']
        self.names, self.properties, self.parents = [], [], []
        for symbol in self.symbols:
            self.names.append(symbol.children[1].value)
            props = {}
            parent = ''
            for n in symbol.children:
                if tag(n) == 'property':
                    if len(n.children) < 3:
                        raise ValueError('プロパティの構造が不正です')
                    offset = 2 if text[n.children[1].start:n.children[1].end] == 'private' else 1
                    if len(n.children) <= offset + 1:
                        raise ValueError('プロパティの構造が不正です')
                    key = n.children[offset].value
                    if key in props:
                        raise ValueError('プロパティ名が重複しています: ' + key)
                    props[key] = n.children[offset + 1]
                elif tag(n) == 'extends':
                    parent = n.children[1].value
            self.properties.append(props)
            self.parents.append(parent)
        if len(set(self.names)) != len(self.names):
            raise ValueError('シンボル名が重複しています')
        self.columns = list(dict.fromkeys(['Reference', 'Value', 'Footprint', 'Datasheet', 'Description', 'ki_keywords'] + [k for p in self.properties for k in p]))
        self.changes = {}

    def get(self, row, key):
        if (row, key) in self.changes:
            return self.changes[row, key]
        n = self.properties[row].get(key)
        return n.value if n else ''

    def set(self, row, key, value):
        original = self.properties[row].get(key)
        if value == (original.value if original else ''):
            self.changes.pop((row, key), None)
        else:
            self.changes[row, key] = value

    def render(self):
        edits, additions = [], {}
        for (row, key), value in self.changes.items():
            n = self.properties[row].get(key)
            if n:
                edits.append((n.start, n.end, quote(value)))
            else:
                additions.setdefault(row, []).append(f'\n\t\t(property {quote(key)} {quote(value)} (at 0 0 0) (hide yes) (effects (font (size 1.27 1.27))))')
        for row, lines in additions.items():
            pos = self.symbols[row].children[1].end
            edits.append((pos, pos, ''.join(lines)))
        if edits:
            generator = next((n for n in self.root.children if tag(n) == 'generator'), None)
            if generator:
                n = generator.children[1]
                edits.append((n.start, n.end, 'kilibedit'))
        text = self.text
        for start, end, replacement in sorted(edits, reverse=True):
            text = text[:start] + replacement + text[end:]
        Library(text)
        return text


def atomic_save(path, text, expected=None):
    path = Path(path)
    if expected is not None and path.read_bytes() != expected:
        raise ValueError('読み込み後にファイルが変更されています。別名で保存してください。')
    data = text.encode('utf-8')
    backup = None
    if path.exists():
        backup = path.with_name(path.name + '.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak')
        with backup.open('xb') as f:
            f.write(path.read_bytes())
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup

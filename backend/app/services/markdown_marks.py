"""One lossless interpretation of authored marks; never rewrites Markdown.

Formatting is transparent, code/HTML/images are barriers, and soft/hard breaks
remain physical line boundaries. Region is the latest explicit @l, including
across headings; a new @l replaces it. Ordinary headings never guess a city.
"""
import re
import uuid
from dataclasses import dataclass
from markdown_it import MarkdownIt
from fastapi import HTTPException

# Legacy spaced names retain their original whole-segment interpretation.
# Compact names stop at whitespace/@; brackets give an explicit end boundary.
MARK = re.compile(r'(?:(?<![\w@])|(?<=[\u3400-\u9fff]))@([lfshtcp])(?:\[([^\]\n\x00]+)\]|([^\S\n]+[^\n@\x00]+)|([^\s@\[\]{}\x00]+))(?:[ \t]*\{#place:[^}\n]*\})?')
IDENTITY = re.compile(r'\s*\{#place:([0-9a-f-]{36})\}\s*$')


def marks(text):
    result = []
    for match in MARK.finditer(text):
        # A URL remains literal even when its path contains a compact mark.
        if re.search(r'\S*(?:https?://|www\.|mailto:)\S*$', text[:match.start()], re.I):
            continue
        name = next(group for group in (match[2], match[3], match[4]) if group is not None).strip()
        identity = IDENTITY.search(match[0])
        pid = None
        if '{#place:' in match[0] and not identity:
            raise HTTPException(422, '地点标记身份格式无效，请重新选择已有地点')
        if identity:
            try:
                pid = str(uuid.UUID(identity[1]))
            except ValueError:
                raise HTTPException(422, '地点标记 UUID 无效') from None
            name = IDENTITY.sub('',name).strip()
        if not name or len(name) > 200:
            raise HTTPException(422, '地点标记名称需为1至200字')
        result.append({'kind': match[1], 'name': name, 'place_id': pid})
    return result


@dataclass
class Line:
    number: int                 # 1-based physical source line
    text: str                   # formatting-free text; unsupported nodes are barriers
    path: tuple                 # enclosing list item identities
    marks: list


@dataclass
class Document:
    lines: list
    marks: list

    def food(self, start, end=None, *, bounded=False):
        from .itinerary import DATES, resolve_day
        out = []
        owners = {}
        day = None
        for line in self.lines:
            text = line.text
            if len(line.path) <= 1:
                # UUID digits cannot act as a date. Same date rules as itinerary.
                match = DATES.search(re.sub(r'\{#place:[a-f0-9-]{36}\}', '', text))
                if match:
                    try:
                        day = resolve_day(match, start, end, bounded=bounded)
                    except (ValueError, OverflowError):
                        day = None
            current = []
            for mark in line.marks:
                if mark['kind'] == 'f':
                    row = {'mark': mark, 'region': mark['region'], 'day': day, 'description': []}
                    out.append(row)
                    current.append(row)
            if current and line.path:
                owners.setdefault(line.path, []).extend(current)
            elif not line.marks and line.path:
                parent = owners.get(line.path) or next((owners[p] for n in range(len(line.path)-1, 0, -1)
                                                       if (p := line.path[:n]) in owners), [])
                for row in parent:
                    row['description'].append(text.replace('\x00', ''))
        return out


def parse(body):
    lines = []
    found = []
    path = []
    item = 0
    region = legacy_region = ''
    physical = body.splitlines()
    offsets = []
    offset = 0
    for raw in body.splitlines(keepends=True):
        offsets.append(offset)
        offset += len(raw)
    media_lines = set()
    for i, raw in enumerate(physical):
        if raw in (':::lj-media-v1',':::lj-entry-v1') and i + 2 < len(physical) and physical[i+2] == ':::':
            media_lines.update((i, i+1, i+2))
    from .body_media import narrative_parser
    for token in narrative_parser().parse(body):
        if token.type == 'list_item_open':
            item += 1
            path.append(item)
        elif token.type == 'list_item_close':
            path.pop()
        elif token.type == 'heading_open':
            # Used ONLY to locate an old food row, not to infer current identity.
            legacy_region = ''
        elif token.type == 'inline' and token.map:
            text = ''.join(c.content if c.type == 'text' else '\n' if c.type in ('softbreak', 'hardbreak')
                           else '\x00' if c.type in ('code_inline', 'html_inline', 'image') else ''
                           for c in token.children or [])
            for index, value in enumerate(text.split('\n')):
                number = token.map[0] + index
                if number in media_lines:
                    continue
                # Never silently truncate a name at an unsupported inline node.
                # Code containing a whole mark is inert; code inside a name is
                # ambiguous and must be corrected explicitly by the author.
                for segment in value.split('\x00')[:-1]:
                    candidate=next(iter(reversed(list(MARK.finditer(segment)))),None)
                    compact_incomplete=bool(candidate and candidate[4] and candidate.end()==len(segment))
                    if re.search(r'(?<![\w@])@[lfshtcp][^\S\n]+[^@\n]*$', segment) or compact_incomplete:
                        raise HTTPException(422, '地点标记名称不能混入代码、HTML或图片；请使用普通文字、加粗或斜体')
                line_marks = marks(value)
                column = 0
                for mark in line_marks:
                    raw = physical[number] if number < len(physical) else ''
                    column = raw.find('@' + mark['kind'], column)
                    column = max(column, 0)
                    mark.update(region='' if mark['kind'] == 'l' else region,
                                legacy_region='' if mark['kind'] == 'l' else legacy_region,
                                line=number+1, column=column+1,
                                offset=(offsets[number] if number < len(offsets) else len(body))+column)
                    column += 2
                    if mark['kind'] == 'l':
                        region = legacy_region = mark['name']
                lines.append(Line(number+1, value, tuple(path), line_marks))
                found.extend(line_marks)
    return Document(lines, found)


def document(db, record):
    """Session-local reuse across one save; no process-global private-text cache."""
    cache = db.info.setdefault('markdown_marks', {})
    old = cache.get(record.id)
    if old is None or old[0] != record.body:
        old = cache[record.id] = (record.body, parse(record.body))
    return old[1]

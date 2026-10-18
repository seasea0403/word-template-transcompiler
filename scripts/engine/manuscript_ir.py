"""Lossless Pandoc AST intake and object inventory for a template writer.

The AST is retained verbatim. Semantic inventory is a second view, not a
replacement parser; tables, math, notes and inline markup are never flattened
for authoring. Image resources are restricted to the manuscript directory.
"""
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(node):
    if isinstance(node, list):
        return ''.join(text(v) for v in node)
    if not isinstance(node, dict):
        return ''
    kind = node.get('t')
    if kind == 'Str': return node['c']
    if kind in ('Space', 'SoftBreak', 'LineBreak'): return ' '
    if kind == 'Math': return node['c'][1]
    if kind == 'Note': return ''  # note body is a separate object
    if kind in ('Link', 'Image'): return text(node['c'][1])
    if kind == 'Header': return text(node['c'][2])
    return text(node.get('c', []))


def walk(node, pointer=''):
    if isinstance(node, dict):
        yield pointer, node
        for key, value in node.items():
            yield from walk(value, pointer + '/' + key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, pointer + '/' + str(index))


def image_resource(target, manuscript):
    url = urlsplit(target)
    if url.scheme or url.netloc or url.query or url.fragment:
        raise ValueError('Only relative local image paths are supported: ' + target)
    relative = Path(unquote(url.path))
    if relative.is_absolute(): raise ValueError('Image path must be relative')
    root = manuscript.resolve().parent
    path = (root / relative).resolve()
    if not path.is_relative_to(root): raise ValueError('Image escapes input directory')
    if not path.is_file(): raise ValueError('Image is missing: ' + target)
    return {'target': target, 'path': str(path), 'bytes': path.stat().st_size,
            'sha256': sha(path)}


def inventory(ast, manuscript):
    objects, assets, anchors, counts = [], [], {}, Counter()
    citation_mentions, bibliography = [], {}
    section, chapter, chapter_level = 'frontmatter', 0, None
    title = text(ast.get('meta', {}).get('title_zh', {}))
    for index, block in enumerate(ast['blocks']):
        pointer = '/blocks/' + str(index)
        kind = block['t']
        if kind == 'Header':
            level, attr, inline = block['c']; label = text(inline)
            if title and label == title: section = 'title'
            elif re.fullmatch(r'(中文)?摘要', label): section = 'abstract_zh'
            elif label.casefold() == 'abstract': section = 'abstract_en'
            elif label in ('参考文献', 'References', 'Bibliography'): section = 'references'
            elif chapter_level is None or level <= chapter_level:
                chapter_level = level; chapter += 1; section = 'body'
        role = section
        if kind == 'Header' and section == 'body':
            role = {0: 'chapter', 1: 'section', 2: 'subsection'}.get(
                block['c'][0] - chapter_level, 'unsupported_heading_depth')
        if kind == 'Para' and section.startswith('abstract'):
            if re.match(r'^(关键词|key\s*words)\s*[:：]', text(block), re.I):
                role = section.replace('abstract', 'keywords')
        if kind == 'Table': role = 'table'
        if kind == 'Figure': role = 'figure'
        if kind == 'Para' and re.match(r'^表\s*\d+[.\-]\d+\s', text(block)):
            role = 'table_caption'
        if section == 'references' and kind == 'Para':
            match = re.match(r'^\[(\d+)\]\s*(.*)', text(block), re.S)
            if not match: raise ValueError('Unrecognized bibliography entry')
            ident = match.group(1)
            if ident in bibliography: raise ValueError('Duplicate reference ID')
            bibliography[ident] = {'pointer': pointer, 'original_text': text(block)}
            role = 'bibliography_entry'
        objects.append({'id': 'block-' + str(index), 'pointer': pointer,
                        'kind': kind, 'role': role, 'chapter': chapter,
                        'text_for_review_only': text(block), 'ast': block})
        for subpointer, node in walk(block, pointer):
            t = node.get('t')
            if t: counts[t] += 1
            if t in ('RawBlock', 'RawInline'):
                raise ValueError('Raw markup requires an explicit adapter')
            if t in ('Header', 'Div', 'Figure', 'Table', 'Span'):
                attr = node['c'][1] if t == 'Header' else node['c'][0]
                if attr[0]:
                    if attr[0] in anchors: raise ValueError('Duplicate anchor')
                    anchors[attr[0]] = subpointer
            if t == 'Image': assets.append(image_resource(node['c'][2][0], manuscript))
            if t in ('Math', 'Note', 'Image', 'Link', 'Table'):
                objects.append({'id': 'object-' + str(len(objects)),
                                'pointer': subpointer, 'kind': t,
                                'role': 'equation' if t == 'Math' and node['c'][0]['t'] == 'DisplayMath' else
                                        'inline_math' if t == 'Math' else t.lower(),
                                'chapter': chapter, 'ast': node})
        if section != 'references':
            # Citations in this manuscript are literal bracketed numbers, not
            # Pandoc Cite nodes. Keep source AST and display separately.
            for match in re.finditer(r'\[(\d+)\]', text(block)):
                citation_mentions.append({'reference_id': match.group(1),
                                          'pointer': pointer,
                                          'text_view_offset': match.start()})
    for obj in objects:
        if obj['kind'] == 'Link':
            target = obj['ast']['c'][2][0]
            if target.startswith('#') and target[1:] not in anchors:
                raise ValueError('Dangling manuscript link: ' + target)
    missing = {c['reference_id'] for c in citation_mentions} - set(bibliography)
    if missing: raise ValueError('Missing bibliography IDs: ' + str(sorted(missing)))
    return {'objects': objects, 'assets': assets, 'anchors': anchors,
            'citation_mentions': citation_mentions, 'bibliography': bibliography,
            'counts': dict(counts), 'chapter_count': chapter}


def parse(manuscript, pandoc):
    before = sha(manuscript)
    command = [str(pandoc), str(manuscript.resolve()), '-f',
               'markdown+tex_math_single_backslash', '-t', 'json']
    result = subprocess.run(command, capture_output=True, check=True)
    ast = json.loads(result.stdout)
    result_inventory = inventory(ast, manuscript)
    if sha(manuscript) != before: raise ValueError('Manuscript changed during parsing')
    version = subprocess.run([str(pandoc), '--version'], capture_output=True,
                             text=True, check=True).stdout.splitlines()[0]
    return {'schema_version': 'manuscript-ir/1', 'source': str(manuscript.resolve()),
            'source_sha256': before, 'parser_version': version, 'command': command,
            'pandoc_api_version': ast['pandoc-api-version'], 'ast': ast,
            'metadata_text_view': {k: text(v) for k, v in ast['meta'].items()},
            **result_inventory,
            'limitations': ['AST pointers are not original Markdown character offsets',
                            'Inventory text is for review, never a replacement for source AST',
                            'Only literal single-number citations are indexed currently']}

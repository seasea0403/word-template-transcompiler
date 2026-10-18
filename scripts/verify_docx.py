"""Read-only DOCX structure checks; no inferred semantic or visual approval."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import unquote, urlsplit
import zipfile
from lxml import etree as E

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_package(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate package parts')
        for name in names:
            if '\\' in name or name.startswith('/') or ':' in name or '..' in PurePosixPath(name).parts:
                raise ValueError('Unsafe package part: ' + name)
        return {n: archive.read(n) for n in names if not n.endswith('/')}


def source_part(rels_part):
    if rels_part == '_rels/.rels':
        return ''
    directory, name = rels_part.rsplit('/_rels/', 1)
    return directory + '/' + name[:-5]


def audit(document, template=None, expected=None):
    expected = expected or {}
    errors, checks, external = [], [], []
    before = sha(document)
    def check(name, ok, detail=None):
        checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
        if not ok:
            errors.append({'check': name, 'detail': detail})
    parts = read_package(document)
    roots = {}
    for name, data in parts.items():
        if name.endswith(('.xml', '.rels')):
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ValueError('DTD/entity declarations unsupported: ' + name)
            roots[name] = E.fromstring(data, E.XMLParser(resolve_entities=False, no_network=True))
    check('required_parts', all(n in parts for n in
                               ('[Content_Types].xml', '_rels/.rels', 'word/document.xml')))
    if 'word/document.xml' not in roots:
        return {'passed': False, 'counts': {}, 'checks': checks, 'errors': errors,
                'limitations': ['Not a complete Word package']}
    rel_maps = {}
    for name, root in roots.items():
        if not name.endswith('.rels'):
            continue
        origin = source_part(name)
        rels = list(root)
        ids = [n.get('Id') for n in rels]
        check('relationship_ids:' + name, None not in ids and len(ids) == len(set(ids)))
        rel_maps[origin] = {n.get('Id'): n for n in rels}
        for rel in rels:
            target = rel.get('Target', '')
            if rel.get('TargetMode') == 'External':
                external.append({'part': origin, 'id': rel.get('Id'), 'type': rel.get('Type'),
                                 'target': target})
                continue
            url = urlsplit(target)
            decoded = unquote(url.path)
            resolved = posixpath.normpath(decoded.lstrip('/') if decoded.startswith('/') else
                                         posixpath.join(posixpath.dirname(origin), decoded))
            check('relationship_target:' + name + ':' + str(rel.get('Id')),
                  bool(target) and not url.scheme and not url.netloc
                  and not resolved.startswith('../') and resolved in parts, resolved)
    stories = {n: r for n, r in roots.items() if n.startswith('word/') and not n.endswith('.rels')}
    bookmark_names, instructions = [], []
    hidden_tc = 0
    for name, root in stories.items():
        starts = list(root.iter(W+'bookmarkStart'))
        ends = list(root.iter(W+'bookmarkEnd'))
        bookmark_names.extend(n.get(W+'name') for n in starts)
        check('bookmark_pairs:' + name,
              Counter(n.get(W+'id') for n in starts) == Counter(n.get(W+'id') for n in ends))
        check('bookmark_ids_unique:' + name,
              len(starts) == len({n.get(W+'id') for n in starts}))
        stack = []
        for node in root.iter():
            if node.tag == W+'fldSimple':
                instructions.append(node.get(W+'instr', ''))
            elif node.tag == W+'fldChar':
                kind = node.get(W+'fldCharType')
                if kind == 'begin':
                    stack.append([])
                elif kind == 'end':
                    check('field_end:' + name, bool(stack))
                    if stack:
                        instructions.append(''.join(stack.pop()))
                elif kind == 'separate':
                    check('field_separator:' + name, bool(stack))
            elif node.tag == W+'instrText':
                check('field_instruction:' + name, bool(stack), (node.text or '')[:80])
                if stack:
                    stack[-1].append(node.text or '')
                if (node.text or '').lstrip().startswith('TC '):
                    run = node.getparent()
                    hide = run.find(W+'rPr/'+W+'vanish')
                    if hide is not None and hide.get(W+'val', '1') not in ('0','false','off'):
                        hidden_tc += 1
            for key, value in node.attrib.items():
                if key in (R+'id', R+'embed', R+'link'):
                    check('relationship_reference:' + name, value in rel_maps.get(name, {}), value)
        check('field_balance:' + name, not stack, len(stack))
    check('bookmark_names_unique', None not in bookmark_names and
          len(bookmark_names) == len(set(bookmark_names)))
    names = set(bookmark_names)
    for name, root in stories.items():
        for link in root.iter(W+'hyperlink'):
            anchor = link.get(W+'anchor')
            if anchor:
                check('hyperlink_anchor:' + name, anchor in names, anchor)
    for instruction in instructions:
        match = re.match(r'^\s*(?:REF|PAGEREF)\s+(?:"([^"]+)"|(\S+))', instruction, re.I)
        if match:
            target = match[1] or match[2]
            check('reference_field_target', target in names, target)
    body = roots['word/document.xml']
    notes = [n for r in stories.values() for n in r.iter(W+'footnote')
             if n.get(W+'type') not in ('separator', 'continuationSeparator')
             and n.get(W+'id') not in ('-1','0')]
    refs = list(body.iter(W+'footnoteReference'))
    note_ids = [n.get(W+'id') for n in notes]
    check('footnote_ids_unique', len(note_ids) == len(set(note_ids)))
    check('footnote_references', all(n.get(W+'id') in note_ids for n in refs))
    def fields(kind):
        return sum(bool(re.match(r'^\s*'+kind+r'\b', i, re.I)) for i in instructions)
    counts = {'paragraphs': len(list(body.iter(W+'p'))), 'tables': len(list(body.iter(W+'tbl'))),
              'math': len(list(body.iter(M+'oMath'))), 'display_math': len(list(body.iter(M+'oMathPara'))),
              'images': sum(n.tag.endswith('}blip') and n.get(R+'embed') is not None for n in body.iter()),
              'footnotes': len(notes), 'bookmarks': len(bookmark_names),
              'toc_fields': fields('TOC'), 'seq_fields': fields('SEQ'),
              'ref_fields': fields('(?:REF|PAGEREF)')}
    allowed = {'exact_counts','minimum_counts','required_text','forbidden_text','preserve_parts','sections'}
    check('expectation_keys', not set(expected)-allowed, sorted(set(expected)-allowed))
    for policy in ('exact_counts', 'minimum_counts'):
        for key, value in expected.get(policy, {}).items():
            check(policy+':'+key, key in counts and isinstance(value, int) and
                  (counts[key] == value if policy == 'exact_counts' else counts[key] >= value),
                  {'expected': value, 'actual': counts.get(key)})
    text = '\n'.join(''.join(p.itertext()) for p in body.iter(W+'t'))
    compact = ''.join(text.split())
    for value in expected.get('required_text', []):
        check('required_text', ''.join(value.split()) in compact, value)
    for value in expected.get('forbidden_text', []):
        check('forbidden_text', ''.join(value.split()) not in compact, value)
    sections = [{E.QName(child).localname: {E.QName(k).localname: v for k,v in child.attrib.items()}
                 for child in sec} for sec in body.iter(W+'sectPr')]
    if 'sections' in expected:
        check('section_count', len(sections) == len(expected['sections']))
        for index, spec in enumerate(expected['sections']):
            actual = sections[index] if index < len(sections) else {}
            for tag, attrs in spec.items():
                check('section:'+str(index)+':'+tag,
                      all(actual.get(tag, {}).get(k) == v for k,v in attrs.items()),
                      {'expected': attrs, 'actual': actual.get(tag)})
    preserved = expected.get('preserve_parts', [])
    if preserved:
        check('preservation_source', template is not None)
        original = read_package(template) if template else {}
        for name in preserved:
            check('preserved_part:'+name, name in original and name in parts
                  and original[name] == parts[name])
    check('input_unchanged', sha(document) == before)
    return {'passed': not errors, 'document': str(document.resolve()), 'sha256': before,
            'counts': counts, 'sections': sections, 'checks': checks, 'errors': errors,
            'external_relationships': external, 'hidden_tc_fields': hidden_tc,
            'update_fields_on_open': [n.get(W+'val') for r in stories.values()
                                      for n in r.iter(W+'updateFields')],
            'expectations_supplied': bool(expected),
            'limitations': ['No semantic completeness or visual review certified',
                            'No Word refresh, real click, or edit-after-update test performed',
                            'display_math counts oMathPara only; inline-layout display equations may use oMath',
                            'External relationships are listed but never fetched']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--document', type=Path, required=True)
    p.add_argument('--template', type=Path)
    p.add_argument('--expected', type=Path)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    if args.report.exists():
        raise FileExistsError('Fresh report path required')
    result = audit(args.document, args.template,
                   json.loads(args.expected.read_text(encoding='utf-8')) if args.expected else {})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'passed': result['passed'], 'errors': result['errors']}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)

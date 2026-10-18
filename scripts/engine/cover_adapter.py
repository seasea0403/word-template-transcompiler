"""Execute a run-local cover-only contract, preserving other OPC parts.

Feature identifiers and ranges belong to the current template interpretation;
there are no case names or school presets in this adapter.
"""
import argparse
import copy
import hashlib
import json
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from lxml import etree as E
from PIL import ImageFont
import pdfplumber
from inspect_docx import paths
from title_layout import distribute_title
from manuscript_ir import sha

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def canonical(n): return E.tostring(n, method='c14n')
def node_text(n): return ''.join(t.text or '' for t in n.iter(W+'t'))


def replace_span(p, start, end, value):
    nodes = p.findall(W+'r/'+W+'t')
    original = ''.join(n.text or '' for n in nodes)
    if not nodes or not 0 <= start <= end <= len(original):
        raise ValueError('Invalid plain-text span')
    if any(c.tag not in (W+'pPr', W+'r', W+'bookmarkStart', W+'bookmarkEnd') for c in p):
        raise ValueError('Complex paragraph requires another adapter')
    if any(c.tag not in (W+'rPr', W+'t') for r in p.findall(W+'r') for c in r):
        raise ValueError('Non-text run cannot be replaced')
    offset, inserted = 0, False
    for n in nodes:
        old = n.text or ''; stop = offset + len(old)
        if stop > start and offset < end:
            left = old[:max(0, start-offset)]
            right = old[max(0, end-offset):] if end < stop else ''
            n.text = left + (value if not inserted else '') + right
            inserted = True
        offset = stop
        n.set(SPACE, 'preserve')
    if start == end:
        raise ValueError('Empty spans use the insertion adapter')
    if node_text(p) != original[:start] + value + original[end:]:
        raise ValueError('Span replacement changed unrelated text')


def replace_plain(p, value):
    if any(c.tag not in (W+'pPr', W+'r', W+'bookmarkStart', W+'bookmarkEnd') for c in p):
        raise ValueError('Complex paragraph')
    if p.findall(W+'r'):
        replace_span(p, 0, len(node_text(p)), value)
    else:
        rp = p.find(W+'pPr/'+W+'rPr')
        if rp is None: raise ValueError('Empty slot has no character properties')
        r = E.SubElement(p, W+'r'); r.append(copy.deepcopy(rp))
        t = E.SubElement(r, W+'t'); t.text = value; t.set(SPACE, 'preserve')


def clear_fullwidth_span(p, start, end, font=None):
    """Clear CJK example values without collapsing source padding or run boundaries.

    Fullwidth examples occupy em cells; use nonbreaking blanks after measuring
    them against the actual source font. Trailing ideographic blanks can hide
    the underline in document renderers even though w:u remains present.
    Proportional Latin examples require a measured adapter and fail explicitly.
    """
    original = node_text(p)
    if not 0 <= start < end <= len(original):
        raise ValueError('Invalid clear span')
    value = original[start:end]
    if any(not c.isspace() and unicodedata.east_asian_width(c) not in ('W','F') for c in value):
        raise ValueError('Proportional example needs measured clearance')
    if font is not None and any(abs(font.getlength(c)-font.getlength('\u00a0'))>.1 for c in value if not c.isspace()):
        raise ValueError('Nonbreaking blank is not width-equivalent in source font')
    offset = 0
    for t in p.findall(W+'r/'+W+'t'):
        old = t.text or ''
        t.text = ''.join('\u00a0' if start <= offset+i < end and not c.isspace() else c
                         for i,c in enumerate(old))
        t.set(SPACE,'preserve'); offset += len(old)
    if offset != len(original): raise ValueError('Complex slot requires another adapter')


def clear_underlined_slot(p, start, end, reference_pdf, page, margin_left_twips, example):
    """Retain underline geometry using source-rendered evidence and a native tab.

    A run of only blank cells is renderer-dependent. The source's contiguous
    underline under the reviewed example provides an unambiguous endpoint.
    """
    if example not in node_text(p)[start:end]: raise ValueError('Slot example mismatch')
    with pdfplumber.open(reference_pdf) as pdf:
        pg=pdf.pages[page-1]
        words=[w for w in pg.extract_words() if w['text']==example]
        if len(words)!=1:raise ValueError('Ambiguous rendered example')
        word=words[0]
        lines=[x for x in pg.lines if abs(x['top']-word['bottom'])<2 and abs(x['top']-x['bottom'])<.1]
        if not lines or not any(x['x0']<=word['x0'] and x['x1']>=word['x1'] for x in lines):
            raise ValueError('No source underline evidence')
        endpoint=max(x['x1'] for x in lines)
        stop=round(endpoint*20-margin_left_twips)
    if not 0<stop<12000:raise ValueError('Invalid measured tab')
    offset=0; target=None
    for r in p.findall(W+'r'):
        n=sum(len(t.text or '') for t in r.findall(W+'t'))
        if offset<=start<offset+n:target=r
        offset+=n
    if target is None or target.find(W+'rPr/'+W+'u') is None:raise ValueError('Underline run required')
    replace_span(p,start,end,'')
    E.SubElement(target,W+'tab')
    pr=p.find(W+'pPr')
    if pr.find(W+'tabs') is not None:raise ValueError('Existing tabs need conflict review')
    tabs=E.SubElement(pr,W+'tabs');E.SubElement(tabs,W+'tab',{W+'val':'left',W+'pos':str(stop)})
    jc=pr.find(W+'jc')
    if jc is None:jc=E.SubElement(pr,W+'jc')
    jc.set(W+'val','left')
    return {'source_pdf_sha256':sha(reference_pdf),'underline_end_pt':endpoint,'tab_stop_twips':stop}


def fill_underlined_slot(p, action, value):
    """Retain this field's typography; derive its reviewed peer-row width from PDF."""
    reference=Path(action['reference_pdf'])
    with pdfplumber.open(reference) as pdf:
        pg=pdf.pages[action['reference_page']-1]
        words=[w for w in pg.extract_words() if w['text']==action['geometry_example']]
        if len(words)!=1:raise ValueError('Ambiguous peer field geometry')
        word=words[0]
        lines=[x for x in pg.lines if abs(x['top']-word['bottom'])<2 and abs(x['top']-x['bottom'])<.1]
        if not lines:raise ValueError('Missing peer underline')
        x0=min(x['x0'] for x in lines); x1=max(x['x1'] for x in lines)
    original=node_text(p); start=action['start']; end=action['end']
    underlined=[r for r in p.findall(W+'r') if r.find(W+'rPr/'+W+'u') is not None]
    if not underlined:raise ValueError('Missing field typography')
    rp=copy.deepcopy(underlined[0].find(W+'rPr'))
    replace_span(p,start,end,'')
    pr=p.find(W+'pPr')
    for tag in ('tabs','jc'):
        old=pr.find(W+tag)
        if old is not None:pr.remove(old)
    E.SubElement(pr,W+'jc',{W+'val':'left'})
    tabs=E.SubElement(pr,W+'tabs'); margin=action['margin_left_twips']
    if value:E.SubElement(tabs,W+'tab',{W+'val':'center',W+'pos':str(round((x0+x1)*10-margin))})
    E.SubElement(tabs,W+'tab',{W+'val':'left',W+'pos':str(round(x1*20-margin))})
    r=E.SubElement(p,W+'r');r.append(rp)
    if value:
        E.SubElement(r,W+'tab');t=E.SubElement(r,W+'t');t.text=value;t.set(SPACE,'preserve')
    E.SubElement(r,W+'tab')
    if node_text(p)!=original[:start]+value+original[end:]:raise ValueError('Field text conservation failure')
    return {'source_pdf_sha256':sha(reference),'geometry_example':action['geometry_example'],'underline_start_pt':x0,'underline_end_pt':x1,'value':value}

def replace_title_lines(p, value, lines):
    if len(lines) != 2 or ''.join(lines) != value:
        raise ValueError('Title lines must conserve full text')
    replace_plain(p, value)
    if lines[1]:
        t = next(t for t in p.findall(W+'r/'+W+'t') if t.text)
        t.text = lines[0]
        r = t.getparent(); E.SubElement(r, W+'br')
        tail = E.SubElement(r, W+'t'); tail.text = lines[1]
        tail.set(SPACE, 'preserve')
    if node_text(p) != value: raise ValueError('Title text lost')


def generate(features_path, bindings_path, ir_path, output):
    f = json.loads(features_path.read_text(encoding='utf-8'))
    contract = json.loads(bindings_path.read_text(encoding='utf-8'))
    if not (bindings_path.parent/'artifact.md').is_file():
        raise ValueError('Missing scoped execution contract')
    ir = json.loads(ir_path.read_text(encoding='utf-8'))
    source = Path(f['source'])
    if sha(source) != f['source_sha256'] or contract['source_sha256'] != f['source_sha256']:
        raise ValueError('Source mismatch')
    if contract['scope'] != 'cover_only_diagnostic': raise ValueError('Wrong execution scope')
    if sha(Path(ir['source'])) != ir['source_sha256']: raise ValueError('Manuscript mismatch')
    if output.exists() or output.resolve() == source.resolve(): raise ValueError('Fresh output required')
    with zipfile.ZipFile(source) as z:
        infos = z.infolist()
        if len({i.filename for i in infos}) != len(infos): raise ValueError('Duplicate OPC part')
        if sum(i.file_size for i in infos) > 64*1024*1024: raise ValueError('OPC too large')
        if any(i.filename.startswith(('/', '\\')) or ':' in i.filename or '..' in i.filename.replace('\\','/').split('/') for i in infos):
            raise ValueError('Unsafe OPC path')
        parts = {i.filename:z.read(i) for i in infos}
    if b'<!DOCTYPE' in parts['word/document.xml'].upper(): raise ValueError('DTD forbidden')
    root = E.fromstring(parts['word/document.xml'], E.XMLParser(resolve_entities=False, no_network=True))
    original = copy.deepcopy(root)
    nodes = {path:n for n,path in paths(root)}
    etnodes = {path:n for n,path in paths(ET.fromstring(parts['word/document.xml']))}
    by_id = {x['id']:x for x in f['features']}
    def locate(ident):
        feature = by_id[ident]
        if feature['part'] != 'word/document.xml': raise ValueError('Wrong part')
        node = etnodes[feature['xml_path']]
        if hashlib.sha256(ET.tostring(node, encoding='utf-8')).hexdigest() != feature['guard_sha256']:
            raise ValueError('Feature guard mismatch')
        return nodes[feature['xml_path']]
    targets, receipts, style_restores = [], [], []
    for action in contract['actions']:
        ids = action.get('feature_ids', [action.get('feature_id')])
        selected = [locate(i) for i in ids]
        for n in selected:
            if n.tag != W+'p': raise ValueError('Slot is not a paragraph')
            if any(n is t or n in t.iterdescendants() or t in n.iterdescendants() for t,_ in targets):
                raise ValueError('Overlapping cover edits')
            targets.append((n, copy.deepcopy(n)))
        value = ir['metadata_text_view'].get(action.get('metadata_key'), '') if action.get('metadata_key') else action.get('literal', '')
        if action['kind'] == 'span':
            n = selected[0]; start = action['start']; end = action.get('end', len(node_text(n)))
            replace_span(n, start, end, value)
        elif action['kind'] == 'clear_fullwidth_span':
            fontfile=Path(action['font_file'])
            font=ImageFont.truetype(str(fontfile),round(float(by_id[ids[0]]['effective_sample_format']['run']['sz']['val'])*2))
            original_text=node_text(selected[0])
            clear_fullwidth_span(selected[0], action['start'], action['end'],font)
            receipts.append({'clear_width_before':font.getlength(original_text),
                             'clear_width_after':font.getlength(node_text(selected[0])),
                             'font_sha256':sha(fontfile)})
        elif action['kind'] == 'clear_underlined_slot':
            receipts.append(clear_underlined_slot(selected[0],action['start'],action['end'],
                Path(action['reference_pdf']),action['reference_page'],action['margin_left_twips'],action['example']))
        elif action['kind'] == 'fill_underlined_slot':receipts.append(fill_underlined_slot(selected[0],action,value))
        elif action['kind'] == 'plain': replace_plain(selected[0], value)
        elif action['kind'] in ('two_title_slots', 'balanced_title_paragraph'):
            fontfile = Path(action['font_file'])
            size = float(by_id[ids[0]]['effective_sample_format']['run']['sz']['val'])/2
            font = ImageFont.truetype(str(fontfile), round(size*4))
            widths = []
            for p in selected:
                cell = p.getparent()
                while cell is not None and cell.tag != W+'tc': cell = cell.getparent()
                if cell is None: raise ValueError('Title slot needs cell width')
                width = int(cell.find(W+'tcPr/'+W+'tcW').get(W+'w'))
                widths.append(width - action['horizontal_cell_margin_twips'])
            if action['kind'] == 'balanced_title_paragraph':
                if len(selected) != 1: raise ValueError('One paragraph required')
                widths *= 2
            layout = distribute_title(value, action['word_boundaries'], widths,
                                      lambda s: font.getlength(s)*5,
                                      protected_terms=action['protected_terms'])
            if action['kind'] == 'balanced_title_paragraph':
                replace_title_lines(selected[0], value, layout['lines'])
                receipts.append({'title_layout':layout,'font_sha256':sha(fontfile)})
                receipts.append({'feature_ids':ids,'kind':action['kind'],'value':value})
                continue
            first = selected[0]
            for index,p in enumerate(selected):
                if index:
                    p.replace(p.find(W+'pPr'), copy.deepcopy(first.find(W+'pPr')))
                    p.find(W+'r').replace(p.find(W+'r/'+W+'rPr'), copy.deepcopy(first.find(W+'r/'+W+'rPr')))
                replace_plain(p, layout['lines'][index])
            receipts.append({'title_layout':layout,'font_sha256':sha(fontfile)})
        else: raise ValueError('Unsupported cover action')
        receipts.append({'feature_ids':ids,'kind':action['kind'],'value':value})
    for action in contract.get('property_actions', []):
        p = locate(action['feature_id'])
        if action['kind'] == 'empty_paragraph_line_height':
            if node_text(p) or any(n.tag in (W+'drawing',W+'pict') for n in p.iter()):
                raise ValueError('Only reviewed blank spacing may be adjusted')
            if any(p is n for n,_ in targets): raise ValueError('Overlapping property edit')
            targets.append((p,copy.deepcopy(p)))
            spacing = p.find(W+'pPr/'+W+'spacing')
            if spacing is None or spacing.get(W+'line') != str(action['expected_line_twips']):
                raise ValueError('Blank spacing precondition')
            value = int(action['line_twips'])
            if not 20 <= value <= int(action['expected_line_twips']):
                raise ValueError('Spacing change exceeds approved direction')
            spacing.set(W+'line',str(value)); spacing.set(W+'lineRule','exact')
        elif action['kind'] == 'textbox_geometry':
            shape = p.getparent()
            while shape is not None and shape.tag != '{urn:schemas-microsoft-com:vml}shape':
                shape = shape.getparent()
            if shape is None: raise ValueError('No VML textbox ancestor')
            path = next(path for path,n in nodes.items() if n is shape)
            old = shape.get('style'); style_restores.append((path,old))
            styles = dict(item.split(':',1) for item in old.split(';') if ':' in item)
            for key,value in action['changes'].items():
                if key not in ('margin-top','height') or styles.get(key) != action['expected'][key]:
                    raise ValueError('Geometry precondition')
                if not value.endswith('pt') or not 0 < float(value[:-2]) < 842:
                    raise ValueError('Geometry must be bounded page points')
                styles[key] = value
            shape.set('style',';'.join(k+':'+v for k,v in styles.items())+';')
        else: raise ValueError('Unsupported cover property action')
        receipts.append({'property_action':action})
    # Restore every edited paragraph in a copy and compare the entire source.
    restored = copy.deepcopy(root)
    restored_nodes = {path:n for n,path in paths(restored)}
    for n,snapshot in targets:
        path = next(path for path,v in nodes.items() if v is n)
        current = restored_nodes[path]; current.getparent().replace(current, snapshot)
    for path,old in style_restores: restored_nodes[path].set('style',old)
    if canonical(restored) != canonical(original): raise ValueError('Out-of-slot change')
    body = root.find(W+'body'); old_children = list(body)
    section = copy.deepcopy(locate(contract['section_feature_id']))
    chosen = []
    for start,end in contract['keep_body_ranges']:
        if not 0 <= start < end <= len(old_children): raise ValueError('Invalid retained range')
        chosen.extend(old_children[start:end])
    if len({id(n) for n in chosen}) != len(chosen): raise ValueError('Overlapping retained ranges')
    for target,_ in targets:
        if not any(target is n or target in n.iterdescendants() for n in chosen):
            raise ValueError('Edited slot not retained')
    preserved_graphics = [canonical(n) for child in chosen for tag in ('drawing','pict') for n in child.iter(W+tag)]
    for n in list(body): body.remove(n)
    for child in chosen:
        # The cover diagnostic has no navigation; remove dangling source bookmarks.
        for tag in ('bookmarkStart','bookmarkEnd','sectPr'):
            for n in list(child.iter(W+tag)): n.getparent().remove(n)
        body.append(child)
    body.append(section)
    final_graphics = [canonical(n) for child in chosen for tag in ('drawing','pict') for n in child.iter(W+tag)]
    if final_graphics != preserved_graphics: raise ValueError('Retained artwork changed')
    changed = dict(parts); changed['word/document.xml'] = E.tostring(root, encoding='UTF-8', xml_declaration=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output,'x') as z:
        for info in infos: z.writestr(info, changed[info.filename])
    with zipfile.ZipFile(output) as z:
        if any(z.read(k) != v for k,v in changed.items()): raise ValueError('Committed package mismatch')
    if sha(source) != f['source_sha256']: raise ValueError('Source changed')
    receipt = {'scope':'cover_only_diagnostic','source_unchanged':True,
               'outside_slot_xml_unchanged_before_approved_trimming':True,
               'retained_drawing_structure_unchanged_after_permitted_metadata_edits':True,
               'all_other_package_parts_byte_identical':True,
               'output_sha256':sha(output),'bindings_sha256':sha(bindings_path),
               'features_sha256':sha(features_path),'ir_sha256':sha(ir_path),
               'actions':receipts,'retained_ranges':contract['keep_body_ranges'],
               'render_and_Word_verification':'not_performed'}
    (output.parent/'write-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--features',type=Path,required=True)
    p.add_argument('--bindings',type=Path,required=True); p.add_argument('--ir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    print(json.dumps(generate(a.features,a.bindings,a.ir,a.output),ensure_ascii=False))

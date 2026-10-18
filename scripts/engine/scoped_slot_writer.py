"""Limited paragraph-slot transaction, not the full contract compiler."""
import copy
import xml.etree.ElementTree as ET
from lxml import etree
from inspect_docx import paths
from text_slot_writer import W, sha, XML_SPACE, fail

def stage_slots(parts, slots):
    if not slots: fail('empty_slots')
    roots={}; targets=[]; seen=set()
    for slot in slots:
        required={'id','part','part_sha256','xml_path','guard_sha256','action','expected_text','replacement'}
        if set(slot)!=required or not all(isinstance(v,str) for v in slot.values()): fail('slot_shape')
        part=slot['part']; key=(part,slot['xml_path'])
        if key in seen: fail('duplicate_slot')
        seen.add(key)
        if part not in parts or part!='word/document.xml': fail('unsupported_part')
        if sha(parts[part])!=slot['part_sha256']: fail('part_hash_mismatch')
        if part not in roots:
            if b'<!DOCTYPE' in parts[part].upper() or b'<!ENTITY' in parts[part].upper(): fail('xml_dtd_forbidden')
            roots[part]=etree.fromstring(parts[part],etree.XMLParser(resolve_entities=False,no_network=True))
        n=dict((p,n) for n,p in paths(roots[part])).get(slot['xml_path'])
        original=dict((p,n) for n,p in paths(ET.fromstring(parts[part]))).get(slot['xml_path'])
        if n is None or original is None: fail('locator_missing')
        if sha(ET.tostring(original,encoding='utf-8'))!=slot['guard_sha256']: fail('node_hash_mismatch')
        if n.tag!=W+'p' or any(c.tag not in (W+'pPr',W+'r') for c in n): fail('unsupported_slot_structure')
        if ''.join(t.text or '' for t in n.iter(W+'t'))!=slot['expected_text']: fail('text_mismatch')
        if any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF or ord(c) in (65534,65535) for c in slot['replacement']): fail('invalid_replacement')
        rs=n.findall(W+'r')
        if slot['action']=='replace_single_run':
            if len(rs)!=1 or len(rs[0].findall(W+'t'))!=1 or any(c.tag not in (W+'rPr',W+'t') for c in rs[0]): fail('not_single_plain_run')
        elif slot['action']=='insert_into_empty_paragraph':
            if rs or slot['expected_text'] or n.find(W+'pPr/'+W+'rPr') is None: fail('not_empty_formatted_paragraph')
        else: fail('unsupported_action')
        targets.append((slot,n,copy.deepcopy(n)))
    before={p:etree.tostring(n,method='c14n') for p,n in roots.items()}
    for slot,n,_ in targets:
        if slot['action']=='replace_single_run': t=n.find(W+'r/'+W+'t')
        else:
            r=etree.SubElement(n,W+'r'); r.append(copy.deepcopy(n.find(W+'pPr/'+W+'rPr'))); t=etree.SubElement(r,W+'t')
        t.text=slot['replacement']
        if t.text!=t.text.strip(): t.set(XML_SPACE,'preserve')
    result=dict(parts)
    for p,n in roots.items(): result[p]=etree.tostring(n,encoding='UTF-8',xml_declaration=True)
    for _,n,old in targets: n.getparent().replace(n,old)
    if any(etree.tostring(n,method='c14n')!=before[p] for p,n in roots.items()): fail('outside_scope_changed')
    return result,{'slots':slots,'modified_parts':list(roots),'outside_slot_xml_unchanged':True,
        'other_parts_byte_identical':all(result[p]==parts[p] for p in parts if p not in roots),
        'limitations':['Limited scoped diagnostic transaction; not full contract execution','Rendering and Word checks required']}

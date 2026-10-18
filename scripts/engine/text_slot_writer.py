"""In-memory, guarded text-node patch primitive. Not a DOCX authoring entry point.

Caller must first approve a complete contract and compile authorized text slots.
This module does not read files, commit a DOCX, render, or certify slot approval.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from lxml import etree
from inspect_docx import paths

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
XML_SPACE='{http://www.w3.org/XML/1998/namespace}space'
FIELDS={'id','part','part_sha256','xml_path','node_sha256','expected_text','replacement'}
def sha(data): return hashlib.sha256(data).hexdigest()
def fail(code): raise ValueError(code)

def stage_text_updates(parts,operations):
    """Return new part bytes and audit receipt; never mutate inputs.

    Node hashes use the existing survey's ElementTree serialization convention.
    Only an explicitly selected leaf w:t in an ordinary w:r is supported.
    """
    if not isinstance(parts,dict) or not all(isinstance(k,str) and isinstance(v,bytes) for k,v in parts.items()): fail('package_type')
    if sum(map(len,parts.values()))>64*1024*1024: fail('package_budget')
    for name in parts:
        if name.startswith(('/', '\\')) or '\\' in name or ':' in name or '..' in name.split('/'): fail('unsafe_part')
    if not isinstance(operations,list) or not operations: fail('empty_operations')
    roots={}; original_nodes={}; seen=set(); ids=set(); targets=[]
    for op in operations:
        if not isinstance(op,dict) or set(op)!=FIELDS: fail('operation_shape')
        if not all(isinstance(op[k],str) for k in FIELDS): fail('operation_type')
        if not op['id'] or op['id'] in ids: fail('duplicate_operation_id')
        ids.add(op['id'])
        part=op['part']; key=(part,op['xml_path'])
        if key in seen: fail('duplicate_target')
        seen.add(key)
        if part not in parts or not part.startswith('word/') or not part.endswith('.xml'): fail('unsupported_part')
        if sha(parts[part])!=op['part_sha256']: fail('part_hash_mismatch')
        if part not in roots:
            raw=parts[part]
            if re.search(br'<!\s*(DOCTYPE|ENTITY)\b',raw,re.I): fail('xml_dtd_forbidden')
            parser=etree.XMLParser(resolve_entities=False,no_network=True,remove_blank_text=False)
            roots[part]=etree.fromstring(raw,parser)
            original_nodes[part]={p:n for n,p in paths(ET.fromstring(raw))}
        node_map={p:n for n,p in paths(roots[part])}
        node=node_map.get(op['xml_path']); old=original_nodes[part].get(op['xml_path'])
        if node is None or old is None: fail('locator_missing')
        if sha(ET.tostring(old,encoding='utf-8'))!=op['node_sha256']: fail('node_hash_mismatch')
        if node.tag!=W+'t' or len(node) or node.getparent() is None or node.getparent().tag!=W+'r': fail('unsupported_text_node')
        if (node.text or '')!=op['expected_text']: fail('text_mismatch')
        ancestor=node.getparent()
        while ancestor is not None:
            if ancestor.tag in {W+x for x in ('hyperlink','fldSimple','ins','del','sdt')} or ancestor.tag.startswith('{http://schemas.openxmlformats.org/officeDocument/2006/math}'): fail('specialized_content')
            if ancestor.tag==W+'p' and any(x.tag in {W+'fldChar',W+'instrText'} for x in ancestor.iter()): fail('specialized_content')
            ancestor=ancestor.getparent()
        replacement=op['replacement']
        if any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF or ord(c) in (0xFFFE,0xFFFF) for c in replacement): fail('replacement_not_single_text')
        targets.append((op,node))
    # Validate every operation before any changes; XML trees are private copies.
    before={part:etree.tostring(root,method='c14n') for part,root in roots.items()}
    saved=[]
    for op,node in targets:
        saved.append((node,node.text,node.get(XML_SPACE)))
        node.text=op['replacement']
        if op['replacement']!=op['replacement'].strip(): node.set(XML_SPACE,'preserve')
    output=dict(parts)
    for part,root in roots.items():
        output[part]=etree.tostring(root,encoding='UTF-8',xml_declaration=True)
    # Roll back only intended text and whitespace flag to prove all other XML
    # structure, attributes, namespaces, drawings and section settings stayed.
    for node,text,space in saved:
        node.text=text
        if space is None: node.attrib.pop(XML_SPACE,None)
        else: node.set(XML_SPACE,space)
    if any(etree.tostring(root,method='c14n')!=before[part] for part,root in roots.items()): fail('unexpected_xml_change')
    changed=[part for part in parts if parts[part]!=output[part]]
    receipt={'operations':[{'id':op['id'],'part':op['part'],'xml_path':op['xml_path'],
        'before_text_sha256':sha(op['expected_text'].encode()),'after_text_sha256':sha(op['replacement'].encode())} for op,_ in targets],
        'changed_parts':changed,'untouched_parts_byte_identical':all(parts[p]==output[p] for p in parts if p not in roots),
        'nontext_xml_unchanged':True,'part_hashes':{p:{'before':sha(parts[p]),'after':sha(output[p])} for p in changed},
        'limitations':['In-memory primitive only; no approval/contract compiler or ZIP commit',
        'Not a security sandbox','No Word editing, rendering, overflow or interaction validation']}
    return output,receipt

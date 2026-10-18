"""Compile task-reviewed sample/override bindings without school presets.

This creates executable paragraph properties, not a complete document contract.
Complex section, table, numbering and TOC structures remain separate adapters.
"""
import argparse
import json
import copy
import hashlib
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from inspect_docx import paths
from manuscript_ir import sha
from paragraph_roles import compile_role, materialize_props
from write_pipeline import verify_review


def compile_bindings(template, review_path, bindings_path):
    review, features = verify_review(template, review_path)
    bindings = json.loads(bindings_path.read_text(encoding='utf-8'))
    if bindings['source_sha256'] != sha(template): raise ValueError('Binding source mismatch')
    by_id = {f['id']: f for f in features['features']}
    with zipfile.ZipFile(template) as z:
        xml = z.read('word/document.xml')
    if b'<!DOCTYPE' in xml.upper(): raise ValueError('DTD forbidden')
    nodes = {path: n for n, path in paths(ET.fromstring(xml))}
    roles = {}
    for binding in bindings['roles']:
        name = binding['role']
        if name in roles: raise ValueError('Duplicate role')
        if not binding.get('rationale') or not binding.get('evidence_ids'):
            raise ValueError('Role requires interpretation evidence')
        for ident in [binding['sample_id']] + binding['evidence_ids']:
            f = by_id[ident]
            if f['kind'] != 'paragraph' or f['part'] != 'word/document.xml':
                raise ValueError('Paragraph evidence required')
            raw = ET.tostring(nodes[f['xml_path']], encoding='utf-8')
            if hashlib.sha256(raw).hexdigest() != f['guard_sha256']:
                raise ValueError('Source node guard mismatch')
        sample = copy.deepcopy(by_id[binding['sample_id']]['effective_sample_format'])
        for area, tags in binding.get('remove_properties', {}).items():
            if area not in ('paragraph', 'run'): raise ValueError('Unknown property area')
            for tag in tags: sample[area].pop(tag, None)
        overrides = binding.get('overrides', {})
        if set(overrides) - {'paragraph', 'run'}: raise ValueError('Unknown override area')
        role = compile_role(sample, overrides)
        for tag in ('sectPr', 'tabs', 'numPr'):
            if tag in role['paragraph']:
                raise ValueError('Complex property requires a dedicated component: '+tag)
        for area, kind in [('paragraph','pPr'),('run','rPr')]:
            materialize_props(kind, role[area])
        roles[name] = {'properties': role, 'sample_id': binding['sample_id'],
                       'evidence_ids': binding['evidence_ids'], 'rationale': binding['rationale']}
    return {'schema_version': 'executable-paragraph-roles/1',
            'source_sha256': sha(template), 'review_sha256': sha(review_path),
            'bindings_sha256': sha(bindings_path), 'roles': roles,
            'scope': 'paragraph_properties_only', 'complete_document_contract': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('template','review','bindings','out'): p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); result=compile_bindings(a.template,a.review,a.bindings)
    if a.out.exists(): raise ValueError('Fresh output required')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'role_count':len(result['roles']),'output_sha256':sha(a.out)}))

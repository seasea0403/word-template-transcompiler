"""Bind human formatting interpretations to a verified, run-local feature record.

This is an evidence report, not an executable formatting preset. No template
names, school rules or semantic decisions are embedded in this utility.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(features_path, annotations_path, output_path):
    features = json.loads(features_path.read_text(encoding='utf-8'))
    annotations = json.loads(annotations_path.read_text(encoding='utf-8'))
    if sha(Path(features['source'])) != features['source_sha256']:
        raise ValueError('Source template changed')
    by_id = {item['id']: item for item in features['features']}
    rules = []
    for item in annotations['rules']:
        if not item.get('evidence_ids'):
            raise ValueError('Every interpretation needs feature evidence')
        evidence = []
        for ident in item['evidence_ids']:
            f = by_id[ident]
            evidence.append({k: f[k] for k in
                             ('id', 'kind', 'part', 'xml_path', 'guard_sha256',
                              'text', 'effective_sample_format') if k in f})
        rules.append({**item, 'evidence': evidence})
    if output_path.exists():
        raise FileExistsError('Preserve previous reports; use a new revision')
    report = {
        'schema_version': 'template-format-review/1',
        'is_executable_contract': False,
        'source': features['source'],
        'source_sha256': features['source_sha256'],
        'features_path': str(features_path.resolve()),
        'features_sha256': sha(features_path),
        'annotations_path': str(annotations_path.resolve()),
        'annotations_sha256': sha(annotations_path),
        'stats': features['stats'],
        'rules': rules,
        'limitations': annotations['limitations'],
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
    return {'rules': len(rules), 'evidence_links': sum(len(r['evidence']) for r in rules),
            'source_unchanged': True, 'output_sha256': sha(output_path)}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--features', type=Path, required=True)
    p.add_argument('--annotations', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(bind(a.features, a.annotations, a.output)))

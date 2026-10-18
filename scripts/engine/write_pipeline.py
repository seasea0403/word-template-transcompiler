"""Unified preflight entrypoint: immutable inputs -> full AST -> bound write plan.

Template-local semantic reviews are intermediate evidence for this run, not
preinstalled school rules. Actual authoring is gated until the complete slot,
section and object adapter contract has been supplied and verified.
"""
import argparse
import json
from pathlib import Path
from manuscript_ir import parse, sha


def verify_review(template, review_path):
    review = json.loads(review_path.read_text(encoding='utf-8'))
    if review['schema_version'] != 'template-format-review/1':
        raise ValueError('Unsupported format review')
    if sha(template) != review['source_sha256']:
        raise ValueError('Review is bound to a different template')
    features_path, annotations_path = Path(review['features_path']), Path(review['annotations_path'])
    if sha(features_path) != review['features_sha256'] or sha(annotations_path) != review['annotations_sha256']:
        raise ValueError('Review evidence changed')
    features = json.loads(features_path.read_text(encoding='utf-8'))
    if features['source_sha256'] != sha(template): raise ValueError('Feature source mismatch')
    by_id = {f['id']: f for f in features['features']}
    annotations = json.loads(annotations_path.read_text(encoding='utf-8'))['rules']
    if len(annotations) != len(review['rules']): raise ValueError('Review rule count mismatch')
    for rule, annotation in zip(review['rules'], annotations):
        if {k: v for k, v in rule.items() if k != 'evidence'} != annotation:
            raise ValueError('Interpretation differs from recorded annotations')
        if [e['id'] for e in rule['evidence']] != rule['evidence_ids']:
            raise ValueError('Evidence list mismatch')
        for evidence in rule['evidence']:
            original = by_id[evidence['id']]
            if any(original.get(k) != v for k, v in evidence.items()):
                raise ValueError('Feature evidence mismatch')
    return review, features


def compile_plan(ir, review, template, output):
    rules = {r['role']: r for r in review['rules']}
    actions = []
    for obj in ir['objects']:
        role = obj['role']
        group = ('body_headings' if role in ('chapter', 'section', 'subsection') else
                 'table' if role in ('table', 'table_caption') else 'figure' if role in ('image', 'figure') else
                 'footnote' if role == 'note' else 'equation' if role in ('equation', 'inline_math') else
                 'references' if role in ('references', 'bibliography_entry') else
                 role.replace('keywords_', 'abstract_') if role.startswith('keywords_') else
                 'body' if role == 'body' else role)
        rule = rules.get(group)
        if rule is None and group == 'references': rule = rules.get('references_journal')
        actions.append({'operation_id': 'op-' + str(len(actions)),
                        'content_object_id': obj['id'], 'content_pointer': obj['pointer'],
                        'kind': obj['kind'], 'role': role, 'chapter': obj['chapter'],
                        'format_rule': rule['role'] if rule else None,
                        'format_properties': rule['properties'] if rule else None,
                        'evidence_ids': rule['evidence_ids'] if rule else [],
                        'status': 'content_and_rule_bound' if rule else 'requires_role_resolution',
                        'not_an_executable_mutation': True})
    return {'schema_version': 'template-write-plan/1',
            'stage': 'preflight_only', 'authoring_allowed': False,
            'template': str(template.resolve()), 'template_sha256': sha(template),
            'manuscript_sha256': ir['source_sha256'], 'output': str(output.resolve()),
            'actions': actions,
            'blocking_requirements': [
                'Complete cover slot map and preservation guards for this template',
                'Compile retained/deleted ranges and final section/header/footer map',
                'Resolve all missing roles, mixed label/body scopes and script fonts',
                'Compile exact paragraph/cell properties, numbering and TOC samples',
                'Wire full native-object adapters and validate content coverage',
            ],
            'verification_after_authoring': ['source_and_preserve_only_package_hashes',
                                            'complete_AST_content_coverage',
                                            'native_tables_math_footnotes',
                                            'citations_and_anchor_targets',
                                            'all_rendered_pages_and_TOC_page_caches',
                                            'Word_interaction_scope'],
            'limitations': ['Bound formatting properties are semantic, not yet OOXML write operations',
                            'No DOCX generated or certified by this preflight']}


def prepare(manuscript, template, review_path, output, run_dir, pandoc):
    if output.resolve() in (manuscript.resolve(), template.resolve()):
        raise ValueError('Output must not overwrite an input')
    if output.exists(): raise FileExistsError('Output path already exists')
    if run_dir.exists(): raise FileExistsError('Use a fresh run directory')
    review, features = verify_review(template, review_path)
    ir = parse(manuscript, pandoc)
    plan = compile_plan(ir, review, template, output)
    run_dir.mkdir(parents=True)
    for name, data in [('manuscript-ir.json', ir), ('write-plan.json', plan)]:
        (run_dir/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    summary = {'stage': 'preflight_complete_authoring_not_started',
               'template_sha256': sha(template), 'manuscript_sha256': sha(manuscript),
               'review_sha256': sha(review_path), 'parser_version': ir['parser_version'],
               'entrypoint_sha256': sha(Path(__file__)),
               'parser_sha256': sha(Path(__file__).with_name('manuscript_ir.py')),
               'chapter_count': ir['chapter_count'], 'counts': ir['counts'],
               'bibliography_count': len(ir['bibliography']),
               'citation_mentions': len(ir['citation_mentions']),
               'actions': len(plan['actions']),
               'unresolved_actions': sum(a['format_rule'] is None for a in plan['actions']),
               'source_templates_unchanged': sha(template) == review['source_sha256'],
               'output_created': False,
               'artifacts': {n: sha(run_dir/n) for n in ['manuscript-ir.json', 'write-plan.json']}}
    (run_dir/'preflight-check.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manuscript', type=Path, required=True)
    p.add_argument('--template', type=Path, required=True)
    p.add_argument('--review', type=Path, required=True, help='Run-local extraction evidence')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--pandoc', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.manuscript, a.template, a.review, a.output, a.run_dir, a.pandoc), ensure_ascii=False))

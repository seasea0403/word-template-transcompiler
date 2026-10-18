"""Portable entry point for evidence-bound Word template workflows."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'engine'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def doctor(args):
    modules = {}
    for name in ('lxml', 'Pillow', 'pdfplumber', 'jsonschema'):
        try:
            modules[name] = {'available': True, 'version': importlib.metadata.version(name)}
        except importlib.metadata.PackageNotFoundError:
            modules[name] = {'available': False}
    tools = {}
    for name in ('pandoc', 'node'):
        path = getattr(args, name)
        if path is None:
            tools[name] = {'tested': False}
            continue
        try:
            result = subprocess.run([str(path), '--version'], capture_output=True,
                                    text=True, timeout=15, check=True)
            tools[name] = {'tested': True, 'available': True,
                           'path': str(path), 'version': result.stdout.splitlines()[0]}
        except (OSError, subprocess.SubprocessError, IndexError) as exc:
            tools[name] = {'tested': True, 'available': False, 'error': str(exc)}
    return {'python': sys.version, 'executable': sys.executable, 'modules': modules,
            'tools': tools, 'ready': all(v['available'] for v in modules.values())
            and all(v.get('available', True) for v in tools.values()),
            'word_and_renderer': 'Discover separately; no COM or renderer invoked by doctor'}


def intake(args):
    from inspect_docx import survey
    from feature_extraction import prepare
    if args.out_dir.exists():
        raise FileExistsError('Fresh intake directory required')
    source = args.template.resolve(strict=True)
    if source.suffix.lower() != '.docx':
        raise ValueError('Expected a DOCX template')
    original = digest(source)
    observed = survey(source)
    args.out_dir.mkdir(parents=True)
    survey_path = args.out_dir / 'survey.json'
    save_new(survey_path, observed)
    prepare(source, survey_path, args.out_dir / 'features')
    if digest(source) != original:
        raise ValueError('Source changed')
    result = {'source': str(source), 'source_sha256': original,
              'source_unchanged': True, 'semantic_review': 'not_performed',
              'visual_review': 'not_performed',
              'tool_sha256': {n: digest(HERE/'engine'/n) for n in
                              ('inspect_docx.py', 'feature_extraction.py', 'paragraph_roles.py')},
              'artifacts': {str(p.relative_to(args.out_dir)): digest(p)
                            for p in args.out_dir.rglob('*') if p.is_file()}}
    save_new(args.out_dir / 'intake-receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deps', type=Path, help='Optional isolated Python dependency directory')
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('doctor', help='Read runtime/module versions and optional tool versions')
    p.add_argument('--pandoc', type=Path)
    p.add_argument('--node', type=Path)
    p = subs.add_parser('intake', help='Read-only source survey and feature preparation')
    p.add_argument('--template', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p = subs.add_parser('parse', help='Preserve full Pandoc AST and inventory supported objects')
    p.add_argument('--manuscript', type=Path, required=True)
    p.add_argument('--pandoc', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = subs.add_parser('check', help='Generic OPC, navigation and declared expectation checks')
    p.add_argument('--document', type=Path, required=True)
    p.add_argument('--template', type=Path)
    p.add_argument('--expected', type=Path)
    p.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    if args.command == 'doctor':
        result = doctor(args)
        code = 0 if result['ready'] else 1
    elif args.command == 'intake':
        result = intake(args)
        code = 0
    elif args.command == 'parse':
        from manuscript_ir import parse
        if args.output.exists():
            raise FileExistsError('Fresh IR path required')
        result = parse(args.manuscript, args.pandoc)
        save_new(args.output, result)
        result = {'output': str(args.output.resolve()), 'sha256': digest(args.output),
                  'counts': result['counts'], 'limitations': result['limitations']}
        code = 0
    else:
        from verify_docx import audit
        if args.report.exists():
            raise FileExistsError('Fresh report path required')
        expected = json.loads(args.expected.read_text(encoding='utf-8')) if args.expected else {}
        result = audit(args.document, args.template, expected)
        save_new(args.report, result)
        result = {k: result[k] for k in ('passed', 'counts', 'errors', 'limitations')}
        code = 0 if result['passed'] else 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())

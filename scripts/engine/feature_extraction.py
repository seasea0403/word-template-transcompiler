"""Prepare neutral DOCX features and assemble agent-authored annotations, read-only."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
from inspect_docx import paths as xml_paths, own_text, xml_or_none

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
Q = '{' + W + '}'
HERE = Path(__file__).resolve().parent
COLLECTIONS = ('regions', 'roles', 'rules', 'slots', 'preservation', 'relations', 'checks', 'conflicts', 'issues', 'extensions')
# Chinese named sizes are a unit glossary, not a template or school preset.
NAMED_SIZES = {'初号':42, '小初':36, '一号':26, '小一':24, '二号':22, '小二':18,
               '三号':16, '小三':15, '四号':14, '小四':12, '五号':10.5, '小五':9,
               '六号':7.5, '小六':6.5, '七号':5.5, '八号':5}
SIZE_PATTERN = re.compile(r'小[初一二三四五六七八九](?:号)?|[初一二三四五六七八九]号')
SPACE_PATTERN = re.compile(r'(?:空|留)[一二三四五六七八九十两0-9]+(?:个)?(?:空)?(?:行|格|字符)')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def new_dir(path):
    if path.exists():
        raise ValueError('Use a new output directory; previous evidence is immutable')
    path.mkdir(parents=True)

def attrs(xml):
    if not xml:
        return {}
    root = ET.fromstring(xml)
    return {node.tag.removeprefix(Q): {key.removeprefix(Q): value for key, value in node.attrib.items()}
            for node in root}

def direct_format(xml):
    raw = attrs(xml)
    out = {'raw': raw, 'scope': 'direct_only_not_effective'}
    for source, target, divisor in [('sz', 'size_pt', 2), ('szCs', 'complex_script_size_pt', 2)]:
        if 'val' in raw.get(source, {}):
            out[target] = float(raw[source]['val']) / divisor
    spacing = raw.get('spacing', {})
    if 'line' in spacing:
        mode = spacing.get('lineRule', 'auto')
        out['line_spacing'] = {'mode': 'multiple' if mode == 'auto' else mode,
                               'amount': float(spacing['line']) / (240 if mode == 'auto' else 20),
                               'basis': 'OOXML lineRule; absent lineRule defaults to auto'}
    return out

def effective_sample_format(paragraph_xml, styles_xml):
    """Resolve the inheritance chain without classifying the paragraph's role."""
    from lxml import etree as LE
    from paragraph_roles import resolve_sample
    try:
        return resolve_sample(LE.fromstring(paragraph_xml.encode()),LE.fromstring(styles_xml.encode()))
    except ValueError as exc:
        return {'state':'review_required','reason':str(exc)}

def cues(text):
    sizes = []
    for match in SIZE_PATTERN.finditer(text):
        name = match.group().removesuffix('号')
        key = name if name.startswith('小') else name + '号'
        sizes.append({'text': match.group(), 'start': match.start(), 'end': match.end(),
                      'points': NAMED_SIZES.get(key), 'status': 'lexical_only_scope_unresolved'})
    return {'size_mentions': sizes,
            'font_mentions': [{'text': m.group(), 'start': m.start(), 'end': m.end()}
                              for m in re.finditer(r'Times New Roman|黑体|宋体|楷体(?:_GB2312)?|仿宋(?:_GB2312)?', text)],
            'space_mentions': [{'text': m.group(), 'start': m.start(), 'end': m.end()}
                               for m in SPACE_PATTERN.finditer(text)],
            'bracket_spans': [{'text': m.group(), 'start': m.start(), 'end': m.end()}
                              for m in re.finditer(r'[（(][^（）()]*[）)]', text)],
            'warning': 'Cues do not identify roles, instruction scope, deletion or approved rules'}

def section_properties(xml):
    raw = attrs(xml)
    derived = {}
    for node, name in [('pgSz', 'page_size'), ('pgMar', 'margins')]:
        derived[name] = {key: {'raw_twip': value, 'mm': float(value)*25.4/1440}
                         for key, value in raw.get(node, {}).items() if key in ('w','h','top','bottom','left','right','header','footer','gutter')}
    root = ET.fromstring(xml)
    children = [{'tag':node.tag.removeprefix(Q), 'attributes':dict(node.attrib)} for node in root]
    return {'raw': raw, 'child_records':children, 'derived': derived,
            'warning': 'sectPr terminates its section; no region or page numbering start inferred'}

def verify_survey(source, survey_path):
    data = read_json(survey_path)
    original = source.read_bytes()
    if digest(original) != data['source_sha256'] or len(original) != data['source_bytes']:
        raise ValueError('Cached survey does not match source')
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != {x['path'] for x in data['parts']}:
            raise ValueError('Package inventory mismatch')
        if sum(info.file_size for info in archive.infolist()) > 64*1024*1024:
            raise ValueError('Package exceeds bounded inspection size')
        nodes = {}
        for part in data['parts']:
            name = part['path'].replace('\\', '/')
            if name.startswith('/') or '..' in PurePosixPath(name).parts or ':' in name:
                raise ValueError('Unsafe package part')
            raw = archive.read(part['path'])
            if digest(raw) != part['sha256'] or len(raw) != part['bytes']:
                raise ValueError('Cached part hash mismatch')
            if name.endswith('.xml'):
                nodes.update({(part['path'],address):node for node,address in xml_paths(ET.fromstring(raw))})
        for paragraph in data['paragraphs']:
            node=nodes.get((paragraph['part'],paragraph['xml_path']))
            if node is None or digest(ET.tostring(node,encoding='utf-8')) != paragraph['guard_sha256']:
                raise ValueError('Cached paragraph location or node hash mismatch')
            actual_runs=[{'text':own_text(r),'direct_run_properties':xml_or_none(r.find(Q+'rPr'))} for r in node.findall(Q+'r')]
            if own_text(node)!=paragraph['text'] or xml_or_none(node.find(Q+'pPr'))!=paragraph['direct_paragraph_properties'] or actual_runs!=paragraph['runs']:
                raise ValueError('Cached paragraph facts do not match source XML')
        for item in data['sections']+data['structures']:
            node=nodes.get((item['part'],item['xml_path']))
            if node is None or xml_or_none(node)!=item['xml']:
                raise ValueError('Cached structure does not match source XML')
    if source.read_bytes() != original:
        raise ValueError('Source changed during preparation')
    return data

def prepare(source, survey_path, out_dir):
    data = verify_survey(source, survey_path)
    with zipfile.ZipFile(source) as archive:
        source_nodes={}
        for name in {p['part'] for p in data['paragraphs']}:
            source_nodes.update({(name,address):node for node,address in xml_paths(ET.fromstring(archive.read(name)))})
        styles_xml=archive.read('word/styles.xml').decode('utf8') if 'word/styles.xml' in archive.namelist() else None
    features = []
    for index, paragraph in enumerate(data['paragraphs'], 1):
        record = {'id': f'P{index:03d}', 'kind': 'paragraph', **paragraph}
        record['direct_format'] = direct_format(paragraph['direct_paragraph_properties'])
        record['effective_sample_format']=effective_sample_format(ET.tostring(source_nodes[(paragraph['part'],paragraph['xml_path'])],encoding='unicode'),styles_xml) if styles_xml else {'state':'review_required','reason':'Missing styles part; effective inheritance unavailable'}
        record['run_formats'] = [{'text': r['text'], 'properties': direct_format(r['direct_run_properties'])} for r in paragraph['runs']]
        record['cues'] = cues(paragraph['text'])
        features.append(record)
    for prefix, kind, collection in [('S','section','sections'), ('X','structure','structures')]:
        for index, item in enumerate(data[collection], 1):
            record = {'id': f'{prefix}{index:03d}', 'kind': kind, **item}
            record['guard_sha256'] = item.get('guard_sha256') or digest(item['xml'].encode('utf-8'))
            if kind == 'section':
                record['properties'] = section_properties(item['xml'])
            features.append(record)
    for index, item in enumerate(data['parts'], 1):
        features.append({'id':f'M{index:03d}', 'kind':'part', 'part':item['path'],
                         'guard_sha256':item['sha256'], 'bytes':item['bytes']})
    statistics = {**data['stats'], 'media_files':sum(p['path'].startswith('word/media/') and not p['path'].endswith('/') for p in data['parts']),
                  'directory_entries':sum(p['path'].endswith('/') for p in data['parts'])}
    result = {'schema_version':'template-features/1', 'source':str(source.resolve()),
              'source_sha256':data['source_sha256'], 'survey':str(survey_path.resolve()),
              'survey_sha256':digest(survey_path.read_bytes()), 'stats':statistics, 'features':features,
              'relationships':data['relationships'], 'styles':data['styles'], 'supporting_xml':data['supporting_xml'],
              'render_review':'not_performed', 'limitations':data['limitations']}
    new_dir(out_dir)
    write_json(out_dir/'features.json', result)
    lines = ['# 模板特征审阅材料', '', '只读事实与词面线索，不是已批准的规则。完整文字与结构在 features.json；这里不推断实际页码。', '',
             f"源 SHA256：{data['source_sha256']}", '', '## 文字与位置', '']
    for f in features:
        if f['kind'] == 'paragraph':
            lines += [f"### {f['id']}", '', f"部件：{f['part']}；位置：`{f['xml_path']}`", '',
                      f['text'] if f['text'].strip() else '（空段，不能据此判定可删除）', '',
                      '直接段落属性：`'+json.dumps(f['direct_format'], ensure_ascii=False)+'`', '']
    lines += ['## 节属性', '']
    for f in features:
        if f['kind'] == 'section':
            lines += [f"### {f['id']}", '', '```json', json.dumps(f['properties'], ensure_ascii=False, indent=2), '```', '']
    (out_dir/'review-packet.md').write_text('\n'.join(lines), encoding='utf-8')
    return {'feature_count':len(features), 'stats':statistics, 'source_unchanged':True}

def target_for_ids(ids):
    return {'role_id':None, 'region_ids':[], 'locator_ids':ids, 'language_tags':[], 'occurrence':'all'}

def expand_target(value):
    if isinstance(value, dict):
        return value
    kind, ident = value.split(':', 1)
    result = target_for_ids([])
    if kind == 'role':
        result['role_id'] = ident
    elif kind == 'region':
        result['region_ids'] = [ident]
    elif kind == 'feature':
        result['locator_ids'] = ['loc-' + ident]
    else:
        raise ValueError('Unknown declarative target kind')
    return result

def assemble(features_path, annotation_path, out_dir, visual_review_path=None):
    snapshot_bytes = features_path.read_bytes()
    data, ann = json.loads(snapshot_bytes), read_json(annotation_path)
    if ann.get('schema_version') != 'feature-annotations/1' or ann.get('feature_snapshot_sha256') != digest(snapshot_bytes):
        raise ValueError('Annotations must bind to the exact feature snapshot')
    source = Path(data['source'])
    if digest(source.read_bytes()) != data['source_sha256'] or digest(Path(data['survey']).read_bytes()) != data['survey_sha256']:
        raise ValueError('Source or survey changed after preparation')
    by_id = {f['id']:f for f in data['features']}
    if len(by_id) != len(data['features']):
        raise ValueError('Duplicate feature ID')
    contract = read_json(HERE/'blank.json')
    contract['state'] = 'review_required'
    contract['sources'] = [{'id':'template', 'kind':'template', 'path':data['source'], 'sha256':data['source_sha256']},
                           {'id':'survey', 'kind':'other', 'path':data['survey'], 'sha256':data['survey_sha256']},
                           {'id':'annotations', 'kind':'other', 'path':str(annotation_path.resolve()), 'sha256':digest(annotation_path.read_bytes())}]
    for f in data['features']:
        contract['locators'].append({'id':'loc-'+f['id'], 'source_id':'template',
            'kind':'file' if f['kind']=='part' else 'xml_path', 'part':f['part'],
            'selector':f['part'] if f['kind']=='part' else f['xml_path'],
            'expected_matches':1, 'guard_sha256':f['guard_sha256']})
    permitted_kinds = {'explicit_instruction','sample_format','structural_fact'}
    for e in ann['evidence']:
        f = by_id[e['feature_id']]
        if e['kind'] not in permitted_kinds:
            raise ValueError('This stage cannot certify rendering, human decisions or external requirements')
        quote = e.get('quote')
        if quote is not None and (not quote or quote not in f.get('text','')):
            raise ValueError('Evidence quote is absent from referenced feature: '+e['id'])
        if e['kind']=='explicit_instruction' and quote is None:
            raise ValueError('Explicit instruction evidence requires an exact quote')
        observed = quote if quote is not None else json.dumps(f.get('properties') or
                    ({'paragraph':f['direct_format'], 'runs':f['run_formats']} if f['kind']=='paragraph' else None) or
                    {'kind':f['kind'], 'part':f['part'], 'xml':f.get('xml'), 'bytes':f.get('bytes'), 'sha256':f['guard_sha256']}, ensure_ascii=False)
        contract['evidence'].append({'id':e['id'], 'source_id':'template', 'locator_ids':['loc-'+f['id']],
                                   'kind':e['kind'], 'observation':observed, 'limitations':e['limitations']})
    for name in COLLECTIONS:
        contract[name] = ann.get(name, [])
        for item in contract[name]:
            for field in ('target','from','to'):
                if field in item:
                    item[field] = expand_target(item[field])
    classifications = ann.get('classifications', [])
    classified = set()
    evidence_ids = {x['id'] for x in contract['evidence']}
    for c in classifications:
        if c['feature_id'] not in by_id or c['feature_id'] in classified:
            raise ValueError('Unknown or duplicate classified feature')
        if not c.get('purpose') or not c.get('category') or not c.get('evidence_ids') or not set(c['evidence_ids']) <= evidence_ids:
            raise ValueError('Classification lacks purpose, category or evidence')
        classified.add(c['feature_id'])
    missing = [f['id'] for f in data['features'] if f['id'] not in classified]
    contract['coverage'] = {'inventory_complete':False, 'unclassified_locator_ids':['loc-'+i for i in missing],
                            'render_review':'not_performed', 'evidence_ids':[]}
    visual_status = 'not_performed'
    if visual_review_path:
        visual=read_json(visual_review_path)
        receipt_path=Path(visual['render_receipt'])
        if visual.get('schema_version')!='template-visual-review/1' or visual['source_sha256']!=data['source_sha256'] or digest(receipt_path.read_bytes())!=visual['render_receipt_sha256']:
            raise ValueError('Visual review is not bound to this source and render receipt')
        rendered=read_json(receipt_path)
        if rendered['source_sha256']!=data['source_sha256'] or rendered['return_code']!=0 or not rendered['pages']:
            raise ValueError('No successful matching template render')
        pages={p['page']:p for p in rendered['pages']}
        reviewed=set(visual['reviewed_pages'])
        if len(reviewed)!=len(visual['reviewed_pages']) or not reviewed or not reviewed<=set(pages):
            raise ValueError('Invalid reviewed page list')
        for p in rendered['pages']:
            if digest(Path(p['path']).read_bytes())!=p['sha256']:
                raise ValueError('Rendered page changed after receipt')
        observations=visual['observations']
        if {o['page'] for o in observations}!=reviewed:
            raise ValueError('Each reviewed page requires an observation')
        for page in sorted(reviewed):
            p=pages[page]; ident=f'render-page-{page}'
            contract['sources'].append({'id':ident,'kind':'render','path':p['path'],'sha256':p['sha256']})
            contract['locators'].append({'id':'loc-'+ident,'source_id':ident,'kind':'file','part':None,
                                        'selector':p['path'],'expected_matches':1,'guard_sha256':p['sha256']})
            eid='e-'+ident
            text='; '.join(o['description'] for o in observations if o['page']==page)
            if not text.strip(): raise ValueError('Empty visual observation')
            contract['evidence'].append({'id':eid,'source_id':ident,'locator_ids':['loc-'+ident],
                                        'kind':'render_observation','observation':text,'limitations':visual['limitations']})
            contract['coverage']['evidence_ids'].append(eid)
        visual_status='complete' if reviewed==set(pages) else 'partial'
        contract['coverage']['render_review']=visual_status
    # Always retain conservative stage blockers. This assembler cannot approve a contract.
    first_locator = contract['locators'][0]['id']
    for ident, category, text in [('stage-visual','layout_risk','尚未渲染和逐页审阅，不确认封面范围、页码或实际布局'),
                                  ('stage-coverage','coverage_gap','本轮只完成部分语义提取；仍需审阅完整格式继承、结构和槽位'),
                                  ('stage-backend','unsupported_feature','没有已验证的 DOCX 生成后端，当前只展示模板契约草案')]:
        if ident=='stage-visual' and visual_status=='complete':
            continue
        if ident=='stage-visual' and visual_status=='partial':
            text='仅部分源模板页面已审阅，不批准完整页面布局'
        contract['issues'].append({'id':ident, 'target':target_for_ids([first_locator]), 'category':category,
                                  'severity':'blocking', 'description':text, 'resolved':False, 'resolution':None, 'evidence_ids':[]})
    new_dir(out_dir)
    write_json(out_dir/'contract.draft.json', contract)
    def pretty(value):
        return json.dumps(value, ensure_ascii=False).replace('|','\\|')
    evidence = {e['id']:e for e in contract['evidence']}
    lines = ['# 模板识别试提取结果', '', '本报告由通用组装工具生成；语义分类与规则由 Agent 阅读本次证据后标注，未经用户批准。', '',
             f"源文件哈希：{data['source_sha256']}", '',
             f"共 {len(data['features'])} 个特征；本轮语义分类 {len(classified)} 个；未分类 {len(missing)} 个。未分类不等于不存在或可删除。", '',
             f'源模板页面审阅状态：{visual_status}。结构草案，不是成稿验收结果。没有修改原模板，没有生成成稿。', '', '## 区域与角色', '']
    for r in contract['regions']:
        lines += [f"- 区域 `{r['id']}`：{r['semantic_role']}（仅按源位置界定，非实际页码）。"]
    for r in contract['roles']:
        lines += [f"- 角色 `{r['id']}`：{r['semantic_role']}；类型 {r['kind']}；层级 {r['level']}。"]
    lines += ['', '## 属性级候选规则', '', '| 规则 | 对象 | 属性 | 值 | 决策 | 依据与取舍 |', '| --- | --- | --- | --- | --- | --- |']
    for r in contract['rules']:
        t = r['target']
        obj = t['role_id'] or ','.join(t['region_ids'] or t['locator_ids'])
        refs = '; '.join(e['id']+': '+e['observation'][:130] for e in (evidence[i] for i in r['evidence_ids']))
        lines += [f"| {r['id']} | {obj} | {r['property']} | {pretty(r['value'])} | {r['decision']} | {refs.replace('|','/')}；{r['rationale'].replace('|','/')} |"]
    lines += ['', '## 保留与替换', '', '| 槽位 | 位置 | 绑定 | 动作 | 缺失／溢出 |', '| --- | --- | --- | --- | --- |']
    for s in contract['slots']:
        lines += [f"| {s['id']} | {', '.join(s['locator_ids'])} | {s['binding']} | {s['action']} / {s['edit_scope']} | {s['missing_policy']} / {s['overflow_policy']} |"]
    for p in contract['preservation']:
        lines += ['', f"保留 `{p['id']}`：{p['policy']}；部件 {', '.join(p['part_paths'])}；位置 {', '.join(p['locator_ids'])}。"]
    lines += ['', '## 冲突与需要你审阅的问题', '']
    for c in contract['conflicts']:
        lines += [f"- 冲突 `{c['id']}`：{c['reason']}；候选 {', '.join(c['rule_ids'])}；已解决：{c['resolved']}。"]
    for issue in contract['issues']:
        lines += [f"- `{issue['id']}`（{issue['severity']}）：{issue['description']}"]
    lines += ['', '## 源模板页面观察', '']
    for e in contract['evidence']:
        if e['kind']=='render_observation':
            lines += [f"- `{e['id']}`：{e['observation']}"]
    lines += ['', '## 分类记录', '', '| 特征 | 类别 | 解释 |', '| --- | --- | --- |']
    for c in classifications:
        lines += [f"| {c['feature_id']} | {c['category']} | {c['purpose'].replace('|','/')} |"]
    lines += ['', '## 调试边界', '', '没有计算完整有效格式或判断全部说明范围。关键词只是候选；空格类别、留白基准、封面视觉边界与图形用途仍需审阅。检查定义不是已经通过的成稿检查。']
    (out_dir/'review.md').write_text('\n'.join(lines), encoding='utf-8')
    receipt = {'features_sha256':digest(snapshot_bytes), 'annotations_sha256':digest(annotation_path.read_bytes()),
               'contract_sha256':digest((out_dir/'contract.draft.json').read_bytes()), 'source_unchanged':True,
               'classified_features':len(classified), 'unclassified_features':len(missing),
               'rules':len(contract['rules']), 'slots':len(contract['slots']), 'render_review':visual_status,
               'semantic_method':'Agent-authored annotations; deterministic assembly, not automatic semantic extraction'}
    write_json(out_dir/'assembly-receipt.json', receipt)
    return receipt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('prepare')
    p.add_argument('--source',type=Path,required=True); p.add_argument('--survey',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    p = subs.add_parser('assemble')
    p.add_argument('--features',type=Path,required=True); p.add_argument('--annotations',type=Path,required=True)
    p.add_argument('--visual-review',type=Path,help='Actual page observations bound to a successful render receipt')
    p.add_argument('--out-dir',type=Path,required=True)
    args = parser.parse_args()
    result = prepare(args.source,args.survey,args.out_dir) if args.command=='prepare' else assemble(args.features,args.annotations,args.out_dir,args.visual_review)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

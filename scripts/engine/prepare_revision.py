"""Apply a reviewed source-bound delta to an immutable previous execution contract."""
import argparse, copy, json, shutil
from pathlib import Path
from blank_flow import extract

def merge(dst, delta):
    for k,v in delta.items():
        if isinstance(v,dict) and isinstance(dst.get(k),dict):merge(dst[k],v)
        else:dst[k]=copy.deepcopy(v)

def prepare(previous,plan_path,work):
    if work.exists():raise ValueError('Fresh revision directory required')
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    if not plan.get('rationale') or not plan.get('evidence_ids'):raise ValueError('Unreviewed revision')
    contract=json.loads((previous/'contract.json').read_text(encoding='utf-8'))
    features=json.loads(Path(contract['features']).read_text(encoding='utf-8'))
    byid={x['id'] for x in features['features']}
    if set(plan['evidence_ids'])-byid:raise ValueError('Unknown source evidence')
    cover=json.loads(Path(contract['cover_bindings']).read_text(encoding='utf-8'))
    for edit in plan.get('cover_action_replacements',[]):
        matches=[i for i,x in enumerate(cover['actions']) if x.get('feature_id')==edit['feature_id']]
        if len(matches)!=1:raise ValueError('Ambiguous cover binding')
        cover['actions'][matches[0]]=edit
    for edit in plan.get('cover_action_additions',[]):
        if any(x.get('feature_id')==edit['feature_id'] for x in cover['actions']):raise ValueError('Duplicate cover action')
        cover['actions'].append(edit)
    merge(contract,plan.get('contract_delta',{}))
    contract['extra_roles']+=plan.get('extra_roles',[])
    work.mkdir(parents=True)
    contract['cover_bindings']=str((work/'reviewed-cover-bindings.json').resolve())
    (work/'reviewed-cover-bindings.json').write_text(json.dumps(cover,ensure_ascii=False,indent=2),encoding='utf-8')
    (work/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding='utf-8')
    (work/'blank-cue-inventory.json').write_text(json.dumps(extract(features),ensure_ascii=False,indent=2),encoding='utf-8')
    (work/'revision-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    (work/'artifact.md').write_text((previous/'artifact.md').read_text(encoding='utf-8')+'\n\n## Reviewed revision\n'+plan['rationale']+'\n\n'+plan.get('scope_notes',''),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('previous-run','plan','run-dir'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();prepare(a.previous_run,a.plan,a.run_dir)

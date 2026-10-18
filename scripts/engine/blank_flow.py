"""Source-bound blank-line cues. Semantic anchors are reviewed, not guessed.

Explicit local size > earlier scoped 下同 size > cue paragraph sample size.
Physical line height/grid come from the cue sample, never adjacent title size.
"""
import copy, re
from paragraph_roles import compile_role

COUNTS={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6}
SIZES={'初号':42,'小初':36,'一号':26,'小一':24,'二号':22,'小二':18,
       '三号':16,'小三':15,'四号':14,'小四':12,'五号':10.5,'小五':9}

def extract(features):
    cues=[]; scoped=None
    for f in features['features']:
        txt=f.get('text','')
        m=re.fullmatch(r'\s*[（(]空([一二两三四五六\d]+)行([^）)]*)[）)]\s*',txt)
        if not m: continue
        count=int(m[1]) if m[1].isdigit() else COUNTS[m[1]]
        size_match=re.search(r'小初|初号|小[一二三四五]|[一二三四五]号',m[2])
        explicit=SIZES[size_match[0]] if size_match else None
        if explicit is not None and '下同' in m[2]: scoped={'pt':explicit,'id':f['id']}
        size=explicit or (scoped['pt'] if scoped else None)
        sample=copy.deepcopy(f['effective_sample_format'])
        for key in ('outlineLvl','numPr','sectPr','tabs','pageBreakBefore','keepNext','keepLines'):
            sample['paragraph'].pop(key,None)
        # Instruction ink/emphasis does not describe blank layout.
        overrides={'run':{'color':{'val':'000000'},'b':{'val':'0'},'bCs':{'val':'0'}},
                   'paragraph':{'spacing':{**sample['paragraph'].get('spacing',{}),'before':'0','after':'0'},
                                'ind':{'left':'0','firstLine':'0','firstLineChars':'0'}}}
        if size: overrides['run'].update({'sz':{'val':str(int(size*2))},'szCs':{'val':str(int(size*2))}})
        cues.append({'id':f['id'],'count':count,'text':txt,
                     'evidence_ids':sorted(set([f['id']]+([scoped['id']] if scoped and not explicit else []))),
                     'size_origin':'explicit' if explicit else 'scoped' if scoped else 'sample',
                     'properties':compile_role(sample,overrides)})
    return {c['id']:c for c in cues}

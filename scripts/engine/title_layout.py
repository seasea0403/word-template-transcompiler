"""Template-neutral one/two-slot title planner. Measurements are caller supplied."""
import math

def distribute_title(text, boundaries, capacities, measure, safety=0.94, protected_terms=()):
    if not text or len(capacities) not in (1,2) or not 0<safety<=1:
        raise ValueError('Invalid title layout input')
    if any(not math.isfinite(x) or x<=0 for x in capacities): raise ValueError('Invalid slot width')
    width=measure(text)
    if not math.isfinite(width) or width<0: raise ValueError('Invalid measurement')
    if width<=capacities[0]*safety:
        return {'lines':[text]+([''] if len(capacities)==2 else []),'mode':'one_slot','widths':[width]}
    if len(capacities)==1: raise ValueError('Title exceeds approved single slot')
    candidates=[]
    protected=set()
    for term in protected_terms:
        if not isinstance(term,str) or not term: raise ValueError('Invalid protected term')
        start=0
        while (start:=text.find(term,start))!=-1:
            protected.update(range(start+1,start+len(term))); start+=1
    closing='，。；：、！？,.!?;:）)]】》'
    opening='（([【《'
    for index in sorted(set(boundaries)):
        if not isinstance(index,int) or not 0<index<len(text): continue
        if index in protected: continue
        left,right=text[:index],text[index:]
        if right[0] in closing or left[-1] in opening: continue
        widths=[measure(left),measure(right)]
        if any(not math.isfinite(x) or x<0 for x in widths): raise ValueError('Invalid measurement')
        ratios=[widths[i]/capacities[i] for i in range(2)]
        if max(ratios)>safety: continue
        # Word segmentation is heuristic, not a guarantee of semantic coherence.
        penalty=0.45 if right[0] in '的地得与和及' else 0
        score=abs(ratios[0]-ratios[1])+penalty
        candidates.append((score,index,[left,right],widths))
    if not candidates: raise ValueError('No token-safe two-slot layout fits; manual review required')
    _,index,lines,widths=min(candidates)
    assert ''.join(lines)==text
    return {'lines':lines,'mode':'two_slots','split_index':index,'widths':widths,'safety':safety}

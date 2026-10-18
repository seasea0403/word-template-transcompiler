"""Resolve sample paragraph formatting, then materialize role-specific writing properties.

No school names or paragraph IDs. Callers bind semantically reviewed sample nodes.
Unsupported theme fonts are reported, not guessed.
"""
import copy
from lxml import etree as E
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def merge(target, props):
    if props is None: return
    for n in props:
        key=n.tag.removeprefix(W)
        attrs={k.removeprefix(W):v for k,v in n.attrib.items()}
        current=target.setdefault(key,{})
        if key=='rFonts':
            for script,theme in [('ascii','asciiTheme'),('hAnsi','hAnsiTheme'),('eastAsia','eastAsiaTheme'),('cs','cstheme')]:
                if script in attrs: current.pop(theme,None)
                if theme in attrs: current.pop(script,None)
        current.update(attrs)

def resolve_sample(p,styles,run=None):
    byid={s.get(W+'styleId'):s for s in styles.findall(W+'style')}
    pr=p.find(W+'pPr'); sid=pr.find(W+'pStyle') if pr is not None else None
    default=next((s.get(W+'styleId') for s in byid.values() if s.get(W+'type')=='paragraph' and s.get(W+'default')=='1'),None)
    sid=sid.get(W+'val') if sid is not None else default
    chain=[]; seen=set()
    while sid:
        if sid in seen: raise ValueError('Style inheritance cycle')
        if sid not in byid: raise ValueError('Missing style '+sid)
        seen.add(sid); s=byid[sid]; chain.append(s)
        parent=s.find(W+'basedOn'); sid=parent.get(W+'val') if parent is not None else None
    pp={}; rp={}; defaults=styles.find(W+'docDefaults')
    if defaults is not None:
        merge(pp,defaults.find(W+'pPrDefault/'+W+'pPr')); merge(rp,defaults.find(W+'rPrDefault/'+W+'rPr'))
    for s in reversed(chain): merge(pp,s.find(W+'pPr')); merge(rp,s.find(W+'rPr'))
    merge(pp,pr)
    normalizations=[]
    direct_ind=pr.find(W+'ind') if pr is not None else None
    if direct_ind is not None and direct_ind.get(W+'firstLine') is not None and direct_ind.get(W+'firstLineChars') in (None,'0'):
        if int(direct_ind.get(W+'firstLine'))>0:
            # Physical sample indentation must not be cancelled by inherited char units.
            pp['ind'].pop('firstLineChars',None)
            normalizations.append('Direct positive physical first-line indent wins over inherited/zero character indent')
    r=run if run is not None else next((r for r in p.findall(W+'r') if ''.join(r.itertext()).strip()),None)
    if r is not None:
        rpr=r.find(W+'rPr'); cs=rpr.find(W+'rStyle') if rpr is not None else None
        if cs is not None:
            style=byid.get(cs.get(W+'val'))
            if style is None: raise ValueError('Missing character style')
            if style.find(W+'basedOn') is not None: raise ValueError('Character style chain requires explicit review')
            merge(rp,style.find(W+'rPr'))
        merge(rp,rpr)
    pp.pop('pStyle',None); pp.pop('rPr',None); rp.pop('rStyle',None)
    # Absence means Word's on-by-default grid behavior; retain this explicitly.
    pp.setdefault('snapToGrid',{'val':'1'})
    return {'paragraph':pp,'run':rp,'style_chain':[s.get(W+'styleId') for s in reversed(chain)],'normalizations':normalizations,
            'theme_unresolved':{k:v for k,v in rp.get('rFonts',{}).items() if 'theme' in k.lower()}}

def materialize_props(kind,values):
    p=E.Element(W+kind)
    for tag,attrs in values.items():
        if tag in ('tabs','numPr','sectPr'): continue # complex nodes need explicit components
        n=E.SubElement(p,W+tag)
        for key,value in attrs.items(): n.set(W+key,str(value))
    return p

def compile_role(sample,overrides=None):
    """Scoped overrides must be evidence-backed, never a global paragraph preset."""
    role=copy.deepcopy(sample)
    for area,values in (overrides or {}).items():
        for tag,attrs in values.items(): role[area][tag]=dict(attrs)
    # Explicit script fonts resolve theme aliases for authoring a standalone role.
    fonts=role['run'].get('rFonts',{})
    for script,theme in [('ascii','asciiTheme'),('hAnsi','hAnsiTheme'),('eastAsia','eastAsiaTheme'),('cs','cstheme')]:
        if script in fonts: fonts.pop(theme,None)
    if any('theme' in k.lower() for k in fonts): raise ValueError('Resolve theme font before writing')
    return role

def apply_role(p,role,include_hyperlink_runs=False):
    old=p.find(W+'pPr'); new=materialize_props('pPr',role['paragraph'])
    if old is not None:
        # Preserve structural paragraph boundaries/complex tabs independently.
        for tag in ('sectPr','tabs','numPr'):
            n=old.find(W+tag)
            if n is not None: new.append(copy.deepcopy(n))
        p.replace(old,new)
    else: p.insert(0,new)
    runs=list(p.findall(W+'r'))
    if include_hyperlink_runs:
        runs.extend(r for h in p.findall(W+'hyperlink') for r in h.findall(W+'r'))
    for r in runs:
        if r.find(W+'footnoteReference') is not None: continue
        old=r.find(W+'rPr'); new=materialize_props('rPr',role['run'])
        if old is not None:
            if r.getparent().tag==W+'hyperlink':
                # Materialize destination formatting, not foreign character-style IDs.
                # Preserve semantic superscript/emphasis independently of link styling.
                for tag in ('vertAlign','i','iCs','b','bCs'):
                    n=old.find(W+tag)
                    if n is not None:
                        present=new.find(W+tag)
                        if present is not None: new.remove(present)
                        new.append(copy.deepcopy(n))
            r.replace(old,new)
        else: r.insert(0,new)

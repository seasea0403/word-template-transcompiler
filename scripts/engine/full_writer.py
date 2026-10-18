"""One source-bound manuscript/template writer, with run-local agent interpretation.

No school/case/name/hash dispatch. Contract is an evidence product of the current
run, not a tool preset. Pandoc is a content converter, never a template saver.
"""
import argparse, copy, json, re, subprocess, zipfile, posixpath
from pathlib import Path
from collections import Counter
from lxml import etree as E
from manuscript_ir import parse, sha, text, walk
from cover_adapter import generate as write_cover
from compile_role_bindings import compile_bindings
from paragraph_roles import compile_role, apply_role, materialize_props, W
from write_pipeline import verify_review
from inspect_docx import paths
from blank_flow import extract as extract_blank_cues
from toc_component import toc_left_indent

M='{http://schemas.openxmlformats.org/officeDocument/2006/math}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG='{http://schemas.openxmlformats.org/package/2006/relationships}'
CT='{http://schemas.openxmlformats.org/package/2006/content-types}'
SPACE='{http://www.w3.org/XML/1998/namespace}space'

def xml(n): return E.tostring(n,encoding='UTF-8',xml_declaration=True,standalone=True)
def plain(n): return ''.join(t.text or '' for t in n.iter(W+'t'))
def node(parent,tag,**attrs):
    n=E.SubElement(parent,W+tag)
    for k,v in attrs.items(): n.set(W+k,str(v))
    return n
def put(pr,tag,attrs):
    old=pr.find(W+tag)
    if old is not None: pr.remove(old)
    return node(pr,tag,**attrs)
def run(p,value,role=None):
    r=node(p,'r')
    if role: r.append(materialize_props('rPr',role['run']))
    t=node(r,'t'); t.text=value; t.set(SPACE,'preserve'); return r
def paragraph(value,role):
    p=E.Element(W+'p'); pr=materialize_props('pPr',role['paragraph']); p.append(pr)
    if not value: pr.append(materialize_props('rPr',role['run']))
    run(p,value,role); return p
def field(p,instruction,value,role):
    f=node(p,'fldSimple',instr=' '+instruction+' '); run(f,value,role); return f
def writezip(path,parts):
    if path.exists(): raise ValueError('Fresh output required: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
        for k,v in parts.items(): z.writestr(k,v)
def readzip(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or any('..' in n.split('/') or n.startswith('/') for n in names):
            raise ValueError('Unsafe/duplicate package part')
        return {n:z.read(n) for n in names}

def replace_equation_links(paragraph_node,equations,role):
    """Resolve actual equation IDs; retain unrelated hyperlinks."""
    for h in list(paragraph_node.iter(W+'hyperlink')):
        ident=h.get(W+'anchor')
        if ident not in equations:
            continue
        if h.getparent() is not paragraph_node:
            raise ValueError('Nested equation link requires a dedicated adapter')
        equation=equations[ident];at=paragraph_node.index(h);paragraph_node.remove(h)
        paragraph_node.insert(at,run(E.Element(W+'p'),'式(',role))
        holder=E.Element(W+'p')
        paragraph_node.insert(at+1,field(holder,'REF '+equation['anchor']+' \\h',equation['number'],role))
        paragraph_node.insert(at+2,run(E.Element(W+'p'),')',role))

class Writer:
    def __init__(self,manuscript,template,output,work,pandoc,node_bin):
        self.manuscript,self.template,self.output,self.work=manuscript,template,output,work
        self.pandoc,self.node_bin=pandoc,node_bin
        self.contract=json.loads((work/'contract.json').read_text(encoding='utf-8'))
        if not (work/'artifact.md').exists(): raise ValueError('Missing complete scoped artifact contract')
        self.c=self.contract
        if self.c['source_sha256']!=sha(template): raise ValueError('Template contract mismatch')
        self.review,self.features=verify_review(template,Path(self.c['review']))
        self.f={x['id']:x for x in self.features['features']}
        self.blank_cues=extract_blank_cues(self.features)
        self.original=readzip(template); self.source_root=E.fromstring(self.original['word/document.xml'])
        self.locations={p:n for n,p in paths(self.source_root)}
        self.bid=10000; self.targets=[]; self.events=[]; self.cite_count=0
        self.roles={}; self.chapter=0; self.counter=Counter(); self.equations={}
    def sample(self,ident):
        f=self.f[ident]
        if f['part']!='word/document.xml': raise ValueError('Unsupported sample part')
        return self.locations[f['xml_path']]
    def role(self,name): return self.roles[name]
    def anchor(self,p,name):
        self.bid+=1
        pr=p.find(W+'pPr'); p.insert(1 if pr is not None else 0,E.Element(W+'bookmarkStart',{W+'id':str(self.bid),W+'name':name}))
        node(p,'bookmarkEnd',id=self.bid); return name
    def apply(self,p,name):
        # Imported paragraph/run styles are not defined by the template.
        for n in list(p.iter()):
            if n.tag in (W+'pStyle',W+'rStyle',W+'bookmarkStart',W+'bookmarkEnd'):
                n.getparent().remove(n)
        emphasis=[]
        for r in p.findall(W+'r'):
            rp=r.find(W+'rPr'); saved=[]
            if rp is not None:
                saved=[copy.deepcopy(n) for n in rp if n.tag in (W+'i',W+'vertAlign')]
            emphasis.append((r,saved))
        apply_role(p,self.role(name),include_hyperlink_runs=True)
        for r,saved in emphasis:
            rp=r.find(W+'rPr')
            if rp is None: rp=node(r,'rPr')
            for s in saved: put(rp,s.tag.removeprefix(W),{k.removeprefix(W):v for k,v in s.attrib.items()})
        for r in p.iter(W+'r'):
            if r.find(W+'footnoteReference') is not None:
                old=r.find(W+'rPr')
                if old is not None:r.remove(old)
                rp=node(r,'rPr'); node(rp,'vertAlign',val='superscript')
        for mr in p.iter(M+'r'):
            old=mr.find(W+'rPr')
            if old is not None: mr.remove(old)
            rp=E.SubElement(mr,W+'rPr'); node(rp,'rFonts',ascii='Cambria Math',hAnsi='Cambria Math',eastAsia='宋体')
            node(rp,'sz',val=self.role(name)['run']['sz']['val'])
        pr=p.find(W+'pPr'); put(pr,'pStyle',{'val':'asc_'+name})
    def setup(self):
        self.ir=parse(self.manuscript,self.pandoc)
        (self.work/'manuscript-ir.json').write_text(json.dumps(self.ir,ensure_ascii=False,indent=2),encoding='utf-8')
        base=json.loads(Path(self.c['role_bindings']).read_text(encoding='utf-8'))
        for binding in base['roles']:
            refinement=self.c.get('role_refinements',{}).get(binding['role'])
            if refinement:
                binding['rationale']+=' '+refinement['rationale']
                binding['evidence_ids']=sorted(set(binding['evidence_ids']+refinement['evidence_ids']))
                for area,tags in refinement['overrides'].items():binding.setdefault('overrides',{}).setdefault(area,{}).update(tags)
        base['roles']+=self.c['extra_roles']
        (self.work/'merged-role-bindings.json').write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding='utf-8')
        compiled=compile_bindings(self.template,Path(self.c['review']),self.work/'merged-role-bindings.json')
        self.roles={k:v['properties'] for k,v in compiled['roles'].items()}
        (self.work/'roles.json').write_text(json.dumps(compiled,ensure_ascii=False,indent=2),encoding='utf-8')
        # Recompute boundaries for actual metadata; no fixed manuscript title split.
        cover=json.loads(Path(self.c['cover_bindings']).read_text(encoding='utf-8'))
        segment=subprocess.run([str(self.node_bin),str(Path(__file__).with_name('segment_title.mjs'))],input=json.dumps({'text':self.ir['metadata_text_view']['title_zh']},ensure_ascii=False),capture_output=True,text=True,encoding='utf-8',check=True)
        boundaries=json.loads(segment.stdout)['boundaries']
        keywords=next(o['text_for_review_only'] for o in self.ir['objects'] if o.get('role')=='keywords_zh' and o['id'].startswith('block-'))
        protected=[s.strip() for s in re.split('[；，,;]',re.sub(r'^关键词[:：]','',keywords))]
        for a in cover['actions']:
            if a['kind'] in ('two_title_slots','balanced_title_paragraph'):
                a['word_boundaries']=boundaries; a['protected_terms']=protected
        (self.work/'cover-bindings.json').write_text(json.dumps(cover,ensure_ascii=False,indent=2),encoding='utf-8')
        write_cover(Path(self.c['features']),self.work/'cover-bindings.json',self.work/'manuscript-ir.json',self.work/'cover.docx')
        self.parts=readzip(self.work/'cover.docx'); self.root=E.fromstring(self.parts['word/document.xml']); self.body=self.root.find(W+'body')
        self.rels=E.fromstring(self.parts['word/_rels/document.xml.rels']); self.ct=E.fromstring(self.parts['[Content_Types].xml'])
        self.styles=E.fromstring(self.parts['word/styles.xml'])
        for name,role in self.roles.items():
            sid='asc_'+name
            if any(s.get(W+'styleId')==sid for s in self.styles): raise ValueError('Source style collision')
            s=node(self.styles,'style',type='paragraph',styleId=sid); node(s,'name',val='ASC '+name)
            s.append(materialize_props('pPr',role['paragraph'])); s.append(materialize_props('rPr',role['run']))
        # TOC styles independent of headings; needed for subsequent Word regeneration.
        for level,sampleid in enumerate(self.c['toc']['samples'],1):
            role=self.toc_role(sampleid,level-1); sid='TOC'+str(level)
            old=next((s for s in self.styles if s.get(W+'styleId')==sid),None)
            if old is not None:self.styles.remove(old)
            s=node(self.styles,'style',type='paragraph',styleId=sid); node(s,'name',val='toc '+str(level))
            s.append(materialize_props('pPr',role['paragraph'])); s.append(materialize_props('rPr',role['run']))
        self.footer_rid=self.add_footer(self.c['footer_size_pt'])
        self.blank_header=self.add_part('header','word/asc-empty-header.xml',xml(E.Element(W+'hdr',nsmap={'w':W[1:-1]})))
        self.blank_footer=self.add_part('footer','word/asc-empty-footer.xml',xml(E.Element(W+'ftr',nsmap={'w':W[1:-1]})))
        self.frontsec=self.section('frontmatter'); self.bodysec=self.section('body')
        for level in range(1,len(self.c['toc']['samples'])+1):
            style=next(s for s in self.styles if s.get(W+'styleId')=='TOC'+str(level))
            pr=style.find(W+'pPr');tabs=node(pr,'tabs')
            node(tabs,'tab',val='right',pos=self.usable_width(self.frontsec),leader='dot')
        self.coversec=self.body.find(W+'sectPr'); self.body.remove(self.coversec)
        # The cover is intentionally unnumbered unless the source contract retains its field.
        if self.c.get('cover_unumbered',True):
            self.section_refs(self.coversec,self.blank_header,self.blank_footer)
        put(self.coversec,'type',{'val':'nextPage'})
        # Avoid adding a new line after a near-full cover: attach boundary to last source paragraph.
        last=self.body[-1]
        if last.tag!=W+'p': raise ValueError('Cover boundary requires a reviewed trailing paragraph')
        pr=last.find(W+'pPr')
        if pr is None: pr=E.Element(W+'pPr'); last.insert(0,pr)
        pr.append(self.coversec)
    def add_part(self,kind,path,data):
        self.parts[path]=data
        ident=1+max([int(r.get('Id')[3:]) for r in self.rels if re.fullmatch(r'rId\d+',r.get('Id',''))]+[0])
        rid='rId'+str(ident)
        E.SubElement(self.rels,PKG+'Relationship',Id=rid,Type=R[1:-1]+'/'+kind,Target=path.removeprefix('word/'))
        content='application/vnd.openxmlformats-officedocument.wordprocessingml.'+kind+'+xml'
        if kind in ('header','footer','footnotes') and not any(n.get('PartName')=='/'+path for n in self.ct):
            E.SubElement(self.ct,CT+'Override',PartName='/'+path,ContentType=content)
        return rid
    def add_footer(self,size):
        role=copy.deepcopy(self.role('body')); role['paragraph']={'jc':{'val':'center'},'ind':{'firstLine':'0','firstLineChars':'0'},'snapToGrid':{'val':'0'}}
        role['run']['sz']={'val':str(round(size*2))}; role['run']['szCs']=dict(role['run']['sz'])
        f=E.Element(W+'ftr',nsmap={'w':W[1:-1]}); p=paragraph('',role); field(p,'PAGE','1',role); f.append(p)
        return self.add_part('footer','word/asc-footer.xml',xml(f))
    def section_refs(self,sec,header,footer):
        for tag in ('headerReference','footerReference','titlePg'):
            for n in list(sec.findall(W+tag)): sec.remove(n)
        for kind,rid in [('headerReference',header),('footerReference',footer)]:
            sec.insert(0,E.Element(W+kind,{W+'type':'default',R+'id':rid}))
            sec.insert(0,E.Element(W+kind,{W+'type':'even',R+'id':rid}))
            sec.insert(0,E.Element(W+kind,{W+'type':'first',R+'id':rid}))
    def section(self,name):
        cfg=self.c['sections'][name]; sec=copy.deepcopy(self.sample(cfg['sample_id']))
        if sec.tag!=W+'sectPr': raise ValueError('Section sample expected')
        for tag,attrs in cfg.get('overrides',{}).items(): put(sec,tag,attrs)
        header=cfg.get('header_rid') or self.blank_header
        self.section_refs(sec,header,self.footer_rid)
        put(sec,'pgNumType',{'fmt':cfg['number_format'],'start':str(cfg['start'])})
        put(sec,'type',{'val':'nextPage'})
        return sec
    def usable_width(self,sec):
        sz=sec.find(W+'pgSz'); mar=sec.find(W+'pgMar')
        return int(sz.get(W+'w'))-sum(int(mar.get(W+k,'0')) for k in ('left','right','gutter'))
    def convert(self):
        ast=copy.deepcopy(self.ir['ast']); ast['meta']={}; blocks=[]
        top=[o for o in self.ir['objects'] if o['id'].startswith('block-')]
        self.top=top
        for i,obj in enumerate(top):
            blocks.append({'t':'Para','c':[{'t':'Str','c':'ASC_BOUNDARY_'+str(i)}]}); blocks.append(obj['ast'])
        ast['blocks']=blocks
        target=self.work/'pandoc-content.docx'
        command=[str(self.pandoc),'-f','json','-t','docx','--resource-path='+str(self.manuscript.resolve().parent),'-o',str(target)]
        result=subprocess.run(command,input=json.dumps(ast,ensure_ascii=False).encode(),capture_output=True,check=True)
        (self.work/'pandoc.log').write_bytes(result.stderr)
        self.pp=readzip(target); doc=E.fromstring(self.pp['word/document.xml'])
        self.pr={r.get('Id'):r for r in E.fromstring(self.pp['word/_rels/document.xml.rels'])}
        groups={}; index=None
        for n in doc.find(W+'body'):
            if n.tag==W+'sectPr':continue
            if n.tag in (W+'bookmarkStart',W+'bookmarkEnd'):continue
            match=re.fullmatch(r'ASC_BOUNDARY_(\d+)',plain(n))
            if match: index=int(match[1]); groups[index]=[]
            elif index is None: raise ValueError('Converted content outside boundary')
            else: groups[index].append(copy.deepcopy(n))
        if len(groups)!=len(top):raise ValueError('Lost AST block boundary')
        self.groups=groups; self.drawid=max([int(n.get('id')) for n in self.root.iter() if n.tag.endswith('}docPr')]+[0])+1
        # Remove all imported locator/style IDs. Native notes/math and image bytes survive.
        for group in groups.values():
            for n in group:
                for q in list(n.iter()):
                    if q.tag in (W+'bookmarkStart',W+'bookmarkEnd',W+'pStyle',W+'rStyle'):q.getparent().remove(q)
                    for attr,val in list(q.attrib.items()):
                        if attr.startswith(R) and attr.removeprefix(R) in ('embed','link','id'):
                            relation=self.pr[val]
                            if relation.get('TargetMode')=='External':
                                ident=self.add_external(relation);q.set(attr,ident)
                            elif relation.get('Type').endswith('/image'):
                                path=posixpath.normpath('word/'+relation.get('Target'))
                                if not path.startswith('word/media/'):raise ValueError('Unsafe converted image path')
                                data=self.pp[path]; ext=Path(path).suffix; newpath='word/media/asc-'+sha_bytes(data)[:20]+ext
                                self.parts[newpath]=data; ident=self.add_image_relation(newpath,relation.get('Type'));q.set(attr,ident)
                            else:raise ValueError('Unexpected imported relationship')
                        if q.tag.endswith('}docPr'):q.set('id',str(self.drawid));self.drawid+=1
    def add_external(self,relation):
        rid='rId'+str(1+max([int(r.get('Id')[3:]) for r in self.rels if re.fullmatch(r'rId\d+',r.get('Id',''))]+[0]))
        E.SubElement(self.rels,PKG+'Relationship',Id=rid,Type=relation.get('Type'),Target=relation.get('Target'),TargetMode='External');return rid
    def add_image_relation(self,path,typ):
        existing=next((r for r in self.rels if r.get('Target')==path.removeprefix('word/')),None)
        if existing is not None:return existing.get('Id')
        rid='rId'+str(1+max([int(r.get('Id')[3:]) for r in self.rels if re.fullmatch(r'rId\d+',r.get('Id',''))]+[0]))
        E.SubElement(self.rels,PKG+'Relationship',Id=rid,Type=typ,Target=path.removeprefix('word/'))
        if not any(n.get('Extension')=='png' for n in self.ct):E.SubElement(self.ct,CT+'Default',Extension='png',ContentType='image/png')
        return rid
    def target(self,p,label,level=0,search=None):
        anchor='asc_heading_'+str(len(self.targets)+1); self.anchor(p,anchor)
        self.targets.append({'label':label,'anchor':anchor,'level':level,'search_text':search or plain(p)})
        self.tc(p,label,level)
    def tc(self,p,label,level=0):
        cfg=self.c['toc']; separator=cfg.get('number_title_separator')
        if cfg.get('number_title_separators'):separator=cfg['number_title_separators'][min(level,len(cfg['number_title_separators'])-1)]
        if separator is not None:label=re.sub(r'^(\d+(?:\.\d+)*)\s+',lambda m:m[1]+separator,label)
        # Mirror Word MarkEntry: explicitly hiding the code runs makes Word skip
        # these entries when hidden text display is disabled. TC is nonprinting.
        r=node(p,'r');node(r,'fldChar',fldCharType='begin')
        r=node(p,'r');code=node(r,'instrText');code.text=' TC "'+label+'" \\f a \\l "'+str(level+1)+'" ';code.set(SPACE,'preserve')
        r=node(p,'r');node(r,'fldChar',fldCharType='end')
    def citations(self,p):
        for r in list(p.findall(W+'r')):
            t=r.find(W+'t')
            if t is None or not re.search(r'\[\d+\]',t.text or ''):continue
            rp=r.find(W+'rPr'); at=p.index(r); p.remove(r)
            for token in re.split(r'(\[\d+\])',t.text):
                if not token:continue
                match=re.fullmatch(r'\[(\d+)\]',token)
                if match:
                    ident=match[1]
                    if ident not in self.ir['bibliography']:raise ValueError('Unknown citation')
                    q=E.Element(W+'hyperlink',{W+'anchor':'asc_bib_'+ident,W+'history':'1'}); rr=node(q,'r'); self.cite_count+=1
                else:q=E.Element(W+'r');rr=q
                if rp is not None:rr.append(copy.deepcopy(rp))
                if match and self.c['citation_superscript']:
                    pr=rr.find(W+'rPr')
                    if pr is None:pr=node(rr,'rPr')
                    put(pr,'vertAlign',{'val':'superscript'})
                tt=node(rr,'t');tt.text=token;tt.set(SPACE,'preserve');p.insert(at,q);at+=1
    def renumber_mentions(self,p):
        for t in p.iter(W+'t'):
            t.text=re.sub(r'([图表])(\d+)\.(\d+)',lambda m:m[1]+m[2]+self.c['number_separator']+m[3],t.text or '')
    def native_table(self,tbl):
        cfg=self.c['table']; pr=tbl.find(W+'tblPr')
        if pr is None:pr=E.Element(W+'tblPr');tbl.insert(0,pr)
        for tag in ('tblStyle','tblLook','tblBorders','tblCellMar','tblInd'): 
            n=pr.find(W+tag)
            if n is not None:pr.remove(n)
        width=self.usable_width(self.bodysec); rows=tbl.findall(W+'tr'); cols=max(len(r.findall(W+'tc')) for r in rows)
        if any(len(r.findall(W+'tc'))!=cols for r in rows):raise ValueError('Merged cells need explicit table adapter')
        # Text-derived proportional widths, with a minimum for numeric/short columns.
        lengths=[]
        for ci in range(cols):
            vals=[plain(r.findall(W+'tc')[ci]) for r in rows]
            lengths.append(max(5,min(24,max(sum(1 if ord(x)>255 else .52 for x in v) for v in vals))))
        widths=[round(width*x/sum(lengths)) for x in lengths];widths[-1]+=width-sum(widths)
        put(pr,'tblW',{'w':width,'type':'dxa'});put(pr,'jc',{'val':'center'});put(pr,'tblLayout',{'type':'fixed'})
        mar=node(pr,'tblCellMar')
        for side,v in [('left',90),('right',90),('top',55),('bottom',55)]:node(mar,side,w=v,type='dxa')
        borders=node(pr,'tblBorders')
        for side in ('top','bottom','left','right','insideH','insideV'):node(borders,side,val='nil')
        old=tbl.find(W+'tblGrid')
        if old is not None:tbl.remove(old)
        grid=E.Element(W+'tblGrid');tbl.insert(1,grid)
        for v in widths:node(grid,'gridCol',w=v)
        for ri,row in enumerate(rows):
            trpr=row.find(W+'trPr')
            if trpr is None:trpr=E.Element(W+'trPr');row.insert(0,trpr)
            for tag in ('trHeight','tblHeader'): 
                for q in list(trpr.findall(W+tag)):trpr.remove(q)
            put(trpr,'cantSplit',{'val':'1'})
            if ri==0:node(trpr,'tblHeader',val=1)
            for ci,cell in enumerate(row.findall(W+'tc')):
                tcpr=cell.find(W+'tcPr')
                if tcpr is None:tcpr=E.Element(W+'tcPr');cell.insert(0,tcpr)
                for tag in ('tcBorders','shd'): 
                    q=tcpr.find(W+tag)
                    if q is not None:tcpr.remove(q)
                put(tcpr,'tcW',{'w':widths[ci],'type':'dxa'});put(tcpr,'vAlign',{'val':'center'})
                cb=node(tcpr,'tcBorders')
                for side in ('top','left','bottom','right'):
                    show=(side=='top' and ri==0) or (side=='bottom' and ri==len(rows)-1)
                    if cfg['border_policy']=='three_line':show=show or (side=='bottom' and ri==0)
                    else:show=show or side in ('top','bottom') or (cfg['border_policy']=='grid') or (side=='left' and ci>0) or (side=='right' and ci<cols-1)
                    node(cb,side,val='single' if show else 'nil',sz=cfg['line_width_eighth_pt'],color='000000',space=0)
                for p in cell.findall(W+'p'):
                    self.apply(p,'table_body');pr=p.find(W+'pPr')
                    keep=len(rows)<=cfg.get('keep_together_max_rows',0) and ri<len(rows)-1
                    put(pr,'keepNext',{'val':'1' if keep else '0'});put(pr,'keepLines',{'val':'1'})
                    if ri==0 and cfg.get('unit_header_policy')=='comma':
                        for t in p.iter(W+'t'):t.text=re.sub(r'[（(]([^）)]+)[）)]',r',\1',t.text or '')
                    put(pr,'jc',{'val':'center' if ci==0 or len(plain(p))<14 else 'left'})
                    if ri==0 and cfg.get('header_bold'):
                        for r in p.findall(W+'r'):put(r.find(W+'rPr'),'b',{'val':'1'})
        self.events.append({'kind':'native_table','rows':len(rows),'columns':cols,'widths_twips':widths,'border_policy':cfg['border_policy']})
    def equation(self,p,obj):
        self.counter[('equation',self.chapter)]+=1; ordinal=self.counter[('equation',self.chapter)]
        number=str(self.chapter)+self.c['number_separator']+str(ordinal)
        self.apply(p,'equation');pr=p.find(W+'pPr');put(pr,'jc',{'val':'left'});put(pr,'ind',{'firstLine':'0','firstLineChars':'0'})
        width=self.usable_width(self.bodysec);tabs=put(pr,'tabs',{})
        node(tabs,'tab',val='center',pos=width//2);node(tabs,'tab',val='right',pos=width)
        mp=p.find(M+'oMathPara')
        if mp is None:raise ValueError('Unsupported display math nesting')
        maths=list(mp.findall(M+'oMath')); at=p.index(mp);p.remove(mp)
        tab=E.Element(W+'r');node(tab,'tab');p.insert(at,tab)
        for j,m in enumerate(maths):p.insert(at+1+j,m)
        r=node(p,'r');node(r,'tab');run(p,'(',self.role('equation'))
        ident=next((n['c'][0][0] for _,n in walk(obj['ast']) if n.get('t')=='Div' and n['c'][0][0]),'asc_equation_'+str(self.chapter)+'_'+str(ordinal))
        anchor=re.sub('[^a-zA-Z0-9_]','_',ident);self.bid+=1
        node(p,'bookmarkStart',id=self.bid,name=anchor);run(p,str(self.chapter)+self.c['number_separator'],self.role('equation'))
        field(p,'SEQ asc_equation_ch'+str(self.chapter)+' \\* ARABIC',str(ordinal),self.role('equation'));node(p,'bookmarkEnd',id=self.bid)
        run(p,')',self.role('equation'));self.equations[ident]={'anchor':anchor,'number':number}
        self.events.append({'kind':'display_equation','anchor':anchor,'number':number})
    def toc_role(self,sampleid,level):
        sample=copy.deepcopy(self.f[sampleid]['effective_sample_format'])
        for tag in ('tabs','numPr','sectPr','outlineLvl'):sample['paragraph'].pop(tag,None)
        fonts=self.c['toc']['fonts']
        indent=toc_left_indent(sample['paragraph'],level,self.c['toc'].get('level_indents_twips'))
        role=compile_role(sample,{'run':{'rFonts':fonts,'b':{'val':'0'},'color':{'val':'000000'}},
             'paragraph':{'ind':{'left':indent,'firstLine':'0','firstLineChars':'0'},'jc':{'val':'left'},'keepNext':{'val':'0'}}})
        role=compile_role(role,self.c['toc'].get('overrides',{}))
        return role
    def blanks(self,container,cue_ids,anchor):
        for ident in cue_ids:
            if ident not in self.blank_cues:raise ValueError('Unrecognized blank cue: '+ident)
            cue=self.blank_cues[ident]
            for _ in range(cue['count']):container.append(paragraph('',cue['properties']))
            self.events.append({'kind':'blank_flow','anchor':anchor,**cue})
    def toc(self):
        cfg=self.c['toc'];self.toc_nodes=[]
        self.blanks(self.toc_nodes,cfg.get('before_heading',[]),'toc.before_heading')
        p=paragraph(cfg['heading_text'],self.role('toc_heading'));self.anchor(p,'asc_toc');self.toc_nodes.append(p)
        put(p.find(W+'pPr'),'pStyle',{'val':'asc_toc_heading'})
        if cfg['include_self']:put(p.find(W+'pPr'),'outlineLvl',{'val':'0'})
        if self.toc_nodes[0] is not p:
            put(self.toc_nodes[0].find(W+'pPr'),'pageBreakBefore',{'val':'1'})
            put(p.find(W+'pPr'),'pageBreakBefore',{'val':'0'})
        self.blanks(self.toc_nodes,cfg.get('after_heading',[]),'toc.after_heading')
        if cfg['include_self']:
            self.targets.insert(2,{'label':cfg['heading_text'],'anchor':'asc_toc','level':0,'search_text':cfg['heading_text']});self.tc(p,cfg['heading_text'])
        # Field begin/separate lives in first cached entry; no artificial blank lines.
        entries=[]
        for i,target in enumerate(self.targets):
            role=self.toc_role(cfg['samples'][min(target['level'],2)],target['level']);q=paragraph('',role)
            pr=q.find(W+'pPr');tabs=node(pr,'tabs');node(tabs,'tab',val='right',pos=self.usable_width(self.frontsec),leader='dot')
            put(pr,'pStyle',{'val':'TOC'+str(target['level']+1)})
            if i==0:
                instruction=' TOC \\h \\z \\f a '
                r=node(q,'r');node(r,'fldChar',fldCharType='begin');r=node(q,'r');node(r,'instrText').text=instruction
                r=node(q,'r');node(r,'fldChar',fldCharType='separate')
            label=target['label']
            separator=cfg.get('number_title_separator')
            if cfg.get('number_title_separators'):
                separator=cfg['number_title_separators'][min(target['level'],len(cfg['number_title_separators'])-1)]
            if separator is not None:
                label=re.sub(r'^(\d+(?:\.\d+)*)\s+',lambda m:m[1]+separator,label)
            h=node(q,'hyperlink',anchor=target['anchor'],history=1);run(h,label,role)
            leader_role=compile_role(role,{'run':cfg.get('leader_run',{})})
            r=node(q,'r');r.append(materialize_props('rPr',leader_role['run']));node(r,'tab')
            page_role=compile_role(role,{'run':cfg.get('page_run',{})})
            field(q,'PAGEREF '+target['anchor']+' \\h','?',page_role)
            entries.append(q)
        r=node(entries[-1],'r');node(r,'fldChar',fldCharType='end');self.toc_nodes+=entries
        # The section break ends the complete frontmatter without adding a blank page.
        entries[-1].find(W+'pPr').append(self.frontsec)
        return self.toc_nodes
    def abstracts(self,obj,group,role):
        cfg=self.c['abstracts'][role]
        if obj['kind']=='Header':
            self.blanks(self.abstract_nodes[role],cfg.get('before_heading',[]),role+'.before_heading')
            if cfg['standalone_heading']:
                label=cfg['heading'];p=paragraph(label,self.role(role+'_title'))
                self.target(p,label);self.abstract_nodes[role].append(p)
            elif cfg.get('paper_title'):
                self.abstract_nodes[role].append(paragraph(self.ir['metadata_text_view']['title_'+('zh' if role.endswith('zh') else 'en')],self.role(cfg.get('paper_title_role','abstract_title'))))
            self.blanks(self.abstract_nodes[role],cfg.get('after_heading',[]),role+'.after_heading')
            return
        keyword=obj['role'].startswith('keywords')
        name=obj['role'] if keyword else role
        if len(group)!=1 or group[0].tag!=W+'p':raise ValueError('Abstract paragraphs required')
        p=group[0];self.apply(p,name+'_body')
        labelrole=name+'_label'
        if keyword:
            # Preserve keyword facts while normalizing separators and initial case per template.
            value=re.sub(r'^(关键词|key\s*words)\s*[:：]\s*','',text(obj['ast']),flags=re.I)
            terms=[s.strip() for s in re.split('[；，,;]',value) if s.strip()]
            if cfg.get('keyword_initial_uppercase'):terms=[s[0].upper()+s[1:] for s in terms]
            value=cfg['keyword_separator'].join(terms)
            p=paragraph(value,self.role(name+'_body'))
            self.blanks(self.abstract_nodes[role],cfg.get('before_keywords',[]),role+'.before_keywords')
            for _ in range(cfg.get('keyword_gap_blank_lines',0)):
                self.abstract_nodes[role].append(paragraph('',self.role(name+'_body')))
            label=cfg['keyword_label']
        else:label=cfg['inline_label']
        if label:
            r=E.Element(W+'r');r.append(materialize_props('rPr',self.role(labelrole)['run']));t=node(r,'t');t.text=label;t.set(SPACE,'preserve');p.insert(1,r)
        if not keyword and not cfg['standalone_heading']:
            self.target(p,cfg['toc_label'],search=plain(p)[:40])
        self.abstract_nodes[role].append(p)
    def bibliography(self,p,obj):
        raw=text(obj['ast']);match=re.match(r'^\[(\d+)\]\s*(.+?et al\.)\s+(.+)\. ([^,]+), (\d{4}), (.+)\. DOI: (.+)\.$',raw)
        if not match:raise ValueError('This bibliography adapter requires reviewed journal fields')
        ident,authors,title,journal,year,volume,doi=match.groups()
        if self.c['references']['uppercase_authors']:authors=authors.removesuffix('et al.').upper().rstrip(', ') + ', et al'
        display='['+ident+'] '+authors+'. '+title+'[J]. '+journal+', '+year+', '+volume+'. DOI: '+doi+'.'
        display=display.replace('al..','al.')
        p=paragraph(display,self.role('bibliography_entry'));self.anchor(p,'asc_bib_'+ident)
        self.events.append({'kind':'bibliography','id':ident,'original':raw,'display':display})
        return p
    def notes(self):
        fn=E.fromstring(self.pp['word/footnotes.xml']);refs=list(self.root.iter(W+'footnoteReference'))
        mapping={};normal=[n for n in fn if n.get(W+'type') not in ('separator','continuationSeparator')]
        for i,r in enumerate(refs,1):mapping[r.get(W+'id')]=str(i);r.set(W+'id',str(i))
        for n in fn:
            typ=n.get(W+'type')
            if typ=='separator':n.set(W+'id','-1')
            elif typ=='continuationSeparator':n.set(W+'id','0')
            else:
                old=n.get(W+'id')
                if old not in mapping:raise ValueError('Unreferenced manuscript footnote')
                n.set(W+'id',mapping[old])
                for p in n.findall(W+'p'):self.apply(p,'footnote')
        self.parts['word/asc-footnotes.xml']=xml(fn)
        for r in list(self.rels):
            if r.get('Type').endswith('/footnotes'):self.rels.remove(r)
        self.add_part('footnotes','word/asc-footnotes.xml',xml(fn))
        return len(normal)
    def build(self):
        self.setup();self.convert();self.abstract_nodes={'abstract_zh':[],'abstract_en':[]};body_nodes=[]
        for i,obj in enumerate(self.top):
            group=self.groups[i];role=obj['role']
            if role=='title':continue
            if role.startswith(('abstract','keywords')):
                self.abstracts(obj,group,role.replace('keywords','abstract'));continue
            if obj['kind']=='Header':
                if role=='chapter':self.chapter=obj['chapter']
                if role in ('chapter','section','subsection','references'):
                    p=group[0];rname='reference_heading' if role=='references' else role;self.apply(p,rname)
                    if role=='chapter' and self.c.get('chapter_number_style')=='arabic':
                        value=re.sub(r'^第.+?章\s*',str(self.chapter)+' ',plain(p));p=paragraph(value,self.role(rname))
                    self.target(p,plain(p),{'chapter':0,'section':1,'subsection':2,'references':0}[role]);body_nodes.append(p)
                    self.blanks(body_nodes,self.c.get('heading_after',{}).get(role,[]),'heading.'+role)
                    continue
            if role=='bibliography_entry':body_nodes.append(self.bibliography(group[0],obj));continue
            for n in group:
                if n.tag==W+'tbl':self.native_table(n)
                elif n.tag==W+'p':
                    if n.find('.//'+W+'drawing') is not None:
                        self.apply(n,'figure');width=self.usable_width(self.bodysec)*635
                        # An inline image determines its own line box. Text-derived
                        # multiple spacing can paint its top into the page header.
                        pr=n.find(W+'pPr')
                        put(pr,'spacing',{'line':'240','lineRule':'auto'})
                        # Adjacent inline images must not paint over a data-table
                        # bottom border in grid-aware renderers. Reserve one table
                        # text line; do not change cover/floating source artwork.
                        if body_nodes and body_nodes[-1].tag==W+'tbl':
                            pr=n.find(W+'pPr');spacing=pr.find(W+'spacing')
                            clearance=int(self.role('table_body')['run']['sz']['val'])*10
                            spacing.set(W+'before',str(max(clearance,int(spacing.get(W+'before','0')))))
                        extent=next(q for q in n.iter() if q.tag.endswith('}extent'));scale=min(1,width/int(extent.get('cx')))
                        for q in n.iter():
                            if q.tag.endswith(('}extent','}ext')) and q.get('cx') and q.get('cy'):
                                q.set('cx',str(round(int(q.get('cx'))*scale)));q.set('cy',str(round(int(q.get('cy'))*scale)))
                    elif n.find(M+'oMathPara') is not None:self.equation(n,obj)
                    else:
                        self.apply(n,'table_caption' if role=='table_caption' else 'figure_caption' if role=='figure' else 'body')
                        if role not in ('table_caption','figure'):self.citations(n)
                    self.renumber_mentions(n)
                else:raise ValueError('Unsupported native block '+n.tag)
                body_nodes.append(n)
            if role=='table' and self.c['table'].get('after_blank_lines'):
                for _ in range(self.c['table']['after_blank_lines']):body_nodes.append(paragraph('',self.role('body')))
        for p in body_nodes:
            replace_equation_links(p,self.equations,self.role('body'))
        # Semantic flow: cover, Chinese abstract, English abstract, TOC, complete body.
        zh=self.abstract_nodes['abstract_zh'];en=self.abstract_nodes['abstract_en']
        if self.c['abstracts']['abstract_en'].get('page_break_before'):put(en[0].find(W+'pPr'),'pageBreakBefore',{'val':'1'})
        for p in zh+en:self.body.append(p)
        for p in self.toc():self.body.append(p)
        # First body starts via section boundary, not an extra manual/chapter break.
        if body_nodes:put(body_nodes[0].find(W+'pPr'),'pageBreakBefore',{'val':'0'})
        for p in body_nodes:self.body.append(p)
        self.body.append(self.bodysec);note_count=self.notes()
        # Retain audited caches on open; manual Word refresh remains unverified.
        settings=E.fromstring(self.parts['word/settings.xml']);put(settings,'updateFields',{'val':'false'})
        # Source special footnote settings must not point at incompatible WPS IDs.
        fp=settings.find(W+'footnotePr')
        if fp is not None:settings.remove(fp)
        fp=node(settings,'footnotePr')
        for key,value in self.c['footnote_numbering'].items():node(fp,key,val=value)
        node(fp,'footnote',id=-1);node(fp,'footnote',id=0)
        for sec in self.root.iter(W+'sectPr'):
            old=sec.find(W+'footnotePr')
            if old is not None:sec.remove(old)
            sf=E.Element(W+'footnotePr')
            for key,value in self.c['footnote_numbering'].items():node(sf,key,val=value)
            pos=0
            while pos<len(sec) and sec[pos].tag in (W+'headerReference',W+'footerReference'):pos+=1
            sec.insert(pos,sf)
        self.parts.update({'word/document.xml':xml(self.root),'word/styles.xml':xml(self.styles),'word/settings.xml':xml(settings),
                           'word/_rels/document.xml.rels':xml(self.rels),'[Content_Types].xml':xml(self.ct)})
        names=[n.get(W+'name') for n in self.root.iter(W+'bookmarkStart')]
        if len(names)!=len(set(names)):raise ValueError('Duplicate bookmark')
        for h in self.root.iter(W+'hyperlink'):
            if h.get(W+'anchor') and h.get(W+'anchor') not in names:raise ValueError('Dangling anchor')
        if self.cite_count!=len(self.ir['citation_mentions']):raise ValueError('Citation count mismatch')
        if len([e for e in self.events if e['kind']=='display_equation'])!=sum(1 for _,n in walk(self.ir['ast']) if n.get('t')=='Math' and n['c'][0]['t']=='DisplayMath'):raise ValueError('Lost display math')
        if note_count!=self.ir['counts']['Note']:raise ValueError('Lost footnote')
        writezip(self.output,self.parts)
        modified=[k for k in self.original if self.parts.get(k)!=self.original[k]]
        if set(modified)-{'word/document.xml','word/styles.xml','word/settings.xml','word/_rels/document.xml.rels','[Content_Types].xml'}:raise ValueError('Unexpected source package edit')
        report={'source_sha256':sha(self.template),'manuscript_sha256':sha(self.manuscript),'output_sha256':sha(self.output),
                'implementation_sha256':sha(Path(__file__)),'contract_sha256':sha(self.work/'contract.json'),
                'native_footnotes':note_count,'citation_count':self.cite_count,'toc_targets':self.targets,'events':self.events,
                'modified_source_parts':modified,'source_parts_preserved':len(self.original)-len(modified),
                'source_unchanged':sha(self.template)==self.c['source_sha256'],'word_refresh_verified':False,'stage':'before_render_and_toc_cache'}
        (self.work/'write-receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report

def sha_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('manuscript','template','output','run-dir','pandoc','node'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=Writer(a.manuscript,a.template,a.output,a.run_dir,a.pandoc,a.node).build()
    print(json.dumps({k:result[k] for k in ('output_sha256','native_footnotes','citation_count','source_unchanged')}))

"""Cache real rendered footer labels, never guess section page numbers."""
import argparse, json, re
from pathlib import Path
import pdfplumber
from lxml import etree as E
from full_writer import W, readzip, writezip, xml, sha

def compact(value):
    return re.sub(r'\s+', '', value)

def locate(pdf, targets):
    with pdfplumber.open(pdf) as doc:
        pages=[{'text':p.extract_text() or '', 'footer':p.crop((0,p.height*.90,p.width,p.height)).extract_text() or ''} for p in doc.pages]
    # Initial caches have ?, finalized caches have leaders followed by a number.
    toc_pages={i for i,p in enumerate(pages,1) if len(re.findall(r'\.{3,}',p['text']))>=3}
    if not toc_pages: raise ValueError('No unambiguous rendered TOC pages')
    result={}
    for target in targets:
        search=compact(target['search_text']); hits=[]
        for i,p in enumerate(pages,1):
            is_self=target['anchor']=='asc_toc'
            if (i in toc_pages)!=is_self: continue
            lines=p['text'].splitlines()
            match=search in [compact(s) for s in lines]
            # Inline abstract labels use a source-content prefix spanning lines.
            if not match and target['label']!=target['search_text']:
                match=search in compact(p['text'])
            if not match: continue
            footers=[s.strip() for s in p['footer'].splitlines() if re.fullmatch(r'[0-9]+|[IVXLCDM]+',s.strip())]
            if len(footers)!=1: raise ValueError('Ambiguous footer: '+target['label'])
            hits.append({'physical_page':i,'page_label':footers[0]})
        if len(hits)!=1: raise ValueError('Ambiguous/missing target: '+target['label']+' '+str(hits))
        result[target['anchor']]={'label':target['label'],**hits[0]}
    return {'page_count':len(pages),'toc_physical_pages':sorted(toc_pages),'targets':result}

def finalize(source,pdf,receipt,output):
    report=json.loads(receipt.read_text(encoding='utf-8'))
    if sha(source)!=report['output_sha256']: raise ValueError('Draft receipt mismatch')
    mapping=locate(pdf,report['toc_targets']);parts=readzip(source);root=E.fromstring(parts['word/document.xml'])
    changed=[]
    for f in root.iter(W+'fldSimple'):
        m=re.fullmatch(r'\s*PAGEREF\s+(\S+)\s+\\h\s*',f.get(W+'instr',''))
        if not m:continue
        anchor=m[1]
        if anchor not in mapping['targets']:raise ValueError('Unknown PAGEREF')
        texts=list(f.iter(W+'t'))
        if len(texts)!=1:raise ValueError('Ambiguous field cache')
        texts[0].text=mapping['targets'][anchor]['page_label'];changed.append(anchor)
    if len(changed)!=len(mapping['targets']) or len(set(changed))!=len(changed):raise ValueError('Incomplete TOC cache')
    parts['word/document.xml']=xml(root);writezip(output,parts)
    return {'source_sha256':sha(source),'pdf_sha256':sha(pdf),'output_sha256':sha(output),'mapping':mapping,'word_refresh_verified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source','pdf','receipt','output','report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=finalize(a.source,a.pdf,a.receipt,a.output)
    a.report.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pages':r['mapping']['page_count'],'targets':len(r['mapping']['targets']),'output_sha256':r['output_sha256']}))

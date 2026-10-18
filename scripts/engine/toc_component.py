"""Clone source TOC typography independently of body headings; author PAGEREF caches."""
import copy,re
from lxml import etree as E
from paragraph_roles import W
def toc_left_indent(sample_paragraph, level, reviewed_indents=None):
    """Left indentation is not first-line indentation; never conflate the two.

    Reviewed levels cover templates whose examples omit a required deeper level.
    Physical units are materialized without competing character-unit overrides.
    """
    if reviewed_indents is not None:
        if level >= len(reviewed_indents):
            raise ValueError('Missing reviewed TOC level indent')
        return str(int(reviewed_indents[level]))
    return str(int(sample_paragraph.get('ind', {}).get('left', '0')))

def toc_entry(sample,label,anchor,page_label):
    p=E.Element(W+'p'); pr=sample.find(W+'pPr')
    if pr is None: raise ValueError('TOC sample missing paragraph properties')
    p.append(copy.deepcopy(pr))
    source=next((r for r in sample.iter(W+'r') if any(t.text for t in r.iter(W+'t'))),None)
    if source is None: raise ValueError('TOC sample missing label run')
    h=E.SubElement(p,W+'hyperlink',{W+'anchor':anchor,W+'history':'1'})
    r=E.SubElement(h,W+'r'); rp=source.find(W+'rPr')
    if rp is not None:r.append(copy.deepcopy(rp))
    E.SubElement(r,W+'t').text=label
    E.SubElement(E.SubElement(p,W+'r'),W+'tab')
    E.SubElement(p,W+'fldSimple',{W+'instr':' PAGEREF '+anchor+' \\h '})
    f=p[-1]; r=E.SubElement(f,W+'r'); E.SubElement(r,W+'t').text=page_label
    return p
def rendered_page_labels(pdf,labels,toc_physical_pages,heading_physical_pages=None):
    """Exact normalized heading matches outside TOC; page label from rendered footer.

    This validates a renderer's cache only, not Word pagination or field updates.
    Ambiguity/missing footer fails instead of substituting physical page numbers.
    """
    import pdfplumber
    compact=lambda s:re.sub(r'\s+','',s)
    result={}
    with pdfplumber.open(pdf) as doc:
        for label in labels:
            hits=[]
            for i,page in enumerate(doc.pages,1):
                approved=(heading_physical_pages or {}).get(label)
                if approved is not None and i!=approved:continue
                if i in toc_physical_pages and approved is None:continue
                lines=(page.extract_text() or '').splitlines()
                if compact(label) not in [compact(s) for s in lines]:continue
                footer=page.crop((0,page.height*.90,page.width,page.height)).extract_text() or ''
                candidates=[s.strip() for s in footer.splitlines() if re.fullmatch(r'[0-9]+|[IVXLCDM]+',s.strip())]
                if len(candidates)!=1:raise ValueError('Missing/ambiguous rendered footer for '+label)
                hits.append({'physical_page':i,'page_label':candidates[0]})
            if len(hits)!=1:raise ValueError('Missing/ambiguous heading location '+label)
            result[label]=hits[0]
    return result

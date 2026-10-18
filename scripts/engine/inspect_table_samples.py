"""Read table examples with border provenance; never modify the source DOCX."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from feature_extraction import Q, read_json, write_json, digest, new_dir
from inspect_docx import paths

def xml(node): return ET.tostring(node,encoding='unicode') if node is not None else None
def text(node): return ''.join(t.text or '' for t in node.iter(Q+'t'))
def borders(node):
    if node is None: return None
    result={}
    for line in node:
        a={k.removeprefix(Q):v for k,v in line.attrib.items()}
        if 'sz' in a: a['width_pt']=float(a['sz'])/8
        a['visibility']='explicit_hidden' if a.get('val') in ('nil','none') else 'explicit_visible' if a.get('val') else 'unspecified'
        result[line.tag.removeprefix(Q)]=a
    return result

def inspect(features_path,out_dir):
    f=read_json(features_path); source=Path(f['source'])
    if digest(source.read_bytes())!=f['source_sha256']: raise ValueError('Source hash mismatch')
    records=[]
    with zipfile.ZipFile(source) as z:
        root=ET.fromstring(z.read('word/document.xml'))
        pathmap={id(n):p for n,p in paths(root)}
        stylesroot=ET.fromstring(z.read('word/styles.xml'))
        styles={s.get(Q+'styleId'):s for s in stylesroot.findall(Q+'style')}
        for i,t in enumerate(root.iter(Q+'tbl'),1):
            p=t.find(Q+'tblPr'); style=p.find(Q+'tblStyle') if p is not None else None
            ident=style.get(Q+'val') if style is not None else None
            chain=[]; seen=set(); current=ident
            while current in styles and current not in seen:
                seen.add(current); s=styles[current]; chain.append({'style_id':current,'xml':xml(s)})
                base=s.find(Q+'basedOn'); current=base.get(Q+'val') if base is not None else None
            rows=[]
            for ri,row in enumerate(t.findall(Q+'tr'),1):
                cells=[]
                for ci,cell in enumerate(row.findall(Q+'tc'),1):
                    cp=cell.find(Q+'tcPr')
                    cells.append({'cell':ci,'path':pathmap[id(cell)],'text':text(cell),
                        'properties_xml':xml(cp),'borders':borders(cp.find(Q+'tcBorders') if cp is not None else None),
                        'paragraphs':[{'path':pathmap[id(p)],'text':text(p),'pPr':xml(p.find(Q+'pPr')),
                            'runs':[{'text':text(r),'rPr':xml(r.find(Q+'rPr'))} for r in p.findall(Q+'r')]} for p in cell.findall(Q+'p')]})
                rows.append({'row':ri,'properties_xml':xml(row.find(Q+'trPr')),'cells':cells})
            records.append({'table':i,'path':pathmap[id(t)],'guard_sha256':digest(xml(t).encode()),
                'properties_xml':xml(p),'direct_borders':borders(p.find(Q+'tblBorders') if p is not None else None),
                'style_chain':chain,'rows':rows})
    new_dir(out_dir)
    report={'source':str(source),'source_sha256':f['source_sha256'],'features_sha256':digest(features_path.read_bytes()),
        'tables':records,'limitations':['Absent borders are unspecified, not hidden','Style chain is evidence, not full conditional-style or shared-border resolution',
        'Merged cells and theme/font inheritance require separate interpretation','Header role is semantic; first row is not automatically header']}
    write_json(out_dir/'table-samples.json',report)
    lines=['# 表格示例原始证据','',*report['limitations']]
    for t in records:
        lines.extend(['',f"## 表对象 {t['table']}",f"直接表边框：{json.dumps(t['direct_borders'],ensure_ascii=False)}",
            f"样式链：{[s['style_id'] for s in t['style_chain']]}"])
        for r in t['rows']:
            for c in r['cells']:
                lines.append(f"行{r['row']}格{c['cell']} {c['text']!r}；格边框 {json.dumps(c['borders'],ensure_ascii=False)}")
    (out_dir/'table-samples.md').write_text('\n'.join(lines),encoding='utf-8')
    return {'table_count':len(records),'source_unchanged':digest(source.read_bytes())==f['source_sha256']}

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--features',type=Path,required=True); p.add_argument('--out-dir',type=Path,required=True); a=p.parse_args()
    print(json.dumps(inspect(a.features,a.out_dir)))

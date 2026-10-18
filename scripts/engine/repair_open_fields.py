"""Narrow package patch: disable update-on-open and explicitly hide native TC fields."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from lxml import etree as E

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def repair(source, output, report):
    if output.exists() or report.exists():
        raise FileExistsError('Use fresh revision paths')
    source_bytes = source.read_bytes()
    with zipfile.ZipFile(source) as z:
        parts = {n: z.read(n) for n in z.namelist()}
        infos = z.infolist()
    old = dict(parts)
    root = E.fromstring(parts['word/document.xml'])
    settings = E.fromstring(parts['word/settings.xml'])
    tc_count = 0
    for instr in root.iter(W + 'instrText'):
        if not (instr.text or '').lstrip().startswith('TC '):
            continue
        current = instr.getparent()
        paragraph = current.getparent()
        index = paragraph.index(current)
        siblings = list(paragraph)
        # This writer's zero-result TC field consists of paired begin/instruction/end runs.
        if index == 0 or index + 1 >= len(siblings):
            raise ValueError('Unsupported TC field layout')
        runs = siblings[index-1:index+2]
        if any(r.tag != W + 'r' for r in runs):
            raise ValueError('Unsupported TC field run structure')
        begin = runs[0].find(W + 'fldChar')
        end = runs[2].find(W + 'fldChar')
        if begin is None or end is None or begin.get(W+'fldCharType') != 'begin' or end.get(W+'fldCharType') != 'end':
            raise ValueError('TC field delimiters not paired')
        for r in runs:
            pr = r.find(W + 'rPr')
            if pr is None:
                pr = E.Element(W + 'rPr'); r.insert(0, pr)
            hide = pr.find(W + 'vanish')
            if hide is None:
                hide = E.SubElement(pr, W + 'vanish')
            hide.set(W + 'val', 'true')
        tc_count += 1
    update = settings.find(W + 'updateFields')
    if update is None:
        update = E.SubElement(settings, W + 'updateFields')
    update.set(W + 'val', 'false')
    parts['word/document.xml'] = E.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
    parts['word/settings.xml'] = E.tostring(settings, encoding='UTF-8', xml_declaration=True, standalone=True)
    # Text, caches, fields, bookmarks and links are not changed by this patch.
    before = E.fromstring(old['word/document.xml'])
    for tag, attribute in [('t',None), ('instrText',None), ('bookmarkStart','name'), ('hyperlink','anchor'), ('fldSimple','instr')]:
        def values(tree):
            return [n.text if attribute is None else n.get(W+attribute) for n in tree.iter(W+tag)]
        assert values(before) == values(root), tag
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x') as z:
        for info in infos:
            z.writestr(info, parts[info.filename])
    assert source.read_bytes() == source_bytes
    changed = [n for n in parts if old[n] != parts[n]]
    assert set(changed) <= {'word/document.xml', 'word/settings.xml'}
    result = {'source':str(source.resolve()), 'source_sha256':sha(source_bytes), 'output':str(output.resolve()), 'output_sha256':sha(output.read_bytes()), 'changed_parts':changed, 'hidden_tc_fields':tc_count, 'update_fields_on_open':False, 'text_fields_bookmarks_and_cached_pages_unchanged':True, 'source_unchanged':True, 'word_open_tested':False, 'word_manual_toc_refresh_tested':False}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(repair(args.source,args.output,args.report), ensure_ascii=False))

if __name__ == '__main__':
    main()

"""Mechanical tests on synthetic XML parts; creates no Word document."""
import argparse
import copy
import io
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from lxml import etree
from inspect_docx import paths
from text_slot_writer import stage_text_updates, sha, W, XML_SPACE

def fixture():
    raw=(f'<w:document xmlns:w="{W[1:-1]}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<w:body><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/></w:rPr>'
        '<w:t>Title</w:t></w:r><w:r><w:t>Author</w:t></w:r></w:p>'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:left="1134"/></w:sectPr></w:body></w:document>').encode()
    parts={'word/document.xml':raw,'word/styles.xml':b'<styles/>','word/media/logo.png':b'synthetic-image-bytes'}
    ops=[]
    for n,p in paths(ET.fromstring(raw)):
        if n.tag==W+'t':
            ops.append({'id':str(len(ops)),'part':'word/document.xml','part_sha256':sha(raw),
                'xml_path':p,'node_sha256':sha(ET.tostring(n,encoding='utf-8')),'expected_text':n.text,'replacement':'New '+n.text})
    return parts,ops

class TextWriter(unittest.TestCase):
    def reject(self,parts,ops,reason):
        original=copy.deepcopy(parts); old_ops=copy.deepcopy(ops)
        with self.assertRaisesRegex(ValueError,'^'+reason+'$'): stage_text_updates(parts,ops)
        self.assertEqual(parts,original); self.assertEqual(ops,old_ops)
    def test_valid_preserves_source_styles_media_section(self):
        parts,ops=fixture(); original=copy.deepcopy(parts)
        output,receipt=stage_text_updates(parts,ops)
        self.assertEqual(parts,original)
        self.assertEqual(output['word/styles.xml'],parts['word/styles.xml'])
        self.assertEqual(output['word/media/logo.png'],parts['word/media/logo.png'])
        root=etree.fromstring(output['word/document.xml'])
        self.assertEqual([n.text for n in root.iter(W+'t')],['New Title','New Author'])
        self.assertEqual(next(root.iter(W+'pgSz')).get(W+'w'),'11906')
        self.assertIsNotNone(next(root.iter(W+'rPr')).find(W+'b'))
        self.assertTrue(receipt['nontext_xml_unchanged']); self.assertTrue(receipt['untouched_parts_byte_identical'])
    def test_xml_escape_and_spaces(self):
        p,o=fixture(); o[0]['replacement']=' A & B < C '
        result,_=stage_text_updates(p,o[:1]); t=next(etree.fromstring(result['word/document.xml']).iter(W+'t'))
        self.assertEqual(t.text,' A & B < C '); self.assertEqual(t.get(XML_SPACE),'preserve')
    def test_part_hash(self):
        p,o=fixture(); o[0]['part_sha256']='0'*64; self.reject(p,o,'part_hash_mismatch')
    def test_node_hash(self):
        p,o=fixture(); o[0]['node_sha256']='0'*64; self.reject(p,o,'node_hash_mismatch')
    def test_expected_text(self):
        p,o=fixture(); o[0]['expected_text']='Wrong'; self.reject(p,o,'text_mismatch')
    def test_duplicate_target(self):
        p,o=fixture(); second=copy.deepcopy(o[0]); second['id']='other'; self.reject(p,[o[0],second],'duplicate_target')
    def test_missing_locator(self):
        p,o=fixture(); o[0]['xml_path']='missing'; self.reject(p,o,'locator_missing')
    def test_all_checked_before_any_change(self):
        p,o=fixture(); o[1]['expected_text']='Wrong'; self.reject(p,o,'text_mismatch')
    def test_reject_tab_and_linebreak(self):
        for value in ['a\tb','a\nb','\x00','\ud800']:
            with self.subTest(value=repr(value)):
                p,o=fixture(); o[0]['replacement']=value; self.reject(p,o,'replacement_not_single_text')
    def test_unsafe_part(self):
        p,o=fixture(); p['../outside']=b'x'; self.reject(p,o,'unsafe_part')
    def test_unknown_operation(self):
        p,o=fixture(); o[0]['font_size']=10; self.reject(p,o,'operation_shape')
    def test_field_text_not_plain_slot(self):
        p,o=fixture(); raw=p['word/document.xml'].replace(b'<w:r><w:t>Author',b'<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:t>Author')
        p['word/document.xml']=raw
        for op in o: op['part_sha256']=sha(raw)
        self.reject(p,o,'specialized_content')
    def test_dtd_rejected(self):
        p,o=fixture(); p['word/document.xml']=b'<!DOCTYPE x>'+p['word/document.xml']
        for op in o: op['part_sha256']=sha(p['word/document.xml'])
        self.reject(p,o,'xml_dtd_forbidden')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--report',type=Path,required=True); a=parser.parse_args()
    if a.report.exists(): raise ValueError('Preserve previous evidence')
    stream=io.StringIO(); r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TextWriter))
    report={'passed':r.wasSuccessful(),'count':r.testsRun,'details':stream.getvalue(),
        'scope':'In-memory synthetic XML tests only; no DOCX generation, full contract compiler or visual validation',
        'dependency':'lxml '+etree.LXML_VERSION.__str__()}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':r.wasSuccessful(),'count':r.testsRun}))
    if not r.wasSuccessful(): raise SystemExit(1)
if __name__=='__main__': main()

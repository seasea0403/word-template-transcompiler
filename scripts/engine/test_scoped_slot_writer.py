import copy
import io
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
from inspect_docx import paths
from scoped_slot_writer import stage_slots
from text_slot_writer import W,sha

class ScopedSlots(unittest.TestCase):
    def fixture(self):
        raw=(f'<w:document xmlns:w="{W[1:-1]}"><w:body><w:p><w:r><w:t>Title</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:jc w:val="center"/><w:rPr><w:sz w:val="36"/></w:rPr></w:pPr></w:p>'
            '<w:sectPr><w:pgSz w:w="12345"/></w:sectPr></w:body></w:document>').encode()
        slots=[]
        for n,p in paths(ET.fromstring(raw)):
            if n.tag==W+'p':
                empty=not list(n.iter(W+'t'))
                slots.append(dict(id=str(len(slots)),part='word/document.xml',part_sha256=sha(raw),xml_path=p,
                    guard_sha256=sha(ET.tostring(n,encoding='utf-8')),action='insert_into_empty_paragraph' if empty else 'replace_single_run',
                    expected_text='' if empty else 'Title',replacement='Author' if empty else 'New title'))
        return {'word/document.xml':raw,'word/styles.xml':b'unchanged'},slots
    def test_two_operations_preserved(self):
        p,s=self.fixture(); old=copy.deepcopy(p); result,r=stage_slots(p,s)
        self.assertEqual(p,old); self.assertTrue(r['outside_slot_xml_unchanged'])
        root=ET.fromstring(result['word/document.xml'])
        self.assertEqual([n.text for n in root.iter(W+'t')],['New title','Author'])
        self.assertEqual(list(root.iter(W+'sz'))[0].get(W+'val'),'36')
        self.assertEqual(result['word/styles.xml'],p['word/styles.xml'])
    def test_empty_slot_must_be_empty(self):
        p,s=self.fixture(); s[0]['action']='insert_into_empty_paragraph'
        with self.assertRaisesRegex(ValueError,'not_empty_formatted_paragraph'): stage_slots(p,s)
    def test_guard_rejected(self):
        p,s=self.fixture(); s[1]['guard_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'node_hash_mismatch'): stage_slots(p,s)
    def test_duplicate_rejected(self):
        p,s=self.fixture()
        with self.assertRaisesRegex(ValueError,'duplicate_slot'): stage_slots(p,[s[0],s[0]])

if __name__=='__main__':
    report=Path(sys.argv[1]); stream=io.StringIO()
    if report.exists(): raise ValueError('Preserve reports')
    r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ScopedSlots))
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps({'passed':r.wasSuccessful(),'count':r.testsRun,'details':stream.getvalue(),'scope':'Synthetic XML only'},indent=2),encoding='utf-8')
    print(json.dumps({'passed':r.wasSuccessful(),'count':r.testsRun}))
    if not r.wasSuccessful(): raise SystemExit(1)

import hashlib
import json
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from compile_role_bindings import compile_bindings
from manuscript_ir import sha
from inspect_docx import paths

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.source=self.root/'source.docx'
        w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        xml=f'<w:document xmlns:w="{w}"><w:body><w:p><w:r><w:t>sample</w:t></w:r></w:p></w:body></w:document>'.encode()
        with zipfile.ZipFile(self.source,'w') as z: z.writestr('word/document.xml',xml)
        node,path=next((n,p) for n,p in paths(ET.fromstring(xml)) if n.tag=='{'+w+'}p')
        self.feature={'id':'P001','kind':'paragraph','part':'word/document.xml','xml_path':path,
                      'guard_sha256':hashlib.sha256(ET.tostring(node,encoding='utf-8')).hexdigest(),
                      'effective_sample_format':{'paragraph':{'snapToGrid':{'val':'1'}},
                          'run':{'rFonts':{'ascii':'Times New Roman','eastAsia':'宋体'}}}}
        self.review=self.root/'review.json'; self.review.write_text('{}',encoding='utf-8')
        self.binding=self.root/'bindings.json'
        self.data={'source_sha256':sha(self.source),'roles':[{'role':'subsection','sample_id':'P001',
            'evidence_ids':['P001'],'rationale':'Explicit reviewed font requirement',
            'overrides':{'paragraph':{'outlineLvl':{'val':'2'}},'run':{'sz':{'val':'24'}}}}]}
    def compile(self):
        self.binding.write_text(json.dumps(self.data),encoding='utf-8')
        with patch('compile_role_bindings.verify_review',return_value=({}, {'features':[self.feature]})):
            return compile_bindings(self.source,self.review,self.binding)
    def test_properties_with_distinct_scope(self):
        r=self.compile(); self.assertFalse(r['complete_document_contract'])
        self.assertEqual(r['roles']['subsection']['properties']['run']['rFonts']['eastAsia'],'宋体')
        self.assertEqual(r['roles']['subsection']['properties']['paragraph']['outlineLvl']['val'],'2')
    def test_duplicate_rejected(self):
        self.data['roles']*=2
        with self.assertRaisesRegex(ValueError,'Duplicate'): self.compile()
    def test_missing_evidence_rejected(self):
        self.data['roles'][0]['evidence_ids']=[]
        with self.assertRaisesRegex(ValueError,'evidence'): self.compile()
    def test_guard_rejected(self):
        self.feature['guard_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'guard'): self.compile()
    def test_complex_properties_rejected(self):
        self.feature['effective_sample_format']['paragraph']['numPr']={}
        with self.assertRaisesRegex(ValueError,'dedicated'): self.compile()

if __name__=='__main__': unittest.main()

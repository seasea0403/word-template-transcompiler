"""Synthetic forward checks for the portable interface and package audit."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from verify_docx import audit

HERE = Path(__file__).resolve().parent
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/package/2006/relationships'


def fixture(path, broken=False):
    target='missing' if broken else 'destination'
    body=f'''<w:document xmlns:w="{W}"><w:body>
    <w:p><w:bookmarkStart w:id="1" w:name="destination"/>
    <w:r><w:t>Independent synthetic template</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p>
    <w:p><w:hyperlink w:anchor="{target}"><w:r><w:t>Link</w:t></w:r></w:hyperlink></w:p>
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134"/></w:sectPr>
    </w:body></w:document>'''
    with zipfile.ZipFile(path, 'x') as archive:
        archive.writestr('word/document.xml',body)
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        archive.writestr('_rels/.rels',f'<Relationships xmlns="{R}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')


class SkillTests(unittest.TestCase):
    def test_intake_relocatable_unchanged_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'unseen.docx';fixture(source)
            original=hashlib.sha256(source.read_bytes()).hexdigest()
            command=[sys.executable,str(HERE/'word_template.py'),'intake','--template',str(source),'--out-dir',str(root/'intake')]
            result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            receipt=json.loads((root/'intake/intake-receipt.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['source_sha256'],original)
            self.assertEqual(receipt['semantic_review'],'not_performed')
            self.assertTrue((root/'intake/features/features.json').is_file())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),original)
            self.assertNotEqual(subprocess.run(command,cwd=root,capture_output=True).returncode,0)

    def test_good_document_and_independent_expectations(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'template.docx';fixture(source)
            result=audit(source,source,{'exact_counts':{'tables':0,'bookmarks':1},
                'required_text':['Independent synthetic template'],
                'sections':[{'pgMar':{'top':'1134'}}],
                'preserve_parts':['word/document.xml']})
            self.assertTrue(result['passed'],result['errors'])

    def test_broken_link_rejected_for_its_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'broken.docx';fixture(source,True)
            result=audit(source)
            self.assertFalse(result['passed'])
            self.assertTrue(any(e['check'].startswith('hyperlink_anchor:') for e in result['errors']))

    def test_wrong_content_and_margin_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'template.docx';fixture(source)
            result=audit(source,expected={'required_text':['absent required text'],
                'sections':[{'pgMar':{'top':'999'}}]})
            names={e['check'] for e in result['errors']}
            self.assertIn('required_text',names)
            self.assertIn('section:0:pgMar',names)

    def test_duplicate_package_part_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'duplicate.docx'
            with zipfile.ZipFile(source,'x') as archive:
                archive.writestr('word/document.xml','<x/>')
                archive.writestr('word/document.xml','<y/>')
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                audit(source)


if __name__=='__main__':
    unittest.main()

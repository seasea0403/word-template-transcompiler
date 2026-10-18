"""Synthetic, institution-independent tests for read-only table evidence."""
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from inspect_table_samples import borders, inspect, Q
from feature_extraction import digest

class TableEvidenceTests(unittest.TestCase):
    def test_missing_is_not_hidden(self):
        self.assertIsNone(borders(None))
        self.assertEqual(borders(ET.fromstring(f'<w:b xmlns:w="{Q[1:-1]}"/>')), {})

    def test_units_and_explicit_hidden(self):
        node=ET.fromstring(f'<w:b xmlns:w="{Q[1:-1]}"><w:top w:val="single" w:sz="6"/><w:left w:val="nil"/></w:b>')
        result=borders(node)
        self.assertEqual(result['top']['width_pt'], .75)
        self.assertEqual(result['left']['visibility'], 'explicit_hidden')

    def fixture(self, p):
        source=p/'source.docx'
        with zipfile.ZipFile(source,'w') as z:
            z.writestr('word/document.xml', f'<w:document xmlns:w="{Q[1:-1]}"><w:body><w:tbl><w:tblPr/><w:tr><w:tc><w:p><w:r><w:t>Example</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
            z.writestr('word/styles.xml', f'<w:styles xmlns:w="{Q[1:-1]}"/>')
        f=p/'features.json'
        f.write_text(json.dumps({'source':str(source),'source_sha256':digest(source.read_bytes())}),encoding='utf-8')
        return source,f

    def test_paths_text_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); source,f=self.fixture(p); before=source.read_bytes()
            result=inspect(f,p/'result')
            self.assertEqual(result,{'table_count':1,'source_unchanged':True})
            table=json.loads((p/'result/table-samples.json').read_text(encoding='utf-8'))['tables'][0]
            cell=table['rows'][0]['cells'][0]
            self.assertTrue(cell['path'].endswith('tc[1]'))
            self.assertEqual(cell['text'],'Example')
            self.assertEqual(source.read_bytes(),before)

    def test_changed_source_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); source,f=self.fixture(p); source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Source hash mismatch'): inspect(f,p/'result')
            self.assertFalse((p/'result').exists())

if __name__=='__main__': unittest.main(verbosity=2)

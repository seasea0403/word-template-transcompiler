import tempfile
import unittest
import zipfile
from pathlib import Path
from lxml import etree as E
from repair_open_fields import repair, W

class OpenFields(unittest.TestCase):
    def test_only_tc_hidden_and_caches_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory); src=d/'source.docx'
            document=f'<w:document xmlns:w="{W[1:-1]}"><w:body><w:p><w:r><w:t>正文</w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> TC "摘要" \\f A </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r><w:fldSimple w:instr=" PAGEREF heading \\h "><w:r><w:t>III</w:t></w:r></w:fldSimple></w:p></w:body></w:document>'
            with zipfile.ZipFile(src,'w') as z:
                z.writestr('word/document.xml',document.encode())
                z.writestr('word/settings.xml',f'<w:settings xmlns:w="{W[1:-1]}"><w:updateFields w:val="true"/></w:settings>')
                z.writestr('word/media/image.png',b'opaque preserved image')
            result=repair(src,d/'fixed.docx',d/'receipt.json')
            self.assertEqual(result['hidden_tc_fields'],1)
            with zipfile.ZipFile(d/'fixed.docx') as z:
                root=E.fromstring(z.read('word/document.xml'))
                self.assertIsNone(root.find('.//'+W+'r').find(W+'rPr'))
                self.assertEqual(len(list(root.iter(W+'vanish'))),3)
                self.assertEqual(z.read('word/media/image.png'),b'opaque preserved image')
                self.assertIn('III',''.join(root.itertext()))
                settings=E.fromstring(z.read('word/settings.xml'))
                self.assertEqual(settings.find(W+'updateFields').get(W+'val'),'false')
            with self.assertRaises(FileExistsError):repair(src,d/'fixed.docx',d/'new.json')

if __name__=='__main__':unittest.main()

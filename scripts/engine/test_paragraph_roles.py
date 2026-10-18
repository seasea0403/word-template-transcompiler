import unittest
from lxml import etree as E
from paragraph_roles import W,resolve_sample,compile_role,apply_role

class Tests(unittest.TestCase):
    def fixture(self):
        s=E.fromstring(('<w:styles xmlns:w="'+W[1:-1]+'"><w:style w:type="paragraph" w:default="1" w:styleId="N"><w:pPr><w:ind w:firstLineChars="200"/></w:pPr><w:rPr><w:rFonts w:eastAsiaTheme="minorEastAsia"/></w:rPr></w:style><w:style w:styleId="H"><w:basedOn w:val="N"/><w:rPr><w:rFonts w:eastAsia="黑体"/><w:sz w:val="28"/></w:rPr></w:style></w:styles>').encode())
        p=E.fromstring(('<w:p xmlns:w="'+W[1:-1]+'"><w:pPr><w:pStyle w:val="H"/></w:pPr><w:r><w:t>标题</w:t></w:r></w:p>').encode())
        return p,s
    def test_inherited_grid(self):
        p,s=self.fixture(); self.assertEqual(resolve_sample(p,s)['paragraph']['snapToGrid']['val'],'1')
    def test_script_font_overrides_inherited_theme(self):
        p,s=self.fixture(); v=resolve_sample(p,s); self.assertEqual(v['run']['rFonts']['eastAsia'],'黑体'); self.assertFalse(v['theme_unresolved'])
    def test_no_blanket_grid_disable(self):
        p,s=self.fixture(); apply_role(p,compile_role(resolve_sample(p,s))); self.assertEqual(p.find(W+'pPr/'+W+'snapToGrid').get(W+'val'),'1')
    def test_role_specific_indent(self):
        p,s=self.fixture(); role=compile_role(resolve_sample(p,s),{'paragraph':{'ind':{'firstLine':'420'}}}); apply_role(p,role); self.assertIsNone(p.find(W+'pPr/'+W+'ind').get(W+'firstLineChars'))
    def test_unresolved_theme_fails(self):
        p,s=self.fixture(); p.find(W+'pPr/'+W+'pStyle').set(W+'val','N'); self.assertRaises(ValueError,compile_role,resolve_sample(p,s))
    def test_cycle_fails(self):
        p,s=self.fixture(); E.SubElement(s[0],W+'basedOn').set(W+'val','H'); self.assertRaises(ValueError,resolve_sample,p,s)
    def test_direct_physical_indent_not_cancelled_by_inheritance(self):
        p,s=self.fixture(); E.SubElement(p.find(W+'pPr'),W+'ind').set(W+'firstLine','480')
        v=resolve_sample(p,s)['paragraph']['ind']
        self.assertEqual(v['firstLine'],'480'); self.assertNotIn('firstLineChars',v)
    def test_explicit_grid_false_preserved(self):
        p,s=self.fixture(); E.SubElement(p.find(W+'pPr'),W+'snapToGrid').set(W+'val','0')
        self.assertEqual(resolve_sample(p,s)['paragraph']['snapToGrid']['val'],'0')
    def test_nested_link_destination_fonts_and_superscript(self):
        p,s=self.fixture(); h=E.SubElement(p,W+'hyperlink'); r=E.SubElement(h,W+'r'); pr=E.SubElement(r,W+'rPr')
        E.SubElement(pr,W+'rStyle').set(W+'val','ForeignStyle')
        E.SubElement(pr,W+'vertAlign').set(W+'val','superscript'); E.SubElement(r,W+'t').text='[1]'
        apply_role(p,compile_role(resolve_sample(p,s)),include_hyperlink_runs=True)
        pr=r.find(W+'rPr'); self.assertIsNone(pr.find(W+'rStyle'))
        self.assertEqual(pr.find(W+'rFonts').get(W+'eastAsia'),'黑体')
        self.assertEqual(pr.find(W+'vertAlign').get(W+'val'),'superscript')
if __name__=='__main__': unittest.main()

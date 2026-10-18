import unittest
from lxml import etree as E
from paragraph_roles import W
from toc_component import toc_entry, toc_left_indent
class Tests(unittest.TestCase):
    def test_first_line_is_not_left_indent(self):
        self.assertEqual(toc_left_indent({'ind':{'firstLine':'480'}},0),'0')
    def test_actual_left_indent_retained(self):
        self.assertEqual(toc_left_indent({'ind':{'firstLine':'480','left':'480','leftChars':'200'}},1),'480')
    def test_reviewed_missing_level(self):
        self.assertEqual(toc_left_indent({},2,[0,480,960]),'960')
        with self.assertRaises(ValueError):toc_left_indent({},3,[0,480,960])
    def sample(self):
        p=E.Element(W+'p');pr=E.SubElement(p,W+'pPr');E.SubElement(pr,W+'pStyle').set(W+'val','source-toc')
        tabs=E.SubElement(pr,W+'tabs');E.SubElement(tabs,W+'tab',{W+'val':'right',W+'leader':'dot',W+'pos':'9000'})
        r=E.SubElement(p,W+'r');rp=E.SubElement(r,W+'rPr');E.SubElement(rp,W+'rFonts').set(W+'eastAsia','SourceFont');E.SubElement(r,W+'t').text='old title'
        return p
    def test_source_unchanged(self):
        s=self.sample();before=E.tostring(s);toc_entry(s,'New title','heading_a','IV');self.assertEqual(E.tostring(s),before)
    def test_independent_source_fonts(self):
        p=toc_entry(self.sample(),'New title','heading_a','IV');self.assertEqual(p.find('.//'+W+'rFonts').get(W+'eastAsia'),'SourceFont')
        self.assertEqual(p.find(W+'pPr/'+W+'pStyle').get(W+'val'),'source-toc')
    def test_anchor_and_pageref_consistent(self):
        p=toc_entry(self.sample(),'New title','heading_a','IV');self.assertEqual(p.find(W+'hyperlink').get(W+'anchor'),'heading_a')
        self.assertIn('PAGEREF heading_a',p.find(W+'fldSimple').get(W+'instr'))
        self.assertEqual(p.find(W+'fldSimple/'+W+'r/'+W+'t').text,'IV')
    def test_dot_leader_preserved(self):
        p=toc_entry(self.sample(),'New title','heading_a','3');self.assertEqual(p.find(W+'pPr/'+W+'tabs/'+W+'tab').get(W+'leader'),'dot')
if __name__=='__main__':unittest.main()

import unittest
from lxml import etree as E
from cover_adapter import W, replace_span, replace_plain, replace_title_lines, node_text

class Tests(unittest.TestCase):
    def sample(self):
        return E.fromstring(f'<w:p xmlns:w="{W[1:-1]}"><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t>label:</w:t></w:r><w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>abc</w:t></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>def tail</w:t></w:r></w:p>')
    def test_cross_run_span(self):
        p=self.sample(); props=[E.tostring(r.find(W+'rPr')) for r in p.findall(W+'r')]
        replace_span(p,7,11,'NEW')
        self.assertEqual(''.join(p.itertext()),'label:aNEWf tail')
        self.assertEqual(props,[E.tostring(r.find(W+'rPr')) for r in p.findall(W+'r')])
    def test_invalid_span(self):
        with self.assertRaisesRegex(ValueError,'Invalid'): replace_span(self.sample(),-1,2,'x')
    def test_drawings_rejected(self):
        p=self.sample(); E.SubElement(p.find(W+'r'),W+'drawing')
        with self.assertRaisesRegex(ValueError,'Non-text'): replace_span(p,6,7,'x')
    def test_empty_insertion_requires_properties(self):
        with self.assertRaisesRegex(ValueError,'character properties'): replace_plain(E.Element(W+'p'),'x')
    def test_title_break_conserves_text_and_properties(self):
        p=self.sample(); before=[E.tostring(r.find(W+'rPr')) for r in p.findall(W+'r')]
        replace_title_lines(p,'full title',['full ','title'])
        self.assertEqual(node_text(p),'full title')
        self.assertEqual(len(list(p.iter(W+'br'))),1)
        self.assertEqual(before,[E.tostring(r.find(W+'rPr')) for r in p.findall(W+'r')])
    def test_short_title_no_break(self):
        p=self.sample(); replace_title_lines(p,'short',['short',''])
        self.assertEqual(len(list(p.iter(W+'br'))),0)
    def test_title_rejects_missing_text(self):
        with self.assertRaisesRegex(ValueError,'conserve'): replace_title_lines(self.sample(),'full',['fu',''])
    def test_bookmark_boundary_kept(self):
        p=self.sample(); b=E.Element(W+'bookmarkStart'); b.set(W+'id','12'); b.set(W+'name','example'); p.insert(1,b)
        replace_span(p,6,9,'new')
        self.assertEqual(E.tostring(p.find(W+'bookmarkStart')),E.tostring(b))
        self.assertEqual(''.join(p.itertext()),'label:newdef tail')

if __name__=='__main__': unittest.main()

import unittest
from blank_flow import extract
from full_writer import paragraph,W
from cover_adapter import clear_fullwidth_span,node_text
from lxml import etree as E

class Tests(unittest.TestCase):
    def f(self,ident,txt,size=44):
        return {'id':ident,'text':txt,'effective_sample_format':{'paragraph':{'spacing':{'line':'360','lineRule':'exact'},'outlineLvl':{'val':'0'}},'run':{'sz':{'val':str(size)},'rFonts':{'ascii':'Times New Roman','eastAsia':'宋体'}}}}
    def test_scoped_size_beats_title(self):
        c=extract({'features':[self.f('a','（空三行，空行都以四号字体为准，下同）'),self.f('b','（空两行）')]})
        self.assertEqual(c['b']['properties']['run']['sz']['val'],'28')
        self.assertEqual(c['b']['evidence_ids'],['a','b'])
        self.assertEqual(c['b']['count'],2)
    def test_local_beats_scoped(self):
        c=extract({'features':[self.f('a','（空一行，空行四号，下同）'),self.f('b','（空两行，小四号）')]})
        self.assertEqual(c['b']['properties']['run']['sz']['val'],'24')
    def test_sample_when_no_prose(self):
        c=extract({'features':[self.f('a','（空两行）',24)]})
        self.assertEqual(c['a']['properties']['run']['sz']['val'],'24')
        self.assertNotIn('outlineLvl',c['a']['properties']['paragraph'])
    def test_empty_paragraph_mark_size(self):
        role=extract({'features':[self.f('a','（空两行）',28)]})['a']['properties']
        self.assertEqual(paragraph('',role).find(W+'pPr/'+W+'rPr/'+W+'sz').get(W+'val'),'28')
    def test_clear_keeps_run_boundaries_and_padding(self):
        p=E.fromstring(f'<w:p xmlns:w="{W[1:-1]}"><w:r><w:t>学院:   </w:t></w:r><w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>工程</w:t></w:r><w:r><w:t>学院   </w:t></w:r></w:p>')
        before=[E.tostring(r.find(W+'rPr')) if r.find(W+'rPr') is not None else None for r in p]
        clear_fullwidth_span(p,6,10)
        self.assertEqual(node_text(p),'学院:   '+'\u00a0'*4+'   ')
        self.assertEqual(before,[E.tostring(r.find(W+'rPr')) if r.find(W+'rPr') is not None else None for r in p])
    def test_proportional_clear_fails(self):
        p=E.fromstring(f'<w:p xmlns:w="{W[1:-1]}"><w:r><w:t>ABC</w:t></w:r></w:p>')
        with self.assertRaisesRegex(ValueError,'measured'):clear_fullwidth_span(p,0,3)

if __name__=='__main__':unittest.main()

import unittest
from unittest.mock import patch
from lxml import etree as E
from cover_adapter import fill_underlined_slot, W, node_text

class Page:
    lines=[{'top':100,'bottom':100,'x0':170,'x1':466}]
    def extract_words(self):return [{'text':'example','bottom':100}]
class PDF:
    pages=[Page()]
    def __enter__(self):return self
    def __exit__(self,*args):pass
class Tests(unittest.TestCase):
    def field(self):
        p=E.Element(W+'p');E.SubElement(p,W+'pPr')
        r=E.SubElement(p,W+'r');E.SubElement(r,W+'t').text='Label:'
        r=E.SubElement(p,W+'r');rp=E.SubElement(r,W+'rPr')
        E.SubElement(rp,W+'u',{W+'val':'single'})
        E.SubElement(rp,W+'sz',{W+'val':'32'})
        E.SubElement(r,W+'t').text=' '*37
        return p
    def write(self,value):
        p=self.field()
        with patch('cover_adapter.pdfplumber.open',return_value=PDF()),patch('cover_adapter.sha',return_value='hash'):
            fill_underlined_slot(p,{'reference_pdf':'unused','reference_page':1,'geometry_example':'example','start':6,'end':43,'margin_left_twips':1417},value)
        return p
    def test_blank_field_remains_visible_native_tab(self):
        p=self.write('');self.assertEqual(node_text(p),'Label:')
        self.assertEqual(len(p.findall('.//'+W+'tab')),2)
        self.assertEqual(p.find(W+'pPr/'+W+'tabs/'+W+'tab').get(W+'pos'),'7903')
    def test_value_and_typography_conserved(self):
        p=self.write('Author');self.assertEqual(node_text(p),'Label:Author')
        self.assertEqual(p[-1].find(W+'rPr/'+W+'sz').get(W+'val'),'32')
        self.assertEqual(p.find(W+'pPr/'+W+'tabs/'+W+'tab').get(W+'val'),'center')

if __name__=='__main__':unittest.main()

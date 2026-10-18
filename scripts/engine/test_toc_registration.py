import unittest
from lxml import etree as E
from full_writer import Writer, W
class Tests(unittest.TestCase):
    def test_registered_target_has_matching_lowercase_identifier_and_level(self):
        w=Writer.__new__(Writer);w.c={'toc':{'number_title_separator':'  '}};w.targets=[];w.bid=1
        p=E.Element(W+'p');E.SubElement(p,W+'pPr')
        w.target(p,'1.2 Title',1)
        code=p.find('.//'+W+'instrText').text
        self.assertIn('\\f a',code);self.assertIn('\\l "2"',code);self.assertIn('1.2  Title',code)
        self.assertEqual(len(list(p.iter(W+'instrText'))),1)
if __name__=='__main__':unittest.main()

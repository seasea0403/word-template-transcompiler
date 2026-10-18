import unittest
from unittest.mock import patch
from finalize_toc import locate

class Page:
    height=800;width=600
    def __init__(self,text,footer):self.text=text;self.footer=footer
    def extract_text(self):return self.text
    def crop(self,box):return Page(self.footer,self.footer)
class PDF:
    def __init__(self,pages):self.pages=pages
    def __enter__(self):return self
    def __exit__(self,*args):pass
class CacheTests(unittest.TestCase):
    def run_map(self,pages,targets):
        with patch('finalize_toc.pdfplumber.open',return_value=PDF(pages)):return locate('unused',targets)
    def base(self):return [Page('目 录\n摘要.....?\n正文.....?\n文献.....?','III'),Page('1 正文','1')]
    def target(self):return [{'anchor':'h1','label':'1 正文','search_text':'1 正文'}]
    def test_uses_footer_not_physical(self):
        m=self.run_map(self.base(),self.target());self.assertEqual(m['targets']['h1']['page_label'],'1');self.assertEqual(m['targets']['h1']['physical_page'],2)
    def test_duplicate_heading_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous/missing'):self.run_map(self.base()+[Page('1 正文','2')],self.target())
    def test_missing_footer_rejected(self):
        pages=self.base();pages[1].footer=''
        with self.assertRaisesRegex(ValueError,'Ambiguous footer'):self.run_map(pages,self.target())
    def test_self_toc(self):
        t=[{'anchor':'asc_toc','label':'目    录','search_text':'目    录'}]
        self.assertEqual(self.run_map(self.base(),t)['targets']['asc_toc']['page_label'],'III')
    def test_inline_abstract_prefix_spans_lines(self):
        t=[{'anchor':'abstract','label':'摘要','search_text':'摘要 本文整理数据'}]
        self.assertEqual(self.run_map(self.base()+[Page('摘要 本文整理\n数据，后文','IV')],t)['targets']['abstract']['page_label'],'IV')
    def test_no_toc_rejected(self):
        with self.assertRaisesRegex(ValueError,'No unambiguous'):self.run_map([Page('1 正文','1')],self.target())

if __name__=='__main__':unittest.main()

import unittest
from title_layout import distribute_title

class Tests(unittest.TestCase):
    def test_short(self): self.assertEqual(distribute_title('短题名',[1,2],[10,10],len)['lines'],['短题名',''])
    def test_balance(self): self.assertEqual(distribute_title('abcdef',[2,3,4],[4,4],len)['lines'],['abc','def'])
    def test_no_split_word(self):
        with self.assertRaises(ValueError): distribute_title('abcdef',[1,5],[4,4],len)
    def test_oversize(self):
        with self.assertRaises(ValueError): distribute_title('a'*20,[10],[5,5],len)
    def test_punctuation(self): self.assertEqual(distribute_title('ab，cd',[2,3],[4,4],len)['lines'],['ab，','cd'])
    def test_exact(self):
        t='sample title with spaces'; r=distribute_title(t,[7,13,18],[16,16],len); self.assertEqual(''.join(r['lines']),t)
    def test_invalid_measurement(self):
        with self.assertRaises(ValueError): distribute_title('abc',[1],[10,10],lambda t:float('nan'))
    def test_protect_domain_term(self):
        r=distribute_title('abCDEFgh',[2,4,6],[7,7],len,protected_terms=['CDEF'])
        self.assertNotEqual(r['split_index'],4)
if __name__=='__main__': unittest.main()

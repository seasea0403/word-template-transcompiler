import unittest
from lxml import etree as E
from full_writer import W, node, replace_equation_links


class EquationLinks(unittest.TestCase):
    def test_unseen_id_resolves_and_unrelated_link_survives(self):
        p=E.Element(W+'p')
        node(p,'hyperlink',anchor='equation-unseen-42')
        node(p,'hyperlink',anchor='other-target')
        replace_equation_links(p,{'equation-unseen-42':{'anchor':'safe_bookmark','number':'4-2'}},None)
        self.assertEqual(len(p.findall(W+'fldSimple')),1)
        self.assertIn('REF safe_bookmark',p.find(W+'fldSimple').get(W+'instr'))
        self.assertEqual(p.find(W+'hyperlink').get(W+'anchor'),'other-target')

    def test_nested_link_fails_instead_of_corrupting(self):
        p=E.Element(W+'p');nested=node(p,'sdt');node(nested,'hyperlink',anchor='eq')
        with self.assertRaisesRegex(ValueError,'Nested equation link'):
            replace_equation_links(p,{'eq':{'anchor':'eq','number':'1'}},None)


if __name__=='__main__':unittest.main()

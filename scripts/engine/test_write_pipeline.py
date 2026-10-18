import copy
import tempfile
import unittest
from pathlib import Path
from manuscript_ir import image_resource, inventory
from write_pipeline import compile_plan


def string(value): return {'t': 'Str', 'c': value}
def header(level, ident, value):
    return {'t': 'Header', 'c': [level, [ident, [], []], [string(value)]]}
def para(value): return {'t': 'Para', 'c': [string(value)]}
def fixture():
    return {'meta': {}, 'blocks': [header(1, 'chapter', '第一章 内容'),
                                  para('结果[1]'), header(2, 'section', '1.1 方法'),
                                  header(1, 'references', '参考文献'),
                                  para('[1] Author. Title. DOI: 10.x/y.')]}


class Tests(unittest.TestCase):
    def test_inventory_roles_and_references(self):
        result = inventory(fixture(), Path('content.md'))
        self.assertEqual(result['chapter_count'], 1)
        self.assertEqual(result['citation_mentions'][0]['reference_id'], '1')
        self.assertEqual(result['objects'][2]['role'], 'section')
        self.assertEqual(len(result['bibliography']), 1)

    def test_ast_unchanged(self):
        source = fixture(); before = copy.deepcopy(source)
        inventory(source, Path('content.md'))
        self.assertEqual(source, before)

    def test_missing_reference(self):
        source = fixture(); source['blocks'][1] = para('结果[2]')
        with self.assertRaisesRegex(ValueError, 'Missing bibliography'):
            inventory(source, Path('content.md'))

    def test_duplicate_anchor(self):
        source = fixture(); source['blocks'][2]['c'][1][0] = 'chapter'
        with self.assertRaisesRegex(ValueError, 'Duplicate anchor'):
            inventory(source, Path('content.md'))

    def test_dangling_link(self):
        source = fixture()
        source['blocks'][1] = {'t': 'Para', 'c': [
            {'t': 'Link', 'c': [['', [], []], [string('式')], ['#missing', '']]}]}
        with self.assertRaisesRegex(ValueError, 'Dangling manuscript link'):
            inventory(source, Path('content.md'))

    def test_raw_markup_rejected(self):
        source = fixture(); source['blocks'].append({'t': 'RawBlock', 'c': ['html', '<x>']})
        with self.assertRaisesRegex(ValueError, 'Raw markup'):
            inventory(source, Path('content.md'))

    def test_image_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            manuscript = Path(directory)/'content.md'
            with self.assertRaisesRegex(ValueError, 'escapes'):
                image_resource('../outside.png', manuscript)
            with self.assertRaisesRegex(ValueError, 'relative local'):
                image_resource('https://example.org/image.png', manuscript)

    def test_plan_cannot_author(self):
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory)/'template.docx'; template.write_bytes(b'fixture')
            inv = inventory(fixture(), Path('content.md'))
            ir = {**inv, 'source_sha256': 'fixture'}
            result = compile_plan(ir, {'rules': []}, template, Path(directory)/'output.docx')
            self.assertFalse(result['authoring_allowed'])
            self.assertTrue(result['blocking_requirements'])
            self.assertTrue(all(a['not_an_executable_mutation'] for a in result['actions']))


if __name__ == '__main__': unittest.main()

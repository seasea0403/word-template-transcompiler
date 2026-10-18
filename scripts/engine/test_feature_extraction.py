"""Synthetic reason-specific tests. Not evidence of actual template interpretation."""
import argparse
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import zipfile
from feature_extraction import Q, cues, direct_format, section_properties, prepare, assemble
from inspect_docx import survey as inspect_survey

class Features(unittest.TestCase):
    def test_named_sizes_are_units_not_case_defaults(self):
        self.assertEqual([m['points'] for m in cues('小二号 二号 小四号 三号 五号')['size_mentions']], [18,22,12,16,10.5])

    def test_mixed_roles_do_not_become_one_rule(self):
        found = cues('标签（四号黑体）（空两格）正文（小四号宋体）')
        self.assertEqual(len(found['font_mentions']), 2)
        self.assertEqual(len(found['size_mentions']), 2)
        self.assertEqual(found['space_mentions'][0]['text'], '空两格')
        self.assertIn('scope_unresolved',found['size_mentions'][0]['status'])

    def test_auto_and_fixed_line_spacing_differ(self):
        exact = direct_format(f'<w:pPr xmlns:w="{Q[1:-1]}"><w:spacing w:line="460" w:lineRule="exact"/></w:pPr>')
        auto = direct_format(f'<w:pPr xmlns:w="{Q[1:-1]}"><w:spacing w:line="460"/></w:pPr>')
        self.assertEqual(exact['line_spacing']['amount'],23)
        self.assertAlmostEqual(auto['line_spacing']['amount'],460/240)
        self.assertNotIn('size_pt', auto)

    def test_repeated_header_refs_not_discarded(self):
        value = section_properties(f'<w:sectPr xmlns:w="{Q[1:-1]}"><w:headerReference w:type="default"/><w:headerReference w:type="even"/></w:sectPr>')
        self.assertEqual(len(value['child_records']),2)

    def make_fixture(self, root):
        source = root/'synthetic.docx'
        xml = f'<w:document xmlns:w="{Q[1:-1]}"><w:body><w:p><w:r><w:t>示例（小二号）</w:t></w:r></w:p></w:body></w:document>'.encode()
        with zipfile.ZipFile(source,'w') as z:
            z.writestr('word/document.xml',xml)
        sha = lambda b:hashlib.sha256(b).hexdigest()
        paragraph = {'part':'word/document.xml','xml_path':'synthetic-path','guard_sha256':'a'*64,
                     'text':'示例（小二号）','direct_paragraph_properties':None,'runs':[]}
        survey = inspect_survey(source)
        path = root/'survey.json'; path.write_text(json.dumps(survey),encoding='utf-8')
        return source,path

    def test_input_mismatch_rejected_before_output(self):
        with tempfile.TemporaryDirectory(prefix='asc-feature-test-') as name:
            root=Path(name); source,survey=self.make_fixture(root)
            data=json.loads(survey.read_text()); data['source_sha256']='0'*64
            survey.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'does not match source'):
                prepare(source,survey,root/'run')
            self.assertFalse((root/'run').exists())

    def test_exact_evidence_quote_and_snapshot_guards(self):
        with tempfile.TemporaryDirectory(prefix='asc-feature-test-') as name:
            root=Path(name); source,survey=self.make_fixture(root)
            prepare(source,survey,root/'run')
            features=root/'run/features.json'
            ann={'schema_version':'feature-annotations/1','feature_snapshot_sha256':hashlib.sha256(features.read_bytes()).hexdigest(),
                 'evidence':[{'id':'e','feature_id':'P001','kind':'explicit_instruction','quote':'不存在的引文','limitations':['synthetic']}],
                 'classifications':[]}
            annotation=root/'ann.json'; annotation.write_text(json.dumps(ann),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'quote is absent'):
                assemble(features,annotation,root/'bad')
            ann['evidence'][0]['quote']='小二号'; annotation.write_text(json.dumps(ann),encoding='utf-8')
            result=assemble(features,annotation,root/'good')
            self.assertEqual(result['unclassified_features'],2)
            ann['feature_snapshot_sha256']='0'*64; annotation.write_text(json.dumps(ann),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'exact feature snapshot'):
                assemble(features,annotation,root/'stale')

    def test_this_stage_cannot_invent_rendering(self):
        with tempfile.TemporaryDirectory(prefix='asc-feature-test-') as name:
            root=Path(name); source,survey=self.make_fixture(root)
            prepare(source,survey,root/'run'); features=root/'run/features.json'
            ann={'schema_version':'feature-annotations/1','feature_snapshot_sha256':hashlib.sha256(features.read_bytes()).hexdigest(),
                 'evidence':[{'id':'e','feature_id':'P001','kind':'render_observation','quote':None,'limitations':[]}], 'classifications':[]}
            annotation=root/'ann.json'; annotation.write_text(json.dumps(ann),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'cannot certify rendering'):
                assemble(features,annotation,root/'bad')

    def test_visual_review_wrong_source_rejected(self):
        with tempfile.TemporaryDirectory(prefix='asc-feature-test-') as name:
            root=Path(name); source,survey=self.make_fixture(root)
            prepare(source,survey,root/'run'); features=root/'run/features.json'
            ann={'schema_version':'feature-annotations/1','feature_snapshot_sha256':hashlib.sha256(features.read_bytes()).hexdigest(),
                 'evidence':[], 'classifications':[]}
            annotation=root/'ann.json'; annotation.write_text(json.dumps(ann),encoding='utf-8')
            receipt=root/'receipt.json'; receipt.write_text('{}',encoding='utf-8')
            visual=root/'visual.json'; visual.write_text(json.dumps({'schema_version':'template-visual-review/1',
                'source_sha256':'0'*64,'render_receipt':str(receipt),
                'render_receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'not bound to this source'):
                assemble(features,annotation,root/'bad',visual)
            self.assertFalse((root/'bad').exists())

    def test_mutated_cached_text_rejected(self):
        with tempfile.TemporaryDirectory(prefix='asc-feature-test-') as name:
            root=Path(name); source,survey=self.make_fixture(root)
            data=json.loads(survey.read_text()); data['paragraphs'][0]['text']='伪造内容'
            survey.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'facts do not match source XML'):
                prepare(source,survey,root/'bad')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--report',type=Path,required=True); args=parser.parse_args()
    if args.report.exists(): raise ValueError('Preserve earlier reports')
    stream=io.StringIO(); result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Features))
    report={'passed':result.wasSuccessful(),'count':result.testsRun,'details':stream.getvalue(),
            'scope':'Synthetic feature and evidence guard tests; not real Word layout or semantic accuracy validation'}
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'count':report['count']}))
    if not result.wasSuccessful(): raise SystemExit(1)

if __name__=='__main__': main()

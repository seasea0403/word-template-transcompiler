"""Synthetic contract tests; no claim of Word authoring or interaction."""
import argparse
import copy
import io
import json
from pathlib import Path
import unittest
from test_contract import fixture
from validate import load_validator, validate

HERE=Path(__file__).resolve().parent
def content():
    return {'representation':'omml','editable_required':True,'display_mode':'display','source_notation':'latex','preserve_math_semantics':True}
def layout():
    return {'formula_alignment':'center','numbered':True,'number_alignment':'right','number_pattern':'({number})',
        'separation':'tab_stops','leader':'none','long_formula_break':'review','keep_number_with_formula':True}
def navigation():
    return {'target_role_id':'r','anchor_policy':'stable_unique_bookmark','display':'target_number',
        'link_required':True,'target_match_required':True,'update_mode':'word_fields',
        'verification':['structural_target','display_matches_number','click_target','after_edit_update']}
def inheritance():
    return {'strategy':'copy_template','source_id':'s','section_locator_ids':['l'],
        'properties':['size','margins'],'original_immutable':True,'work_on_copy':True,
        'section_policy':'remap_to_content','header_footer_policy':'preserve_reviewed',
        'page_number_policy':'remap_to_content','verify_effective_settings':True}

class Domains(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not hasattr(cls,'validator'):cls.validator=load_validator()
        if not hasattr(cls,'schema'):cls.schema=json.loads((HERE/'schema.json').read_text(encoding='utf-8'))
    def run_rule(self,name,data,reason=None,contract=None):
        c=fixture() if contract is None else contract
        c['rules'][0].update(property=name,value={'type':'structured','data':data})
        r=validate(c,self.schema,self.validator)
        self.assertEqual(r['valid'],reason is None,r)
        if reason: self.assertIn(reason,[p['code'] for p in r['issues']],r)
    def test_native(self): self.run_rule('equation.content',content())
    def test_image_not_editable(self):
        d=content(); d['representation']='image'; self.run_rule('equation.content',d,'equation_editability')
    def test_semantics_preserved(self):
        d=content(); d['preserve_math_semantics']=False; self.run_rule('equation.content',d,'equation_semantics')
    def test_layout(self): self.run_rule('equation.layout',layout())
    def test_number_placeholder(self):
        d=layout(); d['number_pattern']='(fixed)'; self.run_rule('equation.layout',d,'equation_number_layout')
    def test_number_attached(self):
        d=layout(); d['keep_number_with_formula']=False; self.run_rule('equation.layout',d,'equation_number_detached')
    def test_unnumbered(self):
        d=layout(); d.update(numbered=False,number_alignment=None,number_pattern=None,separation='none'); self.run_rule('equation.layout',d)
    def test_numbering(self):
        self.run_rule('equation.numbering',{'scope':'document','counter_id':'formula','start':1,'continuous':True,
            'unique':True,'reset_on_scope_change':False,'update_mode':'backend_rebuild'})
    def test_navigation(self): self.run_rule('equation.navigation',navigation())
    def test_click_check_required(self):
        d=navigation(); d['verification'].remove('click_target'); self.run_rule('equation.navigation',d,'equation_link_verification')
    def test_update_check_required(self):
        d=navigation(); d['verification'].remove('after_edit_update'); self.run_rule('equation.navigation',d,'equation_update_verification')
    def test_target_role_exists(self):
        d=navigation(); d['target_role_id']='absent'; self.run_rule('equation.navigation',d,'dangling_reference')
    def test_inheritance(self): self.run_rule('page.source_inheritance',inheritance())
    def test_never_edit_original(self):
        d=inheritance(); d['work_on_copy']=False; self.run_rule('page.source_inheritance',d,'page_inheritance_safety')
    def test_missing_section_locator(self):
        d=inheritance(); d['section_locator_ids']=['absent']; self.run_rule('page.source_inheritance',d,'dangling_reference')
    def test_wrong_source_kind(self):
        c=fixture(); c['sources'][0]['kind']='manuscript'; self.run_rule('page.source_inheritance',inheritance(),'page_inheritance_source',c)
    def test_other_source_locator(self):
        c=fixture(); s=copy.deepcopy(c['sources'][0]); s['id']='s2'; c['sources'].append(s)
        c['locators'][0]['source_id']='s2'; c['evidence'][0]['source_id']='s2'
        self.run_rule('page.source_inheritance',inheritance(),'page_inheritance_source',c)
    def test_unknown_fields_rejected(self):
        d=content(); d['pretend_verified']=True; self.run_rule('equation.content',d,'domain_schema')

def main():
    p=argparse.ArgumentParser(); p.add_argument('--deps',type=Path); p.add_argument('--report',type=Path,required=True); a=p.parse_args()
    if a.report.exists(): raise ValueError('Preserve previous test reports')
    Domains.validator=load_validator(a.deps); Domains.schema=json.loads((HERE/'schema.json').read_text(encoding='utf-8'))
    stream=io.StringIO(); result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Domains))
    report={'passed':result.wasSuccessful(),'count':result.testsRun,'details':stream.getvalue(),
        'scope':'Synthetic schema and rejection-reason tests; not OMML fidelity, Word interaction or page preservation execution'}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'count':report['count']}))
    if not report['passed']: raise SystemExit(1)
if __name__=='__main__': main()

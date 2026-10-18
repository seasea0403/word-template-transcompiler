"""Reason-specific synthetic tests of integrated sub-spec validation."""
import argparse
import copy
import io
import json
import unittest
from pathlib import Path
from test_contract import fixture
from validate import validate, load_validator

HERE=Path(__file__).resolve().parent

def borders():
    return {'model':'three_line','lines':{k:({'visible':True,'style':'single','width_pt':0.75,'color':'000000'}
        if k in ('top','header_bottom','bottom') else {'visible':False})
        for k in ('top','header_bottom','bottom','left','right','inside_horizontal','inside_vertical')},'auxiliary_lines':[]}

def bibliography():
    return {'ordering':'appearance','unreferenced_policy':'review','missing_field_policy':'block',
        'types':[{'type_id':'journal','required_fields':['author','title','year'],
            'optional_fields':['doi'],'field_order':['author','title','year','doi'],
            'type_marker':'J','pattern':'{author}. {title}[J]. {year}. DOI if available'}],
        'identifier_policy':{'doi':'preserve','url':'preserve','access_date':'if_available'}}

class Domains(unittest.TestCase):
    deps=None
    @classmethod
    def setUpClass(cls):
        cls.validator=load_validator(cls.deps)
        cls.schema=json.loads((HERE/'schema.json').read_text(encoding='utf-8'))

    def run_rule(self,name,data,reason=None):
        contract=fixture(); rule=contract['rules'][0]
        rule.update(property=name,value={'type':'structured','data':data})
        result=validate(contract,self.schema,self.validator)
        self.assertEqual(result['valid'],reason is None,result)
        if reason: self.assertIn(reason,[i['code'] for i in result['issues']],result)

    def test_valid_three_lines(self): self.run_rule('table.borders',borders())
    def test_reject_vertical_line(self):
        d=borders(); d['lines']['inside_vertical']={'visible':True,'style':'single','width_pt':1,'color':'000000'}
        self.run_rule('table.borders',d,'three_line_topology')
    def test_line_width_not_defaulted(self):
        d=borders(); del d['lines']['top']['width_pt']; self.run_rule('table.borders',d,'border_incomplete')
    def test_reject_negative_width(self):
        d=borders(); d['lines']['bottom']['width_pt']=-1; self.run_rule('table.borders',d,'domain_schema')
    def test_auxiliary_header_line(self):
        d=borders(); d['auxiliary_lines']=[{'after_header_row':2,'line':{'visible':True,'style':'single','width_pt':0.5,'color':'000000'}}]
        self.run_rule('table.borders',d)
    def test_row_indices(self): self.run_rule('table.row_selection',{'selector':'indices','indices':[2,4]})
    def test_row_indices_missing(self): self.run_rule('table.row_selection',{'selector':'indices'},'row_selector')
    def test_row_zero_rejected(self): self.run_rule('table.row_selection',{'selector':'indices','indices':[0]},'domain_schema')
    def test_continuation_valid(self):
        self.run_rule('table.continuation',{'mode':'caption_each_fragment','repeat_header':True,'caption_pattern':'续表{number}', 'caption_alignment':'right','split_rows':False})
    def test_continuation_missing_number(self):
        self.run_rule('table.continuation',{'mode':'caption_each_fragment','repeat_header':True,'caption_pattern':'续表','caption_alignment':'right','split_rows':False},'continuation_caption')
    def test_continuation_header_false(self):
        self.run_rule('table.continuation',{'mode':'repeat_header','repeat_header':False,'caption_pattern':None,'caption_alignment':None,'split_rows':False},'continuation_header')
    def test_citation_author_year(self):
        self.run_rule('references.citation_style',{'system':'author_year','placement':'inline','label_pattern':'({author}, {year})','multiple_separator':'; ', 'range_policy':'preserve','ordering':'author_year','link_policy':'optional'})
    def test_citation_typo(self):
        self.run_rule('references.citation_style',{'system':'numeric','placement':'supercript'},'domain_schema')
    def test_bibliography(self): self.run_rule('references.bibliography_style',bibliography())
    def test_bibliography_missing_required_in_order(self):
        d=bibliography(); d['types'][0]['field_order'].remove('year'); self.run_rule('references.bibliography_style',d,'reference_fields')
    def test_duplicate_type(self):
        d=bibliography(); d['types'].append(copy.deepcopy(d['types'][0])); self.run_rule('references.bibliography_style',d,'reference_type_duplicate')
    def test_unknown_field_not_silent(self):
        d=bibliography(); d['standard']='invented'; self.run_rule('references.bibliography_style',d,'domain_schema')
    def test_numbering_members_dangling(self):
        self.run_rule('numbering.consistency',{'members':['r','missing'],'scope':'chapter','continuous':True,'unique':True,'reset_on_scope_change':True},'dangling_reference')
    def test_numbering_members_valid(self):
        d=fixture(); role=copy.deepcopy(d['roles'][0]); role['id']='r2'; d['roles'].append(role)
        d['rules'][0].update(property='numbering.consistency',value={'type':'structured','data':{'members':['r','r2'],'scope':'document','continuous':True,'unique':True,'reset_on_scope_change':False}})
        self.assertTrue(validate(d,self.schema,self.validator)['valid'])

def main():
    p=argparse.ArgumentParser(); p.add_argument('--deps',type=Path); p.add_argument('--report',type=Path,required=True); a=p.parse_args()
    if a.report.exists(): raise ValueError('Preserve old reports')
    Domains.deps=a.deps
    stream=io.StringIO(); result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Domains))
    report={'passed':result.wasSuccessful(),'count':result.testsRun,'details':stream.getvalue(),
            'scope':'Synthetic integrated contract checks, not template extraction accuracy or Word rendering'}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'count':report['count']}))
    if not report['passed']: raise SystemExit(1)

if __name__=='__main__': main()

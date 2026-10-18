"""Typed document domain sub-specifications, not a DOCX execution backend.

Schemas apply only to explicitly set structured rules. Unknown requirements use
decision=unresolved; absent requirements must not acquire synthetic defaults.
"""
def obj(properties, required=None):
    return {'type':'object', 'additionalProperties':False,
            'properties':properties, 'required':list(properties) if required is None else required}

def enum(*values): return {'enum':list(values)}
TEXT={'type':'string','minLength':1}
BOOL={'type':'boolean'}
NAMES={'type':'array','items':TEXT,'uniqueItems':True}
POSITIVE={'type':'number','exclusiveMinimum':0}
LINE=obj({'visible':BOOL,'style':enum('single','double','dashed','dotted'),
          'width_pt':POSITIVE,'color':{'type':'string','pattern':'^[0-9A-Fa-f]{6}$'}}, ['visible'])
BOUNDARIES=('top','header_bottom','bottom','left','right','inside_horizontal','inside_vertical')
SCHEMAS={
    'equation.content':obj({'representation':enum('omml','image','plain_text'),
        'editable_required':BOOL,'display_mode':enum('inline','display'),
        'source_notation':enum('latex','mathml','omml','other'),
        'preserve_math_semantics':BOOL}),
    'equation.layout':obj({'formula_alignment':enum('left','center','right'),
        'numbered':BOOL,'number_alignment':enum('left','right',None),
        'number_pattern':{'type':['string','null']},
        'separation':enum('tab_stops','borderless_layout_table','inline','none'),
        'leader':enum('none','dots','dashes'),
        'long_formula_break':enum('operator_at_next_line_start','preserve_source','review'),
        'keep_number_with_formula':BOOL}),
    'equation.numbering':obj({'scope':enum('chapter','document','custom'),
        'counter_id':TEXT,'start':{'type':'integer','minimum':0},
        'continuous':BOOL,'unique':BOOL,'reset_on_scope_change':BOOL,
        'update_mode':enum('static','word_fields','backend_rebuild')}),
    'equation.navigation':obj({'target_role_id':TEXT,
        'anchor_policy':enum('stable_unique_bookmark'),
        'display':enum('target_number','source_label'),
        'link_required':BOOL,'target_match_required':BOOL,
        'update_mode':enum('static','word_fields','backend_rebuild'),
        'verification':{'type':'array','uniqueItems':True,'minItems':1,
            'items':enum('structural_target','display_matches_number','click_target','after_edit_update')}}),
    'page.source_inheritance':obj({'strategy':enum('copy_template','rebuild_from_source_settings'),
        'source_id':TEXT,'section_locator_ids':dict(NAMES,minItems=1),
        'properties':{'type':'array','uniqueItems':True,'minItems':1,'items':enum(
            'size','orientation','margins','gutter','header_footer_distance','columns','grid')},
        'original_immutable':BOOL,'work_on_copy':BOOL,
        'section_policy':enum('preserve_reviewed','remap_to_content'),
        'header_footer_policy':enum('preserve_reviewed','remap_to_content'),
        'page_number_policy':enum('preserve_reviewed','remap_to_content'),
        'verify_effective_settings':BOOL}),
    'table.borders':obj({'model':enum('three_line','grid','custom'),
        'lines':obj({x:LINE for x in BOUNDARIES}),
        'auxiliary_lines':{'type':'array','items':obj({'after_header_row':{'type':'integer','minimum':1},'line':LINE})}}),
    'table.row_selection':obj({'selector':enum('header','body','first','last','indices'),
        'indices':{'type':'array','items':{'type':'integer','minimum':1},'uniqueItems':True}},['selector']),
    'table.continuation':obj({'mode':enum('forbid_split','repeat_header','caption_each_fragment'),
        'repeat_header':BOOL,'caption_pattern':{'type':['string','null']},
        'caption_alignment':enum('left','center','right',None),
        'split_rows':BOOL}),
    'references.citation_style':obj({'system':enum('numeric','author_year','custom'),
        'placement':enum('superscript','inline','footnote','endnote'),
        'label_pattern':TEXT,'multiple_separator':TEXT,'range_policy':enum('expand','compress','preserve'),
        'ordering':enum('appearance','author_year','source','custom'),
        'link_policy':enum('required','optional','none')}),
    'references.bibliography_style':obj({'ordering':enum('appearance','author_year','source','custom'),
        'unreferenced_policy':enum('allow','reject','review'),
        'missing_field_policy':enum('block','review','omit_if_optional'),
        'types':{'type':'array','minItems':1,'items':obj({'type_id':TEXT,
            'required_fields':NAMES,'optional_fields':NAMES,'field_order':NAMES,
            'type_marker':{'type':['string','null']},'pattern':TEXT})},
        'identifier_policy':obj({'doi':enum('preserve','normalize','omit_if_allowed'),
            'url':enum('preserve','normalize','omit_if_allowed'),
            'access_date':enum('required','if_available','not_required')})}),
    'numbering.consistency':obj({'members':NAMES,'scope':enum('chapter','document','custom'),
        'continuous':BOOL,'unique':BOOL,'reset_on_scope_change':BOOL})
}

def check_structured(name, value, validator_class):
    """Return exact reason codes; validation does not prove source semantics."""
    if name not in SCHEMAS or value.get('type')!='structured': return []
    data=value['data']
    issues=[('domain_schema', f"{name}/{'/'.join(map(str,e.path))}: {e.message}")
            for e in validator_class(SCHEMAS[name]).iter_errors(data)]
    if issues: return issues
    if name=='equation.content':
        if data['editable_required'] and data['representation']!='omml':
            issues.append(('equation_editability','Editable equations require the supported native OMML representation, not image/plain text'))
        if not data['preserve_math_semantics']:
            issues.append(('equation_semantics','Conversion must preserve mathematical meaning'))
    if name=='equation.layout':
        if data['numbered']:
            if not (data['number_pattern'] and '{number}' in data['number_pattern'] and data['number_alignment'] and data['separation']!='none'):
                issues.append(('equation_number_layout','Numbered formula needs a number placeholder, alignment and separation mechanism'))
            if not data['keep_number_with_formula']:
                issues.append(('equation_number_detached','Number must stay with its formula'))
        elif data['number_pattern'] is not None or data['number_alignment'] is not None:
            issues.append(('equation_unnumbered','Unnumbered equation must not define number display/alignment'))
    if name=='equation.navigation':
        checks=set(data['verification'])
        if data['link_required'] and not (data['target_match_required'] and {'structural_target','click_target'}<=checks):
            issues.append(('equation_link_verification','Required link needs exact target matching, structural and click verification'))
        if data['display']=='target_number' and 'display_matches_number' not in checks:
            issues.append(('equation_display_verification','Displayed reference must match the target equation number'))
        if data['update_mode']!='static' and 'after_edit_update' not in checks:
            issues.append(('equation_update_verification','Dynamic update needs an actual after-edit check'))
    if name=='page.source_inheritance':
        if not (data['original_immutable'] and data['work_on_copy'] and data['verify_effective_settings']):
            issues.append(('page_inheritance_safety','Source inheritance requires immutable original, separate copy and effective-setting comparison'))
    if name=='table.borders':
        lines=data['lines']
        for key,line in list(lines.items())+[(f'auxiliary-{i}',x['line']) for i,x in enumerate(data['auxiliary_lines'])]:
            if line['visible'] and not all(k in line for k in ('style','width_pt','color')):
                issues.append(('border_incomplete',key+': visible line needs style, width and color'))
        if data['model']=='three_line':
            if not all(lines[k]['visible'] for k in ('top','header_bottom','bottom')) or any(lines[k]['visible'] for k in ('left','right','inside_horizontal','inside_vertical')):
                issues.append(('three_line_topology','Three-line model conflicts with main border visibility'))
            if any(not x['line']['visible'] for x in data['auxiliary_lines']):
                issues.append(('auxiliary_line','An auxiliary line must be visible'))
    if name=='table.row_selection':
        if (data['selector']=='indices') != bool(data.get('indices')):
            issues.append(('row_selector','Indices must be supplied only for indices selection'))
    if name=='table.continuation':
        if data['mode']=='caption_each_fragment' and not (data['caption_pattern'] and '{number}' in data['caption_pattern'] and data['caption_alignment'] and data['repeat_header']):
            issues.append(('continuation_caption','Continuation needs number placeholder, alignment and repeated header'))
        if data['mode']=='forbid_split' and data['split_rows']:
            issues.append(('continuation_split','Cannot split rows when table splitting is forbidden'))
        if data['mode']=='repeat_header' and not data['repeat_header']:
            issues.append(('continuation_header','repeat_header mode requires repeated header'))
    if name=='references.bibliography_style':
        seen=set()
        for t in data['types']:
            if t['type_id'] in seen: issues.append(('reference_type_duplicate',t['type_id']))
            seen.add(t['type_id'])
            required=set(t['required_fields']); optional=set(t['optional_fields'])
            if required & optional or not required<=set(t['field_order']) or not set(t['field_order'])<=required|optional:
                issues.append(('reference_fields',t['type_id']+': field order and required/optional fields disagree'))
    if name=='numbering.consistency' and len(data['members'])<2:
        issues.append(('numbering_members','Consistency requires at least two object roles'))
    return issues

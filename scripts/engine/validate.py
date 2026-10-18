"""Validate template-neutral contracts; never open or modify their DOCX sources."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from domain_subspecs import check_structured


COLLECTIONS = ("sources", "locators", "evidence", "regions", "roles", "rules", "slots",
               "preservation", "relations", "checks", "conflicts", "issues", "extensions")
LENGTH_UNITS = {"pt", "mm", "cm", "inch", "twip"}


def core_properties():
    result = {}
    def add(names, kind):
        result.update({name: kind for name in names.split()})
    add("font.family.latin font.family.east_asia font.family.complex_script font.color "
        "paragraph.alignment page.orientation layout.break_before figure.alignment "
        "figure.caption_position table.alignment table.caption_position table.cell.vertical_alignment table.cell.text_direction equation.representation equation.number_position "
        "note.placement header.content footer.content field.kind field.update_policy", "text")
    add("font.size page.width page.height page.margin.top page.margin.bottom page.margin.left "
        "page.margin.right page.gutter page.header_distance page.footer_distance figure.width "
        "figure.height paragraph.indent.first_line paragraph.indent.left paragraph.indent.right "
        "paragraph.indent.hanging paragraph.spacing.before paragraph.spacing.after", "quantity")
    add("font.bold font.italic font.superscript paragraph.keep_with_next paragraph.keep_together "
        "paragraph.widow_control paragraph.snap_to_grid paragraph.page_break_before "
        "table.repeat_header table.split_rows", "boolean")
    add("page.columns numbering.start", "integer")
    add("paragraph.line_spacing", "line_spacing")
    add("layout.gap_before layout.gap_after", "gap")
    add("layout.text_gap", "literal_spaces")
    add("paragraph.tabs equation.tab_stops", "tab_stops")
    add("page.grid page.section_transition numbering.scheme numbering.scope numbering.reset "
        "numbering.display header.activation footer.activation table.borders table.cell_margins "
        "table.column_widths table.continuation note.numbering references.citation_style "
        "references.bibliography_style table.row_selection numbering.consistency equation.content "
        "equation.layout equation.numbering equation.navigation page.source_inheritance", "structured")
    return result


def validate(data, schema, validator_class, for_execution=False, capabilities=()):
    problems = []
    def problem(code, where, message):
        problems.append({"code": code, "where": where, "message": message})
    for error in sorted(validator_class(schema).iter_errors(data), key=lambda x: str(list(x.path))):
        problem("schema", "/" + "/".join(map(str, error.path)), error.message)
    if problems:
        return {"valid": False, "execution_ready": False, "issues": problems}

    index = {}
    for collection in COLLECTIONS:
        index[collection] = {}
        for item in data[collection]:
            ident = item["id"]
            if ident in index[collection]:
                problem("duplicate_id", collection, ident)
            index[collection][ident] = item

    def refs(ids, collection, where):
        for ident in ids:
            if ident not in index[collection]:
                problem("dangling_reference", where, f"{collection}: {ident}")
    def target(t, where):
        if not (t["role_id"] or t["region_ids"] or t["locator_ids"]):
            problem("empty_target", where, "No role, region or locator")
        refs([t["role_id"]] if t["role_id"] else [], "roles", where)
        refs(t["region_ids"], "regions", where)
        refs(t["locator_ids"], "locators", where)

    for collection in COLLECTIONS:
        for item in data[collection]:
            where = f"{collection}/{item['id']}"
            for field, ref_collection in (("source_id", "sources"), ("role_id", "roles"),
                                          ("inherits_rule_id", "rules")):
                if item.get(field):
                    refs([item[field]], ref_collection, where)
            for field, ref_collection in (("locator_ids", "locators"), ("evidence_ids", "evidence"),
                    ("check_ids", "checks"), ("allowed_slot_ids", "slots"), ("rule_ids", "rules"),
                    ("resolution_evidence_ids", "evidence"), ("selected_rule_ids", "rules")):
                refs(item.get(field, []), ref_collection, where)
            for field in ("target", "from", "to"):
                if field in item:
                    target(item[field], where + "/" + field)
    refs(data["coverage"]["unclassified_locator_ids"], "locators", "coverage")
    refs(data["coverage"]["evidence_ids"], "evidence", "coverage")

    for loc in data["locators"]:
        part = loc["part"]
        if part and (part.startswith(("/", "\\")) or ".." in part.replace("\\", "/").split("/") or ":" in part):
            problem("unsafe_part", loc["id"], part)
    for e in data["evidence"]:
        if not e["locator_ids"]:
            problem("missing_evidence_locator", e["id"], "Evidence must point to an observed location")
        for ident in e["locator_ids"]:
            loc = index["locators"].get(ident)
            if loc and loc["source_id"] != e["source_id"]:
                problem("evidence_source_mismatch", e["id"], ident)

    def cycles(collection, field):
        for item in data[collection]:
            refs([item[field]] if item[field] else [], collection, item["id"])
            seen = set()
            current = item["id"]
            while current in index[collection]:
                if current in seen:
                    problem("inheritance_cycle", item["id"], collection)
                    break
                seen.add(current)
                current = index[collection][current][field]
                if current is None:
                    break
    cycles("roles", "extends")
    cycles("regions", "parent_id")
    cycles("rules", "inherits_rule_id")

    properties = core_properties()
    for ext in data["extensions"]:
        if ext["property"] in properties:
            problem("duplicate_property", ext["id"], ext["property"])
        properties[ext["property"]] = ext["value_type"]

    for rule in data["rules"]:
        name, decision, value = rule["property"], rule["decision"], rule["value"]
        if name not in properties:
            problem("unregistered_property", rule["id"], name)
        if decision == "set":
            if value is None:
                problem("missing_value", rule["id"], name)
            elif name in properties:
                expected = properties[name]
                if value["type"] != expected and not (expected == "gap" and value["type"] in ("blank_lines", "quantity")):
                    problem("value_type", rule["id"], f"{name} requires {expected}")
        elif value is not None:
            problem("unexpected_value", rule["id"], decision)
        if decision == "inherit":
            parent = index["rules"].get(rule["inherits_rule_id"])
            if not parent:
                problem("missing_inheritance", rule["id"], name)
            elif parent["property"] != name:
                problem("inheritance_property", rule["id"], parent["property"])
        elif rule["inherits_rule_id"] is not None:
            problem("unexpected_inheritance", rule["id"], decision)
        if decision != "unresolved" and not rule["evidence_ids"]:
            problem("missing_evidence", rule["id"], "Resolved rule has no source evidence")
        if value and value["type"] == "quantity":
            unit, amount = value["unit"], value["amount"]
            if name == "font.size" and (unit != "pt" or amount <= 0):
                problem("font_size_unit", rule["id"], "Font size must be positive points")
            elif name.startswith(("page.", "figure.")) and (unit not in LENGTH_UNITS or amount < 0):
                problem("length_unit", rule["id"], name)
            elif name.startswith("paragraph.indent") and unit not in LENGTH_UNITS | {"char", "em"}:
                problem("indent_unit", rule["id"], name)
            if name in ("page.width", "page.height", "figure.width", "figure.height") and amount <= 0:
                problem("nonpositive_dimension", rule["id"], name)
        if value and name == "page.columns" and value["type"] == "integer" and value["value"] < 1:
            problem("column_count", rule["id"], "At least one column is required")
        if value:
            domain_issues = check_structured(name, value, validator_class)
            for code, message in domain_issues:
                problem(code, rule['id'], message)
            if not domain_issues and name=='numbering.consistency' and value['type']=='structured':
                refs(value['data'].get('members',[]), 'roles', rule['id'])
            if not domain_issues and name=='equation.navigation' and value['type']=='structured':
                refs([value['data']['target_role_id']], 'roles', rule['id'])
            if not domain_issues and name=='page.source_inheritance' and value['type']=='structured':
                spec=value['data']
                refs([spec['source_id']], 'sources', rule['id'])
                refs(spec['section_locator_ids'], 'locators', rule['id'])
                if spec['source_id'] in index['sources'] and index['sources'][spec['source_id']]['kind']!='template':
                    problem('page_inheritance_source', rule['id'], 'Page settings must refer to a template source')
                for ident in spec['section_locator_ids']:
                    loc=index['locators'].get(ident)
                    if loc and loc['source_id']!=spec['source_id']:
                        problem('page_inheritance_source', rule['id'], 'Section locator belongs to another source')
        if value and value["type"] == "text":
            choices = {
                "page.orientation": {"portrait", "landscape"},
                "paragraph.alignment": {"left", "right", "center", "justify", "distributed"},
                "figure.alignment": {"left", "right", "center"},
                "table.alignment": {"left", "right", "center"},
                "table.caption_position": {"above", "below"},
                "table.cell.vertical_alignment": {"top", "center", "bottom"},
                "table.cell.text_direction": {"horizontal", "vertical", "vertical_rotated"},
                "figure.caption_position": {"above", "below", "beside"},
                "layout.break_before": {"none", "line", "page", "column", "section_next_page", "section_continuous", "section_even_page", "section_odd_page"},
            }
            if name in choices and value["value"] not in choices[name]:
                problem("property_value", rule["id"], name)
        if value and value["type"] == "blank_lines":
            refs([value["baseline_role_id"]] if value["baseline_role_id"] else [], "roles", rule["id"])
            size = value["baseline_font_size"]
            if size and (size["unit"] != "pt" or size["amount"] <= 0):
                problem("gap_baseline_unit", rule["id"], "Baseline font size must be positive points")

    for slot in data["slots"]:
        if not slot["locator_ids"]:
            problem("missing_slot_locator", slot["id"], "Slot must be located")
        if not slot["evidence_ids"]:
            problem("missing_evidence", slot["id"], "Slot action has no evidence")
        if slot["action"] in ("replace_text", "insert_content") and not slot["binding"]:
            problem("missing_binding", slot["id"], slot["action"])
        if slot["action"] == "replace_text" and slot["edit_scope"] != "text_nodes":
            problem("replacement_scope", slot["id"], "Use a separately approved structural edit")
    for preserved in data["preservation"]:
        if not (preserved["locator_ids"] or preserved["part_paths"]):
            problem("empty_preservation", preserved["id"], "No preserved object")
        if preserved["policy"] == "byte_identical" and preserved["allowed_slot_ids"]:
            problem("preservation_edit_conflict", preserved["id"], "Byte identity cannot allow edits")
        for part in preserved["part_paths"]:
            if part.startswith(("/", "\\")) or ".." in part.replace("\\", "/").split("/") or ":" in part:
                problem("unsafe_part", preserved["id"], part)

    conflicting_pairs = set()
    for c in data["conflicts"]:
        if not set(c["selected_rule_ids"]).issubset(c["rule_ids"]):
            problem("conflict_selection", c["id"], "Selection not among candidates")
        if c["resolved"] and not (c["selected_rule_ids"] and c["rationale"] and c["resolution_evidence_ids"]):
            problem("unsupported_resolution", c["id"], "Resolution needs selection, reason and evidence")
        for a in c["rule_ids"]:
            for b in c["rule_ids"]:
                conflicting_pairs.add(frozenset((a, b)))
    seen_rules = {}
    for rule in data["rules"]:
        if rule["decision"] != "set":
            continue
        key = (json.dumps(rule["target"], sort_keys=True), rule["property"])
        previous = seen_rules.get(key)
        if previous and previous["value"] != rule["value"] and frozenset((previous["id"], rule["id"])) not in conflicting_pairs:
            problem("unreported_conflict", rule["id"], previous["id"])
        seen_rules[key] = rule

    execution_problems = []
    def blocked(where, message):
        execution_problems.append({"code": "execution_blocked", "where": where, "message": message})
    if data["state"] != "approved":
        blocked("state", "Contract is not approved")
    if not any(x["kind"] == "template" for x in data["sources"]):
        blocked("sources", "No immutable template source")
    if not data["coverage"]["inventory_complete"] or data["coverage"]["unclassified_locator_ids"]:
        blocked("coverage", "Incomplete or unclassified inventory")
    if data["coverage"]["render_review"] != "complete" or not data["coverage"]["evidence_ids"]:
        blocked("coverage", "Template page review has not been evidenced")
    if not data["roles"] or not (data["rules"] or data["slots"]) or not data["checks"]:
        blocked("coverage", "No roles, operations or checks")
    caps = set(capabilities)
    for loc in data["locators"]:
        if not loc["guard_sha256"]:
            blocked(loc["id"], "Locator has no guard hash")
        if f"locate:{loc['kind']}" not in caps:
            blocked(loc["id"], "Backend does not declare locator support")
    for collection in ("rules", "slots", "preservation", "relations"):
        for item in data[collection]:
            if not item["evidence_ids"] or not item["check_ids"]:
                blocked(item["id"], "Operation has no evidence or check")
    for rule in data["rules"]:
        if rule["decision"] == "unresolved":
            blocked(rule["id"], "Unresolved rule")
        if rule["decision"] == "set" and rule["value"]:
            value = rule["value"]
            if value["type"] == "blank_lines" and not (value["baseline_font_size"] and value["line_spacing"]):
                blocked(rule["id"], "Blank-line baseline must be materialized before execution")
            if f"set:{rule['property']}" not in caps:
                blocked(rule["id"], "Backend does not declare this property support")
    for slot in data["slots"]:
        if f"slot:{slot['action']}" not in caps:
            blocked(slot["id"], "Backend does not declare slot operation support")
    for p in data["preservation"]:
        if f"preserve:{p['policy']}" not in caps:
            blocked(p["id"], "Backend does not declare preservation support")
    for r in data["relations"]:
        if r["update_policy"] == "unresolved" or f"relation:{r['kind']}:{r['update_policy']}" not in caps:
            blocked(r["id"], "Relation is unresolved or unsupported")
    for check in data["checks"]:
        if check["capability"] not in caps:
            blocked(check["id"], "Backend does not declare check support")
    for ext in data["extensions"]:
        if ext["capability"] not in caps or ext["check_capability"] not in caps:
            blocked(ext["id"], "Extension has no declared execution/check capability")
    for c in data["conflicts"]:
        if not c["resolved"]:
            blocked(c["id"], "Unresolved conflict")
    for issue in data["issues"]:
        if issue["resolved"] and not (issue["resolution"] and issue["evidence_ids"]):
            problem("unsupported_resolution", issue["id"], "Issue resolution lacks evidence")
        elif issue["severity"] == "blocking" and not issue["resolved"]:
            blocked(issue["id"], issue["description"])
    ready = not problems and not execution_problems
    return {"valid": not problems and (not for_execution or ready), "execution_ready": ready,
            "issues": problems + (execution_problems if for_execution else []),
            "execution_blockers": execution_problems,
            "limitations": ["Checks are mechanical; evidence authenticity, source matching, actual backend ability, and document correctness are not certified."]}


def load_validator(deps=None):
    if deps:
        sys.path.insert(0, str(Path(deps).resolve()))
    from jsonschema import Draft202012Validator
    return Draft202012Validator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--for-execution", action="store_true")
    parser.add_argument("--capabilities", type=Path, help="JSON array from a tested backend")
    parser.add_argument("--report", type=Path, help="Save full results to a new file and print a compact summary")
    args = parser.parse_args()
    validator = load_validator(args.deps)
    schema = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))
    validator.check_schema(schema)
    data = json.loads(args.contract.read_text(encoding="utf-8"))
    caps = json.loads(args.capabilities.read_text(encoding="utf-8")) if args.capabilities else []
    if not isinstance(caps, list) or not all(isinstance(x, str) for x in caps):
        parser.error("Capabilities must be a JSON array of strings")
    report = validate(data, schema, validator, args.for_execution, caps)
    if args.report:
        if args.report.exists():
            parser.error("Use a new report path; do not overwrite earlier evidence")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"valid":report["valid"], "execution_ready":report["execution_ready"],
                          "issues":len(report["issues"]), "execution_blockers":len(report.get("execution_blockers",[])),
                          "report":str(args.report.resolve())}, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

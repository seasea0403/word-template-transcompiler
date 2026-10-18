"""Synthetic fixtures test representation only, not real template conversion."""
import argparse
import copy
import json
from pathlib import Path

from validate import load_validator, validate


HERE = Path(__file__).resolve().parent


def fixture():
    data = json.loads((HERE / "blank.json").read_text(encoding="utf-8"))
    data["state"] = "approved"
    # All fixtures and observations below are synthetic, not submission evidence.
    data["sources"] = [{"id": "s", "kind": "template", "path": "synthetic-only.docx", "sha256": "0" * 64}]
    data["locators"] = [{"id": "l", "source_id": "s", "kind": "xml_path", "part": "word/document.xml",
                         "selector": "synthetic-only-location", "expected_matches": 1, "guard_sha256": "1" * 64}]
    data["evidence"] = [{"id": "e", "source_id": "s", "locator_ids": ["l"], "kind": "structural_fact",
                         "observation": "SYNTHETIC fixture only, never actual document evidence", "limitations": ["Synthetic"]}]
    data["roles"] = [{"id": "r", "semantic_role": "novel_body_role", "kind": "paragraph", "level": None,
                      "extends": None, "evidence_ids": ["e"]}]
    target = {"role_id": "r", "region_ids": [], "locator_ids": [], "language_tags": [], "occurrence": "all"}
    data["checks"] = [{"id": "c", "kind": "structural", "target": target, "criteria": "Synthetic size comparison",
                       "capability": "check:font_size", "evidence_ids": ["e"]}]
    data["rules"] = [{"id": "a", "target": target, "property": "font.size", "decision": "set",
                      "value": {"type": "quantity", "amount": 13.7, "unit": "pt"}, "inherits_rule_id": None,
                      "evidence_ids": ["e"], "check_ids": ["c"], "rationale": "Synthetic numeric fixture"}]
    data["coverage"] = {"inventory_complete": True, "unclassified_locator_ids": [],
                        "render_review": "complete", "evidence_ids": ["e"]}
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    validator = load_validator(args.deps)
    schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
    validator.check_schema(schema)
    results = []
    caps = ["locate:xml_path", "set:font.size", "check:font_size"]
    def run(name, data, expected, reason=None, execute=False, capabilities=caps):
        result = validate(data, schema, validator, execute, capabilities)
        passed = result["valid"] is expected and (not reason or any(x["code"] == reason for x in result["issues"]))
        results.append({"name": name, "passed": passed, "expected_reason": reason,
                        "actual_codes": sorted({x["code"] for x in result["issues"]})})
        if not passed:
            raise AssertionError((name, result))

    blank = json.loads((HERE / "blank.json").read_text(encoding="utf-8"))
    run("blank_is_valid_draft", blank, True)
    run("blank_cannot_execute", blank, False, "execution_blocked", True)
    run("synthetic_approved_contract", fixture(), True, execute=True)
    data = fixture(); data["roles"][0]["semantic_role"] = "unseen_role"; data["roles"][0]["level"] = 4
    run("dynamic_role_and_fourth_level", data, True, execute=True)
    data = fixture(); data["rules"][0]["property"] = "page.columns"; data["rules"][0]["value"] = {"type": "integer", "value": 2}
    run("non_thesis_multi_column_setting", data, True)
    data = fixture(); data["rules"][0]["property"] = "page.orientation"; data["rules"][0]["value"] = {"type": "text", "value": "landscape"}
    run("non_training_landscape_setting", data, True)
    data = fixture(); data["rules"].append(copy.deepcopy(data["rules"][0]))
    run("duplicate_id", data, False, "duplicate_id")
    data = fixture(); data["rules"][0]["evidence_ids"] = ["missing"]
    run("missing_reference", data, False, "dangling_reference")
    data = fixture(); data["rules"][0]["evidence_ids"] = []
    run("rule_without_evidence", data, False, "missing_evidence")
    data = fixture(); data["rules"][0]["value"]["unit"] = "char"
    run("font_size_cannot_use_char_units", data, False, "font_size_unit")
    data = fixture(); data["rules"][0]["property"] = "paragraph.indent.first_line"; data["rules"][0]["value"] = {"type": "literal_spaces", "count": 2, "space_kind": "ascii"}
    run("indent_is_not_literal_spaces", data, False, "value_type")
    data = fixture(); data["locators"][0]["part"] = "../outside.xml"
    run("unsafe_package_path", data, False, "unsafe_part")
    data = fixture(); data["roles"][0]["extends"] = "r"
    run("cyclic_role_inheritance", data, False, "inheritance_cycle")
    data = fixture(); data["rules"][0]["decision"] = "inherit"; data["rules"][0]["value"] = None; data["rules"][0]["inherits_rule_id"] = "a"
    run("cyclic_rule_inheritance", data, False, "inheritance_cycle")
    data = fixture(); second = copy.deepcopy(data["rules"][0]); second["id"] = "b"; second["value"]["amount"] = 17.2; data["rules"].append(second)
    run("conflicting_identical_target", data, False, "unreported_conflict")
    data["conflicts"] = [{"id": "f", "rule_ids": ["a", "b"], "reason": "Synthetic contradiction",
                          "resolved": False, "selected_rule_ids": [], "rationale": None, "resolution_evidence_ids": []}]
    run("conflict_can_be_recorded", data, True)
    run("unresolved_conflict_cannot_execute", data, False, "execution_blocked", True)
    data["conflicts"][0].update(resolved=True, selected_rule_ids=["a"], rationale="Synthetic decision", resolution_evidence_ids=[])
    run("resolution_requires_evidence", data, False, "unsupported_resolution")
    data = fixture(); data["rules"][0].update(property="layout.gap_before", value={"type": "blank_lines", "count": 1, "baseline_role_id": None, "baseline_font_size": None, "line_spacing": None})
    run("unknown_gap_is_representable", data, True)
    run("unknown_gap_cannot_execute", data, False, "execution_blocked", True, caps + ["set:layout.gap_before"])
    data = fixture(); data["preservation"] = [{"id": "p", "source_id": "s", "locator_ids": ["l"], "part_paths": [], "policy": "byte_identical", "allowed_slot_ids": ["z"], "evidence_ids": ["e"], "check_ids": ["c"]}]
    data["slots"] = [{"id": "z", "locator_ids": ["l"], "role_id": "r", "binding": "metadata.title", "action": "replace_text", "edit_scope": "text_nodes", "missing_policy": "block", "overflow_policy": "review", "evidence_ids": ["e"], "check_ids": ["c"]}]
    run("preservation_cannot_allow_byte_changes", data, False, "preservation_edit_conflict")
    data = fixture(); data["rules"][0]["property"] = "x.example.unseen_feature"
    run("unknown_property_requires_registration", data, False, "unregistered_property")
    data["extensions"] = [{"id": "x", "property": "x.example.unseen_feature", "value_type": "quantity", "semantics": "Synthetic extension only", "capability": "extension:unseen", "check_capability": "check:unseen"}]
    run("new_extension_is_representable", data, True)
    run("unsupported_extension_cannot_execute", data, False, "execution_blocked", True)
    data = fixture(); data["coverage"]["render_review"] = "not_performed"
    run("no_visual_review_cannot_execute", data, False, "execution_blocked", True)
    data = fixture(); data["rules"][0]["unexpected_school_setting"] = True
    run("unrecognized_fields_are_not_silently_ignored", data, False, "schema")
    data = fixture(); data["rules"][0]["property"] = "page.columns"; data["rules"][0]["value"] = {"type": "integer", "value": 0}
    run("column_count_cannot_be_zero", data, False, "column_count")
    data = fixture(); data["rules"][0]["property"] = "page.width"; data["rules"][0]["value"] = {"type": "quantity", "amount": 0, "unit": "mm"}
    run("page_dimension_cannot_be_zero", data, False, "nonpositive_dimension")
    data = fixture(); data["rules"][0]["property"] = "page.orientation"; data["rules"][0]["value"] = {"type": "text", "value": "unsupported-direction"}
    run("orientation_requires_known_semantics", data, False, "property_value")
    data = fixture(); data["evidence"][0]["locator_ids"] = []
    run("evidence_requires_a_location", data, False, "missing_evidence_locator")
    report = {"passed": all(x["passed"] for x in results), "count": len(results), "cases": results,
              "scope": "Synthetic representation and reason-specific rejection tests only; not document or real-template validation"}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

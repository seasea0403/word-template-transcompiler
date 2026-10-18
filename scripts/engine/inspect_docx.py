"""Read-only DOCX structural survey. No template-specific branches or editing."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
W_P = f"{{{W}}}p"
TEXT_TAGS = {f"{{{W}}}t", f"{{{W}}}delText"}
MARKERS = {f"{{{W}}}tab": "\t", f"{{{W}}}br": "\n", f"{{{W}}}cr": "\n"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def paths(root):
    def visit(node, path):
        yield node, path
        counts = {}
        for child in node:
            counts[child.tag] = counts.get(child.tag, 0) + 1
            yield from visit(child, path + f"/{child.tag}[{counts[child.tag]}]")
    yield from visit(root, f"/{root.tag}[1]")


def own_text(node):
    # A surrounding paragraph may contain a text box with its own paragraphs.
    # Those are separate records, not text belonging to the surrounding paragraph.
    out = []
    def visit(current, first=False):
        if current.tag == W_P and not first:
            return
        if current.tag in TEXT_TAGS:
            out.append(current.text or "")
        elif current.tag in MARKERS:
            out.append(MARKERS[current.tag])
        for child in current:
            visit(child)
    visit(node, True)
    return "".join(out)


def xml_or_none(node):
    return ET.tostring(node, encoding="unicode") if node is not None else None


def survey(path):
    original = path.read_bytes()
    paragraphs, sections, styles, relationships, structures = [], [], [], [], []
    structure_tags = {f"{{{W}}}{name}" for name in (
        "tblPr", "tblGrid", "tcPr", "drawing", "pict", "sdtPr", "bookmarkStart", "bookmarkEnd",
        "fldSimple", "fldChar", "instrText", "hyperlink", "footnoteReference", "endnoteReference")}
    parts = []
    xml_parts = {}
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate package part")
        if sum(info.file_size for info in infos) > 64 * 1024 * 1024:
            raise ValueError("Package exceeds the bounded inspection size")
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in PurePosixPath(name).parts or ":" in name:
                raise ValueError(f"Unsafe package part: {name}")
            content = archive.read(info)
            parts.append({"path": info.filename, "bytes": len(content), "sha256": sha256(content)})
            if name.endswith((".xml", ".rels")):
                xml_parts[name] = ET.fromstring(content)
        for name, root in xml_parts.items():
            if name.endswith(".rels"):
                relationships.extend({"part": name, **x.attrib} for x in root)
            if not name.startswith("word/"):
                continue
            for node, address in paths(root):
                if node.tag == W_P:
                    paragraphs.append({
                        "part": name, "xml_path": address,
                        "guard_sha256": sha256(ET.tostring(node, encoding="utf-8")),
                        "text": own_text(node),
                        "direct_paragraph_properties": xml_or_none(node.find("w:pPr", NS)),
                        "runs": [{"text": own_text(r), "direct_run_properties": xml_or_none(r.find("w:rPr", NS))}
                                 for r in node.findall("w:r", NS)],
                    })
                elif node.tag == f"{{{W}}}sectPr":
                    sections.append({"part": name, "xml_path": address, "xml": xml_or_none(node)})
                elif node.tag == f"{{{W}}}style":
                    styles.append({"part": name, "xml_path": address, "xml": xml_or_none(node)})
                if node.tag in structure_tags:
                    structures.append({"part": name, "xml_path": address,
                                       "guard_sha256": sha256(ET.tostring(node, encoding="utf-8")),
                                       "xml": xml_or_none(node)})
    # Only candidate instruction cues: meaning and scope require interpretation.
    cue = re.compile(r"字体|字号|黑体|宋体|楷体|新罗马|Times New Roman|[初一二三四五六七八九]号|行距|缩进|空[一二三四五六七八九十两0-9]+[行格个]|另起|居中|居左|居右|页码|页眉|页脚|格式|下同|三线表|制表符")
    candidates = [{"part": p["part"], "xml_path": p["xml_path"], "text": p["text"]}
                  for p in paragraphs if cue.search(p["text"])]
    doc_root = xml_parts.get("word/document.xml")
    stats = {"paragraphs": len(paragraphs), "nonempty_paragraphs": sum(bool(p["text"].strip()) for p in paragraphs),
             "sections": len(sections), "styles": len(styles), "package_parts": len(parts),
             "instruction_candidates": len(candidates),
             "tables": len(doc_root.findall(".//w:tbl", NS)) if doc_root is not None else 0,
             "text_boxes": len(doc_root.findall(".//w:txbxContent", NS)) if doc_root is not None else 0,
             "structural_records": len(structures),
             "media_parts": sum(p["path"].startswith("word/media/") for p in parts)}
    if path.read_bytes() != original:
        raise ValueError("Source changed during inspection")
    return {"schema_version": "docx-structural-survey/1", "source": str(path.resolve()),
            "source_sha256": sha256(original), "source_bytes": len(original),
            "source_unchanged": True, "stats": stats, "parts": parts, "paragraphs": paragraphs,
            "sections": sections, "styles": styles, "relationships": relationships, "structures": structures,
            "supporting_xml": {name: xml_or_none(root) for name, root in xml_parts.items()
                               if name in ("word/styles.xml", "word/numbering.xml", "word/settings.xml", "word/fontTable.xml")
                               or name.startswith("word/theme/")},
            "instruction_candidates": candidates,
            "limitations": ["No rendering or visual review performed", "Instruction cues are not classified rules",
                            "Direct formatting is not resolved effective formatting; styles, defaults, themes, numbering and script mapping must be reconciled",
                            "No edits, embedded object execution, external relationship fetches or macros"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--manifest", type=Path)
    inputs.add_argument("--template", type=Path, action="append", help="Inspect new local templates without requiring a Playground dataset")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    verified = []
    manifest_bytes = args.manifest.read_bytes() if args.manifest else None
    if manifest_bytes is not None:
        manifest = json.loads(manifest_bytes)
        for resource in manifest["resources"]:
            relative = resource["staged_path"].replace("\\", "/")
            if relative.startswith("/") or ".." in PurePosixPath(relative).parts or ":" in relative:
                raise ValueError("Unsafe staged input path")
            path = args.manifest.parent / relative
            content = path.read_bytes()
            if len(content) != resource["size"] or sha256(content) != resource["sha256"]:
                raise ValueError(f"Resource integrity mismatch: {relative}")
            verified.append({"path": str(path.resolve()), "sha256": sha256(content), "bytes": len(content),
                             "verification": "matches_dataset_manifest"})
    else:
        for path in args.template:
            if path.suffix.lower() != ".docx":
                raise ValueError("Local template inspection requires DOCX")
            content = path.read_bytes()
            verified.append({"path": str(path.resolve()), "sha256": sha256(content), "bytes": len(content),
                             "verification": "local_snapshot_only_not_upstream_authentication"})
    if args.out_dir.exists():
        raise ValueError("Use a new evidence directory; do not overwrite earlier surveys")
    args.out_dir.mkdir(parents=True)
    reports = []
    for item in verified:
        path = Path(item["path"])
        if path.suffix.lower() != ".docx":
            continue
        report = survey(path)
        # File names are labels only. No layout or classification is selected by them.
        label = path.parent.name
        output = args.out_dir / f"{len(reports) + 1:02d}-{label}-survey.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        reports.append({"input": str(path), "output": str(output.resolve()),
                        "sha256": report["source_sha256"], "stats": report["stats"]})
    summary = {"manifest": str(args.manifest.resolve()) if args.manifest else None,
               "manifest_sha256": sha256(manifest_bytes) if manifest_bytes is not None else None,
               "verified_resources": verified, "templates": reports,
               "inspection": "read-only XML; rendering and semantic extraction not performed"}
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verified_resources": len(verified), "templates": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

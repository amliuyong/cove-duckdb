#!/usr/bin/env python3
"""Validate repository documentation and architecture evidence without dependencies."""

import ast
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
COUNTS = {"markdown": 0, "json": 0, "svg": 0, "python": 0, "links": 0}


def error(message: str) -> None:
    ERRORS.append(message)


def local_link(source: Path, raw: str) -> None:
    value = html.unescape(raw.strip().strip("<>"))
    url = urlsplit(value)
    if url.scheme or url.netloc or not url.path:
        return
    target = (ROOT if url.path.startswith("/") else source.parent) / unquote(url.path.lstrip("/"))
    try:
        target.resolve().relative_to(ROOT)
    except ValueError:
        error(f"{source.relative_to(ROOT)}: link leaves repository: {raw}")
        return
    COUNTS["links"] += 1
    if not target.exists():
        error(f"{source.relative_to(ROOT)}: missing link target: {raw}")


def validate_files() -> None:
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in {".git", "__pycache__", "node_modules"} for part in relative.parts):
            continue
        try:
            if path.suffix == ".md":
                COUNTS["markdown"] += 1
                content = path.read_text(encoding="utf-8")
                for match in re.finditer(r"!?\[[^\]]*\]\(([^)\n]+)\)", content):
                    local_link(path, match.group(1).split(' "', 1)[0])
                for match in re.finditer(r"\b(?:href|src|srcset)=[\"']([^\"']+)[\"']", content):
                    local_link(path, match.group(1))
            elif path.suffix == ".json":
                COUNTS["json"] += 1
                json.loads(path.read_text(encoding="utf-8"))
            elif path.suffix == ".py":
                COUNTS["python"] += 1
                ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
            elif path.suffix == ".svg":
                COUNTS["svg"] += 1
                tree = ET.parse(path)
                if tree.getroot().tag != "{http://www.w3.org/2000/svg}svg":
                    error(f"{relative}: root must be SVG")
                if not tree.getroot().get("viewBox"):
                    error(f"{relative}: missing viewBox")
                if any(node.tag.rsplit("}", 1)[-1] in {"script", "foreignObject", "image"} for node in tree.iter()):
                    error(f"{relative}: SVG must remain native vector content")
        except (OSError, ValueError, SyntaxError, ET.ParseError) as exc:
            error(f"{relative}: {exc}")


def validate_architecture() -> None:
    folder = ROOT / "docs" / "design"
    try:
        delivery = json.loads((folder / "architecture.delivery.json").read_text())
        # The finalize record carries the validation of the delivered specification and artifact.
        record = json.loads((folder / "architecture.validation.json").read_text())
        validation = record["validation"]
        if delivery.get("status") != "current" or record.get("status") != "pass" or set(record["gates"].values()) != {"pass"}:
            error("Architecture delivery and its finalize gates must pass")
        if validation.get("checksPassed") != 9 or validation.get("checkCount") != 9:
            error("Architecture delivery must pass all 9 showcase checks")
        if validation.get("errors") != 0 or validation.get("warnings") != 0:
            error("Architecture delivery contains errors or warnings")
        for key, name in [("specification", "architecture.json"), ("artifact", "architecture.html")]:
            data = (folder / name).read_bytes()
            for receipt in (delivery, record):
                if hashlib.sha256(data).hexdigest() != receipt[key]["sha256"] or len(data) != receipt[key]["bytes"]:
                    error(f"{name}: content differs from delivery receipt")

        browser = json.loads((folder / "architecture.visual-check.json").read_text())
        if not browser.get("ok") or browser.get("status") != "pass":
            error("Architecture browser evidence has not passed")
        if browser["artifact"]["sha256"] != delivery["artifact"]["sha256"]:
            error("Browser evidence belongs to a different architecture artifact")
        measured = {(v["width"], v["height"]) for v in browser["containment"]["viewports"] if v.get("ok")}
        expected = {(1440, 900), (1600, 1000), (1920, 1080), (2048, 1320)}
        if measured != expected:
            error("Architecture browser viewport coverage is incomplete")
        for capture in browser["captures"]["screenshots"]:
            if not (folder / capture["file"]).exists():
                error(f"Missing browser evidence screenshot: {capture['file']}")
        if len(browser["captures"]["screenshots"]) != 4:
            error("Architecture must retain all 4 endpoint theme screenshots")

        spec = json.loads((folder / "architecture.json").read_text())
        nodes = {node["id"]: node for node in spec["components"]}
        if len(nodes) != len(spec["components"]):
            error("Duplicate architecture component IDs")
        for edge in spec["connections"]:
            if edge["from"] not in nodes or edge["to"] not in nodes:
                error(f"Unknown architecture endpoint: {edge['id']}")
        svg = ET.parse(ROOT / "docs" / "assets" / "architecture.svg")
        ids = {node.get("id") for node in svg.iter()}
        if not set(nodes).issubset(ids) or not {edge["id"] for edge in spec["connections"]}.issubset(ids):
            error("Native SVG is missing components or connections from its source")
        svg_text = "".join(svg.getroot().itertext())
        for node in nodes.values():
            if node["label"] not in svg_text or node["sublabel"] not in svg_text:
                error(f"Native SVG text differs from source: {node['id']}")
        for edge in spec["connections"]:
            if edge["label"] not in svg_text:
                error(f"Native SVG label differs from source: {edge['id']}")
        assets = json.loads((folder / "evidence" / "assets.json").read_text())
        for name, receipt in assets["files"].items():
            data = (ROOT / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != receipt["sha256"] or len(data) != receipt["bytes"]:
                error(f"{name}: content differs from visual asset receipt")
    except (OSError, KeyError, ValueError, ET.ParseError) as exc:
        error(f"Architecture evidence: {exc}")


def main() -> int:
    validate_files()
    validate_architecture()
    if ERRORS:
        for message in ERRORS:
            print("ERROR:", message, file=sys.stderr)
        return 1
    print(
        f"PASS: {COUNTS['markdown']} Markdown files, {COUNTS['json']} JSON files, "
        f"{COUNTS['svg']} SVG files, {COUNTS['python']} Python sources, "
        f"{COUNTS['links']} local links, and architecture receipts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

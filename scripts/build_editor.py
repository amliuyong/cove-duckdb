#!/usr/bin/env python3
"""Build only the six source-bound Query Editor and Admin Console files; no AWS acceptance."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {"index.html": "text/html; charset=utf-8",
         "query-editor/app.js": "application/javascript; charset=utf-8",
         "query-editor/app.css": "text/css; charset=utf-8",
         "admin.html": "text/html; charset=utf-8",
         "admin/app.js": "application/javascript; charset=utf-8",
         "admin/app.css": "text/css; charset=utf-8"}
SCRIPTS = ["query-editor/app.js", "admin/app.js"]


def source():
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise RuntimeError("Commit exact source before building a deployable artifact")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_artifact(directory, head):
    manifest = json.loads((directory / "manifest.json").read_text())
    raw = (directory / "editor.zip").read_bytes()
    if (manifest.get("format_version") != 1 or manifest.get("source_commit") != head
            or manifest.get("source_tree") != subprocess.check_output(
                ["git", "rev-parse", head + "^{tree}"], cwd=ROOT, text=True).strip()
            or manifest.get("status") != "PASS_STATIC_ARTIFACT_ONLY"
            or manifest.get("zip_sha256") != sha(raw) or manifest.get("zip_bytes") != len(raw)
            or set(manifest.get("files", {})) != set(FILES)):
        raise RuntimeError("Editor artifact/source binding differs")
    with zipfile.ZipFile(directory / "editor.zip") as archive:
        if sorted(archive.namelist()) != sorted(FILES):
            raise RuntimeError("Editor archive must contain exactly the named static files")
        for name, mime in FILES.items():
            file = ROOT / "infra/web" / name
            content = archive.read(name)
            if (file.is_symlink() or content != file.read_bytes()
                    or manifest["files"][name] != {
                        "sha256": sha(content), "bytes": len(content), "content_type": mime}):
                raise RuntimeError("Editor archive member differs: " + name)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    if directory.exists() or directory == ROOT or ROOT in directory.parents:
        parser.error("use a fresh external artifact directory")
    head = source()
    for script in SCRIPTS:
        subprocess.run(["node", "--check", str(ROOT / "infra/web" / script)], check=True)
    directory.mkdir(parents=True)
    manifest = {"format_version": 1, "status": "PASS_STATIC_ARTIFACT_ONLY", "source_commit": head,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(), "files": {}}
    with zipfile.ZipFile(directory / "editor.zip", "x", compression=zipfile.ZIP_STORED) as archive:
        for name, mime in FILES.items():
            file = ROOT / "infra/web" / name
            if file.is_symlink():
                raise RuntimeError("Static assets must be regular source files")
            raw = file.read_bytes()
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, raw)
            manifest["files"][name] = {"sha256": sha(raw), "bytes": len(raw), "content_type": mime}
    raw = (directory / "editor.zip").read_bytes()
    manifest.update(zip_sha256=sha(raw), zip_bytes=len(raw))
    if source() != head:
        raise RuntimeError("Source changed while building")
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    validate_artifact(directory, head)
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()

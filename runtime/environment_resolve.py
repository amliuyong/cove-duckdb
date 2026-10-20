"""Resolve and acquire target wheels without AWS or private-index credentials."""

import contextlib
import hashlib
import io
import json
import os
import platform
import re
import stat
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pip._internal.cli.main import main as pip_main
from pip._internal.network.session import PipSession
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename


class Rejected(Exception):
    def __init__(self, code, requirements=()):
        super().__init__(code)
        self.requirements = list(requirements)


def check(condition, code="DEPENDENCY_RESOLUTION_FAILED"):
    if not condition:
        raise Rejected(code)


MISSING = re.compile(r"ERROR: (?:No matching distribution found for|"
                     r"Could not find a version that satisfies the requirement) (\S+)")


def unresolved(output, submitted):
    """Submitted requirements pip found no binary wheel for, echoed from the request, never from pip."""
    names = set()
    for line in output.splitlines():
        match = MISSING.match(line.strip())
        if match:
            try:
                names.add(canonicalize_name(Requirement(match.group(1)).name))
            except Exception:
                pass
    return sorted({str(Requirement(content)) for content in submitted
                   if canonicalize_name(Requirement(content).name) in names})


def main():
    root = Path(sys.argv[1])
    request = json.loads((root / "request.json").read_text())
    check(platform.python_version() == request["python_version"]
          and platform.machine() == "aarch64", "DEPENDENCY_PLATFORM_MISMATCH")
    check(not any(os.environ.get(x) for x in [
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    ]), "BUILD_CREDENTIALS_IN_RESOLVER")
    maximum = request["maximum_wheel_bytes"]
    transferred = 0
    original = PipSession.request

    def approved_request(session, method, url, *args, **kwargs):
        nonlocal transferred
        value = urlsplit(url)
        check(value.scheme == "https" and value.hostname in {"pypi.org", "files.pythonhosted.org"}
              and not value.username and not value.password and value.port in {None, 443},
              "DEPENDENCY_SOURCE_NOT_APPROVED")
        kwargs["allow_redirects"] = False
        # Requests eagerly consumes non-streamed index/metadata bodies otherwise.
        kwargs["stream"] = True
        response = original(session, method, url, *args, **kwargs)
        check(not 300 <= response.status_code < 400, "DEPENDENCY_SOURCE_NOT_APPROVED")
        check(int(response.headers.get("content-length", "0")) <= min(maximum, 134217728),
              "DEPENDENCY_WHEEL_QUOTA")
        stream = response.raw.stream
        response_bytes = 0

        def bounded_stream(*arguments, **options):
            nonlocal transferred, response_bytes
            for chunk in stream(*arguments, **options):
                check(transferred + len(chunk) <= maximum
                      and response_bytes + len(chunk) <= min(maximum, 134217728),
                      "DEPENDENCY_WHEEL_QUOTA")
                transferred += len(chunk)
                response_bytes += len(chunk)
                yield chunk

        response.raw.stream = bounded_stream
        return response

    PipSession.request = approved_request
    private = request.get("private_wheels", {})
    requirements = request["requirements"] + request["platform_requirements"]
    roots = []
    constraints = []
    for name, value in private.items():
        filename = value["filename"]
        check(Path(filename).name == filename and filename.endswith(".whl"),
              "PRIVATE_WHEEL_INVALID")
        path = root / "private" / filename
        check(hashlib.sha256(path.read_bytes()).hexdigest() == value["sha256"],
              "PRIVATE_WHEEL_HASH_MISMATCH")
        wheel_name, version, _, tags = parse_wheel_filename(filename)
        check(canonicalize_name(name) == canonicalize_name(wheel_name)
              and str(version) == value["version"] and set(tags).intersection(sys_tags()),
              "DEPENDENCY_PLATFORM_MISMATCH")
        constraints.append(f"{name}=={version}")
    for content in requirements:
        requirement = Requirement(content)
        name = canonicalize_name(requirement.name)
        check(requirement.url is None and requirement.marker is None,
              "DEPENDENCY_SOURCE_NOT_APPROVED")
        if name in private:
            value = private[name]
            check(value["version"] in requirement.specifier, "PRIVATE_WHEEL_VERSION_CONFLICT")
            extras = "[" + ",".join(sorted(requirement.extras)) + "]" if requirement.extras else ""
            roots.append(str(root / "private" / value["filename"]) + extras)
        else:
            roots.append(content)
    (root / "private-constraints.txt").write_text("\n".join(constraints) + "\n")
    report_path = root / "pip-report.json"
    # Suppress raw dependency diagnostics: they can contain metadata-controlled URLs.
    # Only submitted requirements that pip names as unavailable are reported.
    diagnostics = io.StringIO()
    with contextlib.redirect_stdout(diagnostics), contextlib.redirect_stderr(diagnostics):
        status = pip_main([
            "install", "--dry-run", "--ignore-installed", "--no-input", "--disable-pip-version-check",
            "--index-url", "https://pypi.org/simple", "--only-binary=:all:", "--no-cache-dir",
            "--find-links", str(root / "private"), "-c", str(root / "private-constraints.txt"),
            "--report", str(report_path), *roots])
    missing = unresolved(diagnostics.getvalue(), request["requirements"]) if status else []
    if missing:
        raise Rejected("DEPENDENCY_NOT_FOUND", missing)
    check(status == 0)
    report = json.loads(report_path.read_text())
    installs = report["install"]
    check(0 < len(installs) <= request["maximum_packages"], "DEPENDENCY_PACKAGE_QUOTA")
    packages, downloads = [], []
    for value in installs:
        metadata, download = value["metadata"], value["download_info"]
        name, version = canonicalize_name(metadata["name"]), metadata["version"]
        sha = download["archive_info"]["hashes"]["sha256"]
        url = urlsplit(download["url"])
        if name in private:
            approved = private[name]
            check(url.scheme == "file" and unquote(url.path) ==
                  str(root / "private" / approved["filename"])
                  and sha == approved["sha256"], "PRIVATE_WHEEL_SOURCE_MISMATCH")
            source = approved
        else:
            check(url.scheme == "https" and url.hostname == "files.pythonhosted.org"
                  and not url.username and not url.password, "DEPENDENCY_SOURCE_NOT_APPROVED")
            source = download["url"]
        license_expression = metadata.get("license_expression") or metadata.get("license") or ""
        classifiers = [x for x in metadata.get("classifier", []) if x.startswith("License ::")]
        check(license_expression in request["approved_licenses"]
              or any(x in request["approved_license_classifiers"] for x in classifiers),
              "DEPENDENCY_LICENSE_NOT_APPROVED")
        packages.append({"name": name, "version": version, "wheel_sha256": sha, "source": source,
                         "license": license_expression, "license_classifiers": classifiers,
                         "requires_dist": metadata.get("requires_dist", [])})
        downloads.append(download["url"] + " --hash=sha256:" + sha)
    check(len({x["name"] for x in packages}) == len(packages))
    (root / "download.lock").write_text("\n".join(downloads) + "\n")
    wheels = root / "wheels"
    wheels.mkdir()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        status = pip_main([
            "download", "--no-deps", "--require-hashes", "--only-binary=:all:", "--no-input",
            "--disable-pip-version-check", "--no-cache-dir", "--dest", str(wheels),
            "-r", str(root / "download.lock")])
    check(status == 0)
    expected = {x["name"]: x for x in packages}
    wheel_bytes = 0
    unpacked_bytes = 0
    tags = set(sys_tags())
    for path in wheels.iterdir():
        check(path.is_file() and not path.is_symlink() and path.suffix == ".whl",
              "DEPENDENCY_WHEEL_INVALID")
        name, version, _, wheel_tags = parse_wheel_filename(path.name)
        name = canonicalize_name(name)
        check(name in expected and str(version) == expected[name]["version"]
              and set(wheel_tags).intersection(tags), "DEPENDENCY_PLATFORM_MISMATCH")
        check(hashlib.sha256(path.read_bytes()).hexdigest() == expected[name]["wheel_sha256"],
              "DEPENDENCY_WHEEL_HASH_MISMATCH")
        wheel_bytes += path.stat().st_size
        check(wheel_bytes <= maximum, "DEPENDENCY_WHEEL_QUOTA")
        with zipfile.ZipFile(path) as archive:
            unpacked_bytes += sum(entry.file_size for entry in archive.infolist())
            check(unpacked_bytes <= request["maximum_image_bytes"], "DEPENDENCY_WHEEL_QUOTA")
            check(not any(stat.S_ISLNK(entry.external_attr >> 16) for entry in archive.infolist()),
                  "DEPENDENCY_WHEEL_INVALID")
            check(not any(Path(x).is_absolute() or ".." in Path(x).parts or "\\" in x
                          for x in archive.namelist()), "DEPENDENCY_WHEEL_INVALID")
            top = [x for x in archive.namelist() if x.endswith(".dist-info/top_level.txt")]
            modules = archive.read(top[0]).decode().splitlines() if len(top) == 1 else sorted({
                filename.split("/", 1)[0] for filename in archive.namelist()
                if filename.count("/") == 1 and filename.endswith("/__init__.py")
            } | {
                filename.split(".", 1)[0] for filename in archive.namelist()
                if "/" not in filename and (filename.endswith(".py") or filename.endswith(".so"))
            })
        expected[name]["filename"] = path.name
        modules = [x for x in modules if x.isidentifier()]
        # A wheel can ship optional top-level modules whose imports need extras
        # (duckdb's adbc_driver_duckdb needs adbc_driver_manager). When the
        # distribution's own module exists, that import is the qualification.
        primary = canonicalize_name(name).replace("-", "_")
        expected[name]["import_modules"] = [primary] if primary in modules else modules[:16]
    check(len(list(wheels.iterdir())) == len(packages))
    lock = "".join(f"{x['name']}=={x['version']} --hash=sha256:{x['wheel_sha256']}\n"
                   for x in sorted(packages, key=lambda x: x["name"]))
    (root / "requirements.lock").write_text(lock)
    # Platform hashes remain mandatory even though the resolver also handles user ranges.
    for name, expected_sha in request["platform_hashes"].items():
        check(expected[name]["wheel_sha256"] == expected_sha, "PLATFORM_DEPENDENCY_HASH_MISMATCH")
    for name, approved in private.items():
        if name in expected:
            expected[name]["import_modules"] = [approved["import_name"]]
    result = {"status": "RESOLVED", "python_version": platform.python_version(), "python_abi": "cp312",
              "platform": "linux_arm64", "pip_version": report["pip_version"],
              "packages": packages, "wheel_bytes": wheel_bytes,
              "unpacked_wheel_bytes": unpacked_bytes,
              "dependency_lock_sha256": hashlib.sha256(lock.encode()).hexdigest()}
    (root / "resolution.json").write_text(json.dumps(result, sort_keys=True))
    print(json.dumps({"status": "RESOLVED", "packages": len(packages), "wheel_bytes": wheel_bytes}))


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        # A safe terminal, never pip's untrusted text, URLs or credentials; at most the
        # submitted requirements pip could not find.
        failure = {"status": "FAILED", "code": str(error) if isinstance(error, Rejected)
                   else "DEPENDENCY_RESOLUTION_FAILED"}
        if isinstance(error, Rejected) and error.requirements:
            failure["requirements"] = error.requirements
        print(json.dumps(failure))
        sys.exit(1)

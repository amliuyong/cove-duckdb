# Third-party source and license records

Colvenna Isle's original source code, documentation, contracts and brand assets are distributed under [Apache-2.0](LICENSE). Third-party components keep their own licenses, recorded below. Release artifacts also carry the license and notice files shipped inside each bundled Python distribution (`*.dist-info`).

## Archify

The standalone architecture viewer includes generated runtime code from [Archify](https://github.com/tt-a1i/archify), under MIT. Copyright (c) 2026 tt-a1i (Archify), and Copyright (c) 2025 Cocoon AI. The full notice remains in [third_party/archify.LICENSE](third_party/archify.LICENSE). Apache-2.0 does not replace that license for those portions.

## Promotional video source

The editable [promotion scenes](docs/assets/promo-source/README.md) bundle GSAP 3.13.0 for deterministic offline rendering. Copyright 2025 GreenSock. All rights reserved. Its [standard license](https://gsap.com/standard-license) and original header remain applicable; it is not relicensed as Apache-2.0. The adapted Colvenna SVG generator follows the Apache-2.0 [series generator](https://github.com/amliuyong/colvenna-for-clickhouse/blob/main/assets/brand/generate.py).

## Native storage qualification

| Component | Fixed source | License record |
| --- | --- | --- |
| DuckDB 1.5.6 | `069cc9f9b5be802405797faecc284961b07c70ef` | [MIT and vendored notices](https://github.com/duckdb/duckdb/tree/069cc9f9b5be802405797faecc284961b07c70ef) |
| duckdb-object-storage | `f096ca13244cb586e04ce04417cadfdd5d18cc0c` | [MIT](https://github.com/dentiny/duckdb-object-storage/blob/f096ca13244cb586e04ce04417cadfdd5d18cc0c/LICENSE) |
| extension-ci-tools (build tooling) | `3fd6109fc01555673b7c7123eba8d0d143fe8ce4` | No top-level license file at the fixed checkout; UNKNOWN pending upstream clarification; not packaged as a runtime component |
| httpfs | build `4bc690d`, v1.5.6 ARM64 binary hash in runtime lock | [MIT and vendored notices](https://github.com/duckdb/duckdb-httpfs/blob/4bc690d/LICENSE) |
| aws extension | build `28c853c`, v1.5.6 ARM64 binary hash in runtime lock | [MIT and AWS SDK dependencies](https://github.com/duckdb/duckdb-aws/blob/28c853c/LICENSE) |
| SlateDB / storage Rust dependencies | versions and Cargo.lock hash in runtime lock | [fixed source Cargo.lock](https://github.com/dentiny/duckdb-object-storage/blob/f096ca13244cb586e04ce04417cadfdd5d18cc0c/rust/Cargo.lock) |
| Python base image | Python 3.12.14 slim-trixie, digest in runtime lock | [Python license](https://docs.python.org/3.12/license.html) and [Debian licenses](https://www.debian.org/legal/licenses/) |

Binary hashes, ABI and source identities are in [runtime/storage-lock.json](runtime/storage-lock.json). The base image and native upstream license files must accompany redistribution as applicable.

## Python distributions in the 1.1.0 release artifacts

The control ZIP (control, intake, sync and pipeline Lambda code), the writer image and the query image install these locked distributions. The table lists each distribution's declared license metadata; its own license/notice files ship inside the artifact.

| Distribution | Version | Declared license | In |
| --- | --- | --- | --- |
| boto3 | 1.42.89 | Apache-2.0 | control, writer, query |
| botocore | 1.42.89 | Apache-2.0 | control, writer, query |
| s3transfer | 0.16.0 | Apache-2.0 | control, writer, query |
| jmespath | 1.0.1 | MIT | control, writer, query |
| python-dateutil | 2.9.0.post0 | BSD / Apache-2.0 | control, writer, query |
| urllib3 | 2.0.7 | MIT | control, writer, query |
| six | 1.17.0 | MIT | control, writer, query |
| jsonschema | 4.25.1 | MIT | control, writer, query |
| jsonschema-specifications | 2025.9.1 | MIT | control, writer, query |
| referencing | 0.37.0 | MIT | control, writer, query |
| rpds-py | 2026.9.1 | MIT | control, writer, query |
| attrs | 26.1.0 | MIT | control, writer, query |
| typing_extensions | 4.16.0 | PSF-2.0 | control, writer, query |
| pytz | 2026.5 | MIT | control, writer, query |
| PyYAML | 6.0.1 | MIT | control, writer, query |
| duckdb | 1.5.6 | MIT | writer, query |
| pyarrow | 24.0.0 | Apache-2.0 | writer, query |
| pip | 25.0.1 | MIT | writer, query (base image tooling) |

Runtime environments are built from the dependencies a space declares (for example duckdb, numpy, pandas and pyarrow); those distributions keep their own licenses and are not part of the release artifact.

## Not yet audited

A transitive SBOM and legal review of the native Rust dependencies (SlateDB and the object-storage extension's Cargo.lock) and of the Debian base image packages has not run (NOT_RUN). This record does not claim that audit.

Referenced technologies and trademarks belong to their respective owners. A link alone does not mean software is bundled. The Colvenna mark is an independent series asset; provenance and usage rules are in [brand assets](docs/assets/README.md).

DuckDB is a trademark of the DuckDB Foundation. Colvenna Isle is independent of the DuckDB Foundation and is not endorsed by it.

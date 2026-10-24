# Architecture validation

Date: 2026-10-24. Scope: documentation artifacts and their presentation. The 2026-10-24 refresh changes branding only; topology and product behavior remain unchanged.

The current diagram includes the S3/CloudFront Query Editor and its authenticated `/v1/*` proxy to API Gateway without API caching. It shows the VPC synchronous Lambda on private port 8082 and the receipt-conditioned query path through the private Writer Control Lambda. The writer copies approved Native values; user SQL executes on the query process's sealed local snapshot. Lambda-mediated DynamoDB access, FIFO polling and the VPC Link/internal ALB/query Service remain distinct. The control group now includes trusted CodeBuild environment builds and immutable ECR images; numeric Lambda/ECS bindings retain separate identities. Planned Lambda Invoke / ECS RunTask executors retain fixed SQL/Python inputs and staged outputs. Native DuckDB/SlateDB storage and Parquet compute files remain separate.

## Native SVG

The primary README diagram is [../assets/architecture.svg](../assets/architecture.svg), drawn as editable vector shapes, paths, and text. It contains no embedded raster image and requires no JavaScript.

Regenerate the original SVG and brand assets:

```bash
python3 scripts/render_architecture.py
python3 scripts/render_brand.py
```

The SVG uses the same [architecture specification](architecture.json) as the supplementary interactive viewer, with explicitly authored orthogonal routes. The checker verifies its component IDs, relationship IDs, and semantic labels against the source.

Native SVG XML validation passed. Chromium rendered the complete SVG at 1440×1100; the retained image was inspected for fit. This screenshot does not claim a separate DOM overflow measurement. An image-capable review checked its text, labels, routes, node fit, and conclusion cards. The logo's light/dark variants were reviewed together at 960×670 (including 96/64/32/24px marks).

Evidence: [SVG render](evidence/architecture-svg.png), [logo render](evidence/logos.png), and [asset receipt](evidence/assets.json).

SVG SHA-256:

```text
6df88f093f9dbbe86121a51468c8a5f5ab86b8f68671ba6209dece92c0767d46
```

## Supplementary interactive viewer

The standalone [architecture.html](architecture.html) was generated using Archify 3.2.0.

```text
diagram_type: architecture
validation: 9/9 showcase, 0 errors, 0 warnings
browser_evidence: passed
visual_review: passed
correction_rounds: 0 (perceptual review; structural authoring diagnostics retained separately)
```

The deterministic [delivery receipt](architecture.delivery.json) binds the specification and HTML bytes; the [finalize record](architecture.validation.json) keeps its validation and gate results. The automated [browser receipt](architecture.visual-check.json) measures the exact delivered artifact at:

| Viewport | Light-theme containment | Readability |
| --- | --- | --- |
| 1440×900 | PASS | PASS |
| 1600×1000 | PASS | PASS |
| 1920×1080 | PASS | PASS |
| 2048×1320 | PASS | PASS |

Light/dark screenshots at the smallest and largest viewports are retained in the [browser contact sheet](architecture.visual-check.html). Current 1440×900 light and 2048×1320 dark images were also reviewed for perceptual fit. The automated receipt records its own `visualReview: pending`; the separate image review above does not rewrite that receipt.

Specification SHA-256:

```text
2a7ae527b6c92f2edda41e9d84330cbd1f2b7f7a1506cb70359bc0d3910a0b51
```

HTML SHA-256:

```text
6b6099bbed458b6995b5652138aea77c54b7bbe736dc6f907db8dc5e05c9c55a
```

## Scope of the evidence

These checks validate documents, diagrams, and presentation. They do not run the product API, DuckDB storage extension, ECS writer, SQS delivery, SQL query service, authentication service, or AWS recovery scenarios.

This diagram does not establish AWS acceptance; product acceptance is defined by the [UAT test cases](../uat/test-cases.md).

DuckDB is a trademark of the DuckDB Foundation. Colvenna Isle is independent of the DuckDB Foundation and is not endorsed by it.

#!/usr/bin/env python3
"""Draw the editable README architecture SVG from its authored JSON source."""

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "design" / "architecture.json"
OUTPUT = ROOT / "docs" / "assets" / "architecture.svg"

# Authored orthogonal routes; changing layout requires updating these routes.
# Each entry contains points and the position of its semantic label.
ROUTES = {
    "client-api": ([(240, 88), (350, 88)], (295, 69)),
    "write-api": ([(550, 88), (630, 88)], (592, 69)),
    "enqueue-batches": ([(840, 88), (980, 88)], (912, 69)),
    "control-access": ([(450, 136), (450, 210)], (450, 174)),
    "control-ddb": ([(350, 266), (260, 266)], (305, 247)),
    "consume-batches": ([(1090, 136), (1090, 210)], (1090, 172)),
    "schedule-compute": ([(550, 266), (579, 266), (579, 696), (630, 696)], (579, 610)),
    "commit-warehouse": (
        [(1090, 322), (1090, 430)],
        (1090, 377),
    ),
    "query-routing": (
        [(450, 40), (450, 16), (16, 16), (16, 376), (450, 376), (450, 430)],
        (235, 359),
    ),
    "read-warehouse": (
        [(450, 542), (450, 800), (1090, 800), (1090, 542)],
        (765, 784),
    ),
    "stage-compute": ([(740, 640), (740, 542)], (740, 590)),
    "load-staged": (
        [(850, 486), (916, 486), (916, 284), (980, 284)],
        (916, 380),
    ),
    "sync-api": ([(550, 105), (605, 105), (605, 266), (630, 266)], (605, 185)),
    "sync-writer": ([(850, 266), (900, 266), (900, 248), (980, 248)], (916, 230)),
    "receipt-read": (
        [(550, 486), (573, 486), (573, 770), (956, 770), (956, 266), (980, 266)],
        (640, 768),
    ),
}

PALETTE = {
    "frontend": ("#f0fdfa", "#0f766e"),
    "external": ("#f1f5f9", "#64748b"),
    "cloud": ("#fffbeb", "#d97706"),
    "backend": ("#ecfdf5", "#059669"),
    "database": ("#f5f3ff", "#7c3aed"),
    "messagebus": ("#fff7ed", "#ea580c"),
}
LINE_COLORS = {
    "default": "#718799",
    "emphasis": "#059669",
    "dashed": "#7c3aed",
    "security": "#d97706",
}


def escape(value: str) -> str:
    return html.escape(value, quote=True)


def text(x: float, y: float, value: str, size: int = 13, **attrs: str) -> str:
    properties = " ".join(f'{key.replace("_", "-")}="{escape(val)}"' for key, val in attrs.items())
    return f'<text x="{x}" y="{y}" font-size="{size}" {properties}>{escape(value)}</text>'


def render() -> None:
    spec = json.loads(SOURCE.read_text(encoding="utf-8"))
    edges = spec["connections"]
    if set(ROUTES) != {edge["id"] for edge in edges}:
        raise ValueError("Architecture routes and source connections differ")

    pieces = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1240 1060" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(spec["meta"]["title"])}</title>',
        "<desc id=\"desc\">The S3/CloudFront Query Editor retains its key in page memory and "
        "forwards authenticated API requests to API Gateway without caching API responses. "
        "API Gateway and intake Lambda buffer writes through SQS FIFO. "
        "Authorizer and management Lambda functions access the DynamoDB control table through the AWS SDK. "
        "Query HTTP requests traverse VPC Link and an internal ALB to an ECS query Service. "
        "A separate ECS writer Service consumes SQS without an ALB and persists native DuckDB data in S3. "
        "An independent VPC synchronous Lambda uses private port 8082 and waits for the approved writer's native receipt. "
        "Receipt-conditioned queries invoke the private Writer Control Lambda for a bounded Native copy; "
        "user SQL runs only on the query process's sealed snapshot. "
        "A scheduling Lambda invokes versioned Lambda functions or starts independent ECS RunTask compute; "
        "their Parquet results are published through the writer. "
        "DuckDB is a trademark of the DuckDB Foundation. Colvenna Isle is independent of "
        "the DuckDB Foundation and is not endorsed by it.</desc>",
        "<defs>",
    ]
    for variant, color in LINE_COLORS.items():
        pieces.append(
            f'<marker id="arrow-{variant}" markerWidth="9" markerHeight="9" '
            f'refX="8" refY="4.5" orient="auto"><path d="M0 0L9 4.5L0 9z" fill="{color}"/></marker>'
        )
    pieces.extend(
        [
            "</defs>",
            '<rect width="1240" height="1060" rx="18" fill="#ffffff"/>',
            '<g font-family="Noto Sans SC, Microsoft YaHei, Arial, sans-serif" fill="#173641">',
            text(40, 24, spec["meta"]["title"], 18, font_weight="700"),
            '<g transform="translate(0 36)">',
            '<g id="connections" fill="none" stroke-linecap="round" stroke-linejoin="round">',
        ]
    )
    for edge in edges:
        points, _ = ROUTES[edge["id"]]
        variant = edge.get("variant", "default")
        color = LINE_COLORS[variant]
        path = "M" + " L".join(f"{x} {y}" for x, y in points)
        dash = ' stroke-dasharray="6 5"' if variant == "dashed" else ""
        pieces.append(
            f'<path id="{edge["id"]}" d="{path}" stroke="{color}" stroke-width="2"'
            f'{dash} marker-end="url(#arrow-{variant})"/>'
        )
    pieces.append('</g><g id="components">')
    for node in spec["components"]:
        x, y = node["pos"]
        width, height = node["size"]
        fill, stroke = PALETTE[node["type"]]
        pieces.extend(
            [
                f'<g id="{node["id"]}">',
                f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1.7"/>',
                text(x + 12, y + 19, node["type"].upper(), 9, fill=stroke, letter_spacing="1"),
                text(x + width / 2, y + 46, node["label"], 15, text_anchor="middle", font_weight="700"),
                text(x + width / 2, y + 66, node["sublabel"], 11, text_anchor="middle", fill="#526a74"),
            ]
        )
        if node.get("tag"):
            pieces.append(text(x + width / 2, y + 88, node["tag"], 10, text_anchor="middle", fill=stroke))
        pieces.append("</g>")

    pieces.append('</g><g id="relationship-labels">')
    for edge in edges:
        x, y = ROUTES[edge["id"]][1]
        label = edge["label"]
        estimated_width = sum(12 if ord(char) > 127 else 7 for char in label) + 12
        pieces.append(
            f'<rect x="{x - estimated_width / 2}" y="{y - 13}" width="{estimated_width}" '
            'height="19" rx="4" fill="#ffffff"/>'
        )
        pieces.append(text(x, y, label, 12, text_anchor="middle", fill=LINE_COLORS[edge.get("variant", "default")]))
    pieces.append("</g>")

    for index, card in enumerate(spec["cards"]):
        x = 40 + index * 400
        pieces.append(f'<rect x="{x}" y="860" width="360" height="135" rx="12" fill="#f8fafc" stroke="#dbe5e9"/>')
        pieces.append(text(x + 18, 888, card["title"], 15, font_weight="700"))
        for item_index, item in enumerate(card["items"]):
            pieces.append(text(x + 18, 915 + item_index * 23, "• " + item, 12, fill="#526a74"))
    pieces.extend(["</g></g>", "</svg>", ""])
    OUTPUT.write_text("\n".join(pieces), encoding="utf-8")
    print(f"Rendered {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    render()

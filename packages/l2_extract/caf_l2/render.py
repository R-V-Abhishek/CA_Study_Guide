"""Debug render generation: colour-coded HTML of blocks, units, and validation flags."""

import html
from pathlib import Path
from caf_l2.blocks import LineBlock
from caf_l2.pairing import flatten_units
from caf_l2.segmenter import ParsedUnit
from caf_l2.validators import ValidationResult

PALETTE = [
    "#e8f0fe", "#fce8e6", "#e6f4ea", "#fef7e0",
    "#f3e8fd", "#e0f2f1", "#fff0f5", "#f1f8e9",
]


def render_debug_html(
    doc_sha256: str,
    lines: list[LineBlock],
    units: list[ParsedUnit],
    validation: ValidationResult,
    output_dir: Path,
) -> Path:
    """Generate interactive debug HTML showing line blocks colored by unit assignment."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{doc_sha256}.html"

    all_units = flatten_units(units)
    # Map block_id to unit
    block_unit_map: dict[str, ParsedUnit] = {}
    unit_colors: dict[str, str] = {}
    for idx, u in enumerate(all_units):
        unit_colors[u.label_path] = PALETTE[idx % len(PALETTE)]
        for lb in u.line_blocks:
            block_unit_map[lb.block_id] = u

    # Build issues list HTML
    issues_html = ""
    for iss in validation.issues:
        sev_color = "#d93025" if iss.severity == "error" else "#f29900"
        issues_html += f"""
        <li style="margin-bottom: 4px;">
            <strong style="color: {sev_color};">[{iss.code}]</strong> 
            {html.escape(iss.message)}
        </li>
        """

    # Build line rows HTML
    rows_html = ""
    for lb in lines:
        u = block_unit_map.get(lb.block_id)
        bg = unit_colors.get(u.label_path, "#ffffff") if u else "#f8f9fa"
        u_label = u.label_path if u else "—"
        marks_badge = f'<span style="background: #1a73e8; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{u.marks}M</span>' if (u and u.marks is not None and u.block_start == lb.block_id) else ""
        flags_badge = ""
        if u and u.validation_flags and u.block_start == lb.block_id:
            flags_badge = "".join(f'<span style="background: #ea8600; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 4px;">{f}</span>' for f in u.validation_flags)

        bold_style = "font-weight: bold;" if lb.bold else ""

        rows_html += f"""
        <tr style="background-color: {bg}; border-bottom: 1px solid #e0e0e0;">
            <td style="padding: 4px 8px; font-family: monospace; font-size: 11px; color: #5f6368; width: 80px;">{lb.block_id}</td>
            <td style="padding: 4px 8px; font-family: monospace; font-size: 11px; width: 90px; font-weight: 500;">{u_label}</td>
            <td style="padding: 4px 8px; {bold_style}">{html.escape(lb.text)}</td>
            <td style="padding: 4px 8px; width: 140px; text-align: right;">{marks_badge} {flags_badge}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Debug Extraction — {doc_sha256[:12]}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 20px; background: #fafafa; color: #202124; }}
        .header {{ background: white; padding: 16px 24px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
        .badge-ok {{ background: #ceead6; color: #137333; }}
        .badge-ok_with_warnings {{ background: #feefc3; color: #b06000; }}
        .badge-needs_review {{ background: #fad2cf; color: #c5221f; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th {{ background: #f1f3f4; padding: 8px; text-align: left; font-size: 12px; color: #5f6368; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>Document Extraction Debug Render</h2>
        <p><strong>SHA256:</strong> <code>{doc_sha256}</code></p>
        <p><strong>Outcome:</strong> <span class="badge badge-{validation.outcome}">{validation.outcome.upper()}</span></p>
        <p><strong>Total Units:</strong> {len(all_units)} | <strong>Total Lines:</strong> {len(lines)}</p>
        {f'<div><h4>Validation Issues:</h4><ul>{issues_html}</ul></div>' if validation.issues else '<p style="color: #137333;">✓ All validations passed cleanly.</p>'}
    </div>

    <table>
        <thead>
            <tr>
                <th>Block ID</th>
                <th>Unit</th>
                <th>Line Text</th>
                <th>Details</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>
"""
    out_file.write_text(html_content, encoding="utf-8")
    return out_file

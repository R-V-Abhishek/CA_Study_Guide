"""Render bounded source pages for independent taxonomy extraction review."""

import json
from pathlib import Path

import pymupdf
import typer


def main(manifest_path: Path = Path("taxonomy/textbook_v1/manifest.json"),
         output_dir: Path = Path("/tmp/phase3-pdf-check")):
    manifest = json.loads(manifest_path.read_text())
    artifacts = {artifact["id"]: artifact for artifact in manifest["textbook_artifacts"]}
    node = next(node for node in manifest["nodes"] if node["paper_id"] == "s2023.P2"
                and node["kind"] == "topic" and "ADJUSTED PRESENT VALUE" in node["name"].upper())
    span = node["source_spans"][0]
    artifact = artifacts[span["artifact_id"]]
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"node_id": node["id"], "heading": node["name"], "artifact_id": artifact["id"],
        "edition": artifact["edition"], "source_span": span, "rendered_pages": []}
    with pymupdf.open(artifact["local_path"]) as pdf:
        for number in sorted({span["pdf_page_start"], span["pdf_page_end"],
                              min(span["pdf_page_end"] + 1, len(pdf))}):
            page = pdf[number - 1]
            path = output_dir / f"afm-apv-page-{number}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(path)
            result["rendered_pages"].append({"pdf_page": number, "image_path": str(path),
                "exercise_heading_present": "TEST YOUR KNOWLEDGE" in " ".join(page.get_text().split()).upper()})
    result["colophon_pages"] = []
    for artifact in manifest["textbook_artifacts"]:
        if artifact["paper_id"] != "s2023.P1" or artifact.get("artifact_role") != "front_matter":
            continue
        with pymupdf.open(artifact["local_path"]) as pdf:
            for page_index in range(min(6, len(pdf))):
                text = pdf[page_index].get_text().casefold()
                if "edition" in text and "reprint" in text:
                    path = output_dir / "fr-colophon.png"
                    pdf[page_index].get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(path)
                    result["colophon_pages"].append({"artifact_id": artifact["id"],
                        "pdf_page": page_index + 1, "image_path": str(path)})
                    break
        if result["colophon_pages"]:
            break
    (output_dir / "inspection.json").write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    typer.run(main)

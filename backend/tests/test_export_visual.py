import shutil
import subprocess
from pathlib import Path

import fitz
import pytest

from api.routes import export


def _fixture_report():
    return {
        "contract_id": "visual-export",
        "filename": "visual.pdf",
        "contract_type": "nda",
        "health": {
            "score": 82,
            "grade": "B",
            "label": "Low Risk",
            "risk_counts": {"high": 0, "medium": 1, "low": 1},
            "total_clauses": 2,
            "scored_clause_count": 2,
            "unknown_count": 0,
            "failed_clause_count": 0,
            "top_level_clause_count": 2,
            "parsed_section_count": 3,
        },
        "clauses": [
            {
                "clause_title": "Confidentiality Definition",
                "risk_level": "low",
                "risk_score": 20,
                "analysis_status": "success",
                "original_text": "Confidential Information means non-public information marked confidential.",
                "plain_english": "This defines what information is protected.",
                "risk_reason": "The definition is clear and limited.",
                "key_concerns": ["None material"],
                "suggested_fix": "Keep the current marking requirement.",
                "risk_rule_applied": "Definitions should be clear.",
                "evidence_summary": "A strong benchmark match supports this assessment.",
                "benchmark_alignment": "strong",
                "predicted_clause_type": "definition",
                "retrieval_quality": "strong",
                "eligible_benchmark_count": 1,
                "citation_suppressed": False,
                "clause_number": "1",
                "subclauses": [
                    {
                        "clause_number": "(a)",
                        "heading": "Public information exclusion",
                        "section_type": "subclause",
                    }
                ],
                "parsed_section_count": 2,
                "cited_benchmark_ids": ["nda_001"],
                "retrieved_benchmarks": [
                    {
                        "benchmark_id": "nda_001",
                        "contract_type": "nda",
                        "clause_type": "definition",
                        "risk_level": "low",
                        "similarity": 0.91,
                        "citation_eligible": True,
                        "relevance_reason": "eligible",
                    }
                ],
            }
        ],
    }


def test_weasyprint_export_renders_nonblank_first_page(tmp_path):
    pytest.importorskip("weasyprint")
    if not shutil.which("pdftoppm"):
        pytest.skip("Poppler pdftoppm is not installed")
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow is not installed")

    html = export._build_html_report(_fixture_report())
    from weasyprint import HTML

    pdf_path = tmp_path / "report.pdf"
    png_prefix = tmp_path / "page"
    pdf_path.write_bytes(HTML(string=html).write_pdf())

    subprocess.run(
        ["pdftoppm", "-png", "-f", "1", "-singlefile", str(pdf_path), str(png_prefix)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    image = Image.open(Path(f"{png_prefix}.png")).convert("RGB")
    pixels = list(image.getdata())
    nonwhite = sum(1 for pixel in pixels if pixel != (255, 255, 255))

    assert nonwhite / len(pixels) > 0.01
    assert b"Contract Risk Analysis Report" in pdf_path.read_bytes() or pdf_path.stat().st_size > 1000


def test_weasyprint_export_contains_selectable_text(tmp_path):
    pytest.importorskip("weasyprint")
    html = export._build_html_report(_fixture_report())
    from weasyprint import HTML

    pdf_path = tmp_path / "selectable-report.pdf"
    pdf_path.write_bytes(HTML(string=html).write_pdf())

    doc = fitz.open(pdf_path)
    try:
        extracted = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

    assert "Contract Risk Analysis Report" in extracted
    assert "visual.pdf" in extracted
    assert "Risk Breakdown" in extracted
    assert "Confidentiality Definition" in extracted
    assert "top-level clause" in extracted
    assert "Nested Sections" in extracted


def test_fallback_export_renders_nonblank_first_page(tmp_path):
    if not shutil.which("pdftoppm"):
        pytest.skip("Poppler pdftoppm is not installed")
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow is not installed")

    lines = export._fallback_build_report_lines(_fixture_report())
    pdf_path = tmp_path / "fallback-report.pdf"
    png_prefix = tmp_path / "fallback-page"
    pdf_path.write_bytes(export._build_pdf(lines))

    subprocess.run(
        ["pdftoppm", "-png", "-f", "1", "-singlefile", str(pdf_path), str(png_prefix)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    image = Image.open(Path(f"{png_prefix}.png")).convert("RGB")
    pixels = list(image.getdata())
    nonwhite = sum(1 for pixel in pixels if pixel != (255, 255, 255))

    assert nonwhite / len(pixels) > 0.01

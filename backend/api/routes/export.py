"""
Export API Route
Download a PDF risk report for completed contract analyses.
"""

import re
import textwrap
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response

from api.routes.analyse import analysis_results
from api.routes.upload import contract_store
from db.queries import get_contract_with_clauses
from db.supabase_client import is_supabase_configured

router = APIRouter()


def _safe_filename(filename: str) -> str:
    base = re.sub(r"\.pdf$", "", filename or "contract", flags=re.IGNORECASE)
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-._")
    return base or "contract"


def _normalize_concerns(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


async def _load_report_data(contract_id: str) -> Optional[Dict[str, Any]]:
    if is_supabase_configured():
        db_contract = await get_contract_with_clauses(contract_id)
        if db_contract:
            return {
                "contract_id": contract_id,
                "filename": db_contract.get("filename", "contract.pdf"),
                "contract_type": db_contract.get("contract_type", "unknown"),
                "status": db_contract.get("status", "unknown"),
                "health": {
                    "score": db_contract.get("health_score", 0),
                    "grade": db_contract.get("health_grade", "N/A"),
                    "label": db_contract.get("health_label", "Unknown"),
                    "risk_counts": {
                        "high": db_contract.get("high_risk_count", 0),
                        "medium": db_contract.get("medium_risk_count", 0),
                        "low": db_contract.get("low_risk_count", 0),
                    },
                    "total_clauses": db_contract.get("total_clauses", 0),
                    "unknown_count": db_contract.get("unknown_risk_count", 0),
                    "failed_clause_count": db_contract.get("failed_clause_count", 0),
                    "scored_clause_count": db_contract.get("scored_clause_count", 0),
                },
                "clauses": db_contract.get("clauses", []),
            }

    record = contract_store.get(contract_id)
    result = analysis_results.get(contract_id)
    if not record:
        return None

    return {
        "contract_id": contract_id,
        "filename": record.get("filename", "contract.pdf"),
        "contract_type": record.get("contract_type", "unknown"),
        "status": "complete" if result else record.get("status", "unknown"),
        "health": result.get("health") if result else None,
        "clauses": result.get("clauses", []) if result else [],
    }


def _plain_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _wrap_block(text: Any, width: int = 92) -> List[str]:
    lines: List[str] = []
    for raw_line in _plain_text(text).splitlines() or [""]:
        if not raw_line.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw_line, width=width) or [""])
    return lines


def _build_report_lines(report: Dict[str, Any]) -> List[str]:
    health = report.get("health") or {}
    risk_counts = health.get("risk_counts") or {}
    clauses = report.get("clauses") or []

    lines = [
        "CONTRACT RISK ANALYSIS REPORT",
        "",
        f"Contract: {_plain_text(report.get('filename'))}",
        f"Type: {_plain_text(report.get('contract_type', 'unknown')).title()}",
        f"Contract ID: {_plain_text(report.get('contract_id'))}",
        "",
        "RISK SUMMARY",
        f"Health Score: {_plain_text(health.get('score', 0))}",
        f"Grade: {_plain_text(health.get('grade', 'N/A'))}",
        f"Overall Label: {_plain_text(health.get('label', 'Unknown'))}",
        f"High Risk Clauses: {_plain_text(risk_counts.get('high', 0))}",
        f"Medium Risk Clauses: {_plain_text(risk_counts.get('medium', 0))}",
        f"Low Risk Clauses: {_plain_text(risk_counts.get('low', 0))}",
        f"Unknown Clauses: {_plain_text(health.get('unknown_count', 0))}",
        f"Failed Analyses: {_plain_text(health.get('failed_clause_count', 0))}",
        f"Scored Clauses: {_plain_text(health.get('scored_clause_count', 0))}",
        f"Total Clauses: {_plain_text(health.get('total_clauses') or len(clauses))}",
        "",
        "CLAUSE ANALYSIS",
        "",
    ]

    for index, clause in enumerate(clauses, 1):
        risk_level = _plain_text(clause.get("risk_level", "medium")).title()
        analysis_status = _plain_text(clause.get("analysis_status", "success")).title()
        concerns = _normalize_concerns(clause.get("key_concerns"))
        lines.extend([
            f"{index}. {_plain_text(clause.get('clause_title') or f'Clause {index}')} [{risk_level}; {analysis_status}]",
            "",
            "Original Text:",
        ])
        lines.extend(_wrap_block(clause.get("original_text", ""), width=92))
        lines.extend(["", "Plain English:"])
        lines.extend(_wrap_block(clause.get("plain_english", "No explanation provided."), width=92))
        lines.extend(["", "Risk Reason:"])
        lines.extend(_wrap_block(clause.get("risk_reason", "No risk reason provided."), width=92))
        lines.extend(["", "Key Concerns:"])
        if concerns:
            for concern in concerns:
                lines.extend(_wrap_block(f"- {concern}", width=92))
        else:
            lines.append("- None listed.")
        lines.extend(["", "Suggested Fix:"])
        lines.extend(_wrap_block(clause.get("suggested_fix", "No suggested fix provided."), width=92))
        benchmarks = clause.get("retrieved_benchmarks") or []
        if benchmarks:
            lines.extend(["", "Retrieved Benchmarks:"])
            for benchmark in benchmarks[:3]:
                lines.extend(_wrap_block(
                    "- "
                    f"{benchmark.get('id', 'benchmark')} | "
                    f"{benchmark.get('contract_type', 'unknown')} | "
                    f"{benchmark.get('clause_type', 'unknown')} | "
                    f"similarity {benchmark.get('similarity', 'n/a')} | "
                    f"{benchmark.get('risk_notes', '')}",
                    width=92,
                ))
        lines.extend(["", "-" * 92, ""])

    return lines


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(lines: List[str]) -> bytes:
    lines_per_page = 54
    pages = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]
    objects: List[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Pages object is filled after page objects are allocated.
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_object_numbers: List[int] = []

    for page_lines in pages:
        stream_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in page_lines:
            stream_lines.append(f"({_pdf_escape(line[:120])}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        contents_obj = len(objects) + 1
        page_obj = len(objects) + 2
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" +
            stream +
            b"\nendstream"
        )
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {contents_obj} 0 R >>".encode("ascii")
        )
        page_object_numbers.append(page_obj)

    kids = " ".join(f"{obj} 0 R" for obj in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("ascii")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_num, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{obj_num} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


@router.get("/export/{contract_id}")
async def export_report(contract_id: str):
    """
    Export a completed contract analysis as a PDF report.
    """
    report = await _load_report_data(contract_id)
    if not report:
        raise HTTPException(status_code=404, detail="Contract not found")

    if report.get("status") != "complete" or not report.get("health"):
        raise HTTPException(status_code=400, detail="Analysis is not complete, cannot export")

    pdf_bytes = _build_pdf(_build_report_lines(report))
    filename = f"risk-report-{_safe_filename(report.get('filename', 'contract'))}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )

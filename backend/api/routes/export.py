"""
Export API Route
Download a polished PDF risk report for completed contract analyses.
Priority 4: Requires authentication and contract ownership.
Priority 5: Uses WeasyPrint for clean typography and structured sections.
Falls back to a text-based PDF builder when WeasyPrint is not installed.
"""

import logging
import re
import html
import textwrap
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response, Depends

from api.routes.analyse import analysis_results
from api.routes.upload import contract_store, _can_persist_user_to_supabase
from api.middleware.auth import require_user, DEV_MODE
from db.queries import get_contract_with_clauses_for_user
from db.supabase_client import is_supabase_configured

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_supabase_persistable_user(user_id: Optional[str]) -> None:
    if is_supabase_configured() and not _can_persist_user_to_supabase(user_id):
        raise HTTPException(
            status_code=401,
            detail="Please sign in before exporting reports.",
        )


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


def _check_contract_ownership(contract_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Check if a contract exists and is owned by the given user.
    Returns the contract record if owned, None otherwise.
    Excludes soft-deleted contracts.
    """
    record = contract_store.get(contract_id)
    if not record:
        return None
    if record.get("deleted_at"):
        return None
    if DEV_MODE and record.get("user_id") is None:
        return record
    if record.get("user_id") == user_id:
        return record
    return None


async def _load_report_data(contract_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Load report data for a contract, verifying ownership.
    """
    if is_supabase_configured():
        try:
            db_contract = await get_contract_with_clauses_for_user(contract_id, user_id)
            if db_contract:
                return {
                    "contract_id": contract_id,
                    "filename": db_contract.get("filename", "contract.pdf"),
                    "contract_type": db_contract.get("contract_type", "unknown"),
                    "selected_contract_type": db_contract.get("selected_contract_type"),
                    "detected_contract_type": db_contract.get("detected_contract_type"),
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
        except Exception:
            if not DEV_MODE:
                raise HTTPException(status_code=503, detail="Database service unavailable")

        if not DEV_MODE:
            return None

    record = _check_contract_ownership(contract_id, user_id)
    result = analysis_results.get(contract_id)
    if not record:
        return None

    return {
        "contract_id": contract_id,
        "filename": record.get("filename", "contract.pdf"),
        "contract_type": record.get("contract_type", "unknown"),
        "selected_contract_type": record.get("selected_contract_type"),
        "detected_contract_type": record.get("detected_contract_type"),
        "status": "complete" if result else record.get("status", "unknown"),
        "health": result.get("health") if result else record.get("health"),
        "clauses": result.get("clauses", []) if result else record.get("analysis", []),
    }


def _html(text: Any) -> str:
    if text is None:
        return ""
    return html.escape(str(text))


def _plain_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


def _generate_recommendations(report: Dict[str, Any]) -> List[str]:
    """
    Generate deterministic recommendations from existing analysis data.
    No LLM calls during export.
    """
    health = report.get("health") or {}
    risk_counts = health.get("risk_counts") or {}
    clauses = report.get("clauses") or []
    recs: List[str] = []

    high = risk_counts.get("high", 0)
    medium = risk_counts.get("medium", 0)
    low = risk_counts.get("low", 0)
    failed = health.get("failed_clause_count", 0)
    unknown = health.get("unknown_count", 0)
    score = health.get("score", 0)

    if high > 0:
        recs.append(f"Prioritize reviewing {high} high-risk clause(s). These represent the greatest exposure.")
    if medium > 0:
        recs.append(f"Review {medium} medium-risk clause(s) for potential renegotiation.")
    if failed > 0:
        recs.append(f"Re-run analysis or manually review {failed} failed clause(s). Failed clauses are excluded from the health score.")
    if unknown > 0:
        recs.append(f"{unknown} clause(s) could not be confidently scored. Consider manual legal review.")
    if low > 0 and high == 0 and medium == 0:
        recs.append("All scored clauses are low risk. The contract appears broadly acceptable, but confirm alignment with your specific requirements.")
    if score < 50:
        recs.append("Overall health score is low. Consider significant revisions or legal counsel before signing.")
    elif score < 75:
        recs.append("Overall health score is moderate. Address highlighted risks before finalizing.")
    else:
        recs.append("Overall health score is good. Continue to monitor high-impact clauses in future versions.")

    # Contract type conflict check
    selected = report.get("selected_contract_type", "")
    detected = report.get("detected_contract_type", "")
    if selected and detected and selected != detected:
        recs.append(f"Contract type mismatch detected (selected: {selected}, detected: {detected}). Verify the analysis used the correct benchmarks.")

    # Top risky clause specific advice
    risky_clauses = [
        c for c in clauses
        if c.get("risk_level") in {"high", "medium"} and c.get("analysis_status") != "failed"
    ]
    risky_clauses.sort(key=lambda c: (c.get("risk_level") == "high", c.get("risk_score") or 0), reverse=True)
    for clause in risky_clauses[:3]:
        title = clause.get("clause_title", "Unnamed clause")
        fix = clause.get("suggested_fix", "")
        if fix:
            recs.append(f"<strong>{_html(title)}</strong>: {_html(fix)}")
        else:
            recs.append(f"<strong>{_html(title)}</strong>: Review this clause carefully.")

    return recs


def _build_html_report(report: Dict[str, Any]) -> str:
    health = report.get("health") or {}
    risk_counts = health.get("risk_counts") or {}
    clauses = report.get("clauses") or []
    filename = report.get("filename", "Contract")
    escaped_filename = _html(filename)
    contract_type = _html(report.get("contract_type", "unknown")).title()
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    score = health.get("score", 0)
    grade = _html(health.get("grade", "N/A"))
    label = _html(health.get("label", "Unknown"))

    high = risk_counts.get("high", 0)
    medium = risk_counts.get("medium", 0)
    low = risk_counts.get("low", 0)
    unknown = health.get("unknown_count", 0)
    failed = health.get("failed_clause_count", 0)
    scored = health.get("scored_clause_count", 0)
    total = health.get("total_clauses") or len(clauses)

    # Determine score color
    if score < 50:
        score_color = "#dc2626"
        score_bg = "#fef2f2"
    elif score < 75:
        score_color = "#ca8a04"
        score_bg = "#fefce8"
    else:
        score_color = "#16a34a"
        score_bg = "#f0fdf4"

    # Recommendations
    recommendations = _generate_recommendations(report)
    recs_html = ""
    if recommendations:
        recs_html = "".join(f"<li>{r}</li>" for r in recommendations)
        recs_html = f"<h2>Recommendations</h2><ul class='recommendations'>{recs_html}</ul>"

    # Risk breakdown
    risk_breakdown = f"""
    <div class="risk-grid">
        <div class="risk-card high">
            <p class="risk-number">{high}</p>
            <p class="risk-label">High Risk</p>
        </div>
        <div class="risk-card medium">
            <p class="risk-number">{medium}</p>
            <p class="risk-label">Medium Risk</p>
        </div>
        <div class="risk-card low">
            <p class="risk-number">{low}</p>
            <p class="risk-label">Low Risk</p>
        </div>
        <div class="risk-card unknown">
            <p class="risk-number">{unknown}</p>
            <p class="risk-label">Unknown</p>
        </div>
        <div class="risk-card failed">
            <p class="risk-number">{failed}</p>
            <p class="risk-label">Failed</p>
        </div>
        <div class="risk-card scored">
            <p class="risk-number">{scored}</p>
            <p class="risk-label">Scored</p>
        </div>
    </div>
    """

    # Top risky clauses
    top_risky_html = ""
    risky_clauses = [
        c for c in clauses
        if c.get("risk_level") in {"high", "medium"} and c.get("analysis_status") != "failed"
    ]
    risky_clauses.sort(
        key=lambda c: (c.get("risk_level") == "high", c.get("risk_score") or 0),
        reverse=True,
    )
    if risky_clauses:
        top_items = "".join(
            f"<li><strong>{_html(c.get('clause_title', 'Unnamed'))}</strong> "
            f"— {_html(c.get('risk_level', '').title())} "
            f"(score: {c.get('risk_score', 'N/A')})</li>"
            for c in risky_clauses[:5]
        )
        top_risky_html = f"<h2>Top Risky Clauses</h2><ol>{top_items}</ol>"

    # Failed / unknown clauses
    failed_clauses = [c for c in clauses if c.get("analysis_status") == "failed"]
    failed_html = ""
    if failed_clauses:
        items = "".join(
            f"<li><strong>{_html(c.get('clause_title', 'Unnamed'))}</strong> "
            f"— {_html(c.get('error_message', 'Analysis failed'))}</li>"
            for c in failed_clauses
        )
        failed_html = f"<h2>Failed Analysis</h2><ul>{items}</ul>"

    # Full clause analysis
    clause_sections = []
    for idx, clause in enumerate(clauses, 1):
        status = clause.get("analysis_status", "success")
        risk = _html(clause.get("risk_level", "unknown").title())
        provider = _html(clause.get("provider_used") or "N/A")
        retries = clause.get("retry_count", 0)
        alignment = _html(clause.get("benchmark_alignment", "none").title())

        header_chips = f"""
        <div class="clause-chips">
            <span class="chip risk-{clause.get('risk_level', 'unknown').lower()}">{risk}</span>
            <span class="chip status-{status}">{_html(status.title())}</span>
            <span class="chip">Provider: {provider}</span>
            <span class="chip">Retries: {retries}</span>
            <span class="chip">RAG: {alignment}</span>
        </div>
        """

        body = f"""
        <div class="clause-body">
            <p class="label">Original Text</p>
            <div class="box mono">{_html(clause.get('original_text', ''))}</div>

            <p class="label">What This Means</p>
            <div class="box">{_html(clause.get('plain_english', 'No explanation provided.'))}</div>

            <p class="label">Risk Reason</p>
            <div class="box alert">{_html(clause.get('risk_reason', 'No risk reason provided.'))}</div>
        """

        concerns = _normalize_concerns(clause.get("key_concerns"))
        if concerns:
            body += "<p class='label'>Key Concerns</p><ul>"
            for concern in concerns:
                body += f"<li>{_html(concern)}</li>"
            body += "</ul>"

        fix = clause.get("suggested_fix")
        if fix:
            body += f"""
            <p class="label">Suggested Fix</p>
            <div class="box fix">{_html(fix)}</div>
            """

        # RAG evidence
        evidence_parts = []
        if clause.get("risk_rule_applied"):
            evidence_parts.append(f"<p><strong>Rule:</strong> {_html(clause['risk_rule_applied'])}</p>")
        if clause.get("evidence_summary"):
            evidence_parts.append(f"<p><strong>Evidence:</strong> {_html(clause['evidence_summary'])}</p>")
        cited = clause.get("cited_benchmark_ids") or []
        if cited:
            evidence_parts.append(f"<p><strong>Cited Benchmarks:</strong> {_html(', '.join(str(i) for i in cited))}</p>")

        benchmarks = clause.get("retrieved_benchmarks") or []
        if benchmarks:
            bench_rows = ""
            for b in benchmarks[:3]:
                bench_id = _html(b.get("id") or b.get("benchmark_id") or "benchmark")
                btype = _html(b.get("contract_type", "unknown"))
                bclause = _html(b.get("clause_type", "unknown"))
                brisk = _html(b.get("risk_level", "unknown"))
                sim = _html(b.get("similarity", "n/a"))
                bench_rows += f"<tr><td>{bench_id}</td><td>{btype}</td><td>{bclause}</td><td>{brisk}</td><td>{sim}</td></tr>"
            evidence_parts.append(f"""
            <p class="label">Retrieved Benchmarks</p>
            <table class="benchmark-table">
                <thead><tr><th>ID</th><th>Type</th><th>Clause</th><th>Risk</th><th>Similarity</th></tr></thead>
                <tbody>{bench_rows}</tbody>
            </table>
            """)

        if evidence_parts:
            body += f"<div class='rag-panel'><p class='label'>RAG Evidence</p>{''.join(evidence_parts)}</div>"

        body += "</div>"

        clause_sections.append(
            f"<div class='clause-section'><h3>{idx}. {_html(clause.get('clause_title', f'Clause {idx}'))}</h3>{header_chips}{body}</div>"
        )

    clauses_html = "".join(clause_sections)

    html_report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Contract Risk Report — {escaped_filename}</title>
<style>
@page {{
    size: A4;
    margin: 60px 50px 70px 50px;
    @bottom-center {{
        content: counter(page);
        font-size: 10px;
        color: #6b7280;
    }}
}}
body {{
    font-family: Helvetica, Arial, sans-serif;
    font-size: 11px;
    line-height: 1.5;
    color: #1f2937;
}}
h1 {{
    font-size: 22px;
    margin-bottom: 6px;
    color: #111827;
}}
h2 {{
    font-size: 14px;
    margin-top: 24px;
    margin-bottom: 10px;
    color: #111827;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 4px;
}}
h3 {{
    font-size: 12px;
    margin-top: 18px;
    margin-bottom: 6px;
    color: #374151;
}}
p {{ margin: 4px 0; }}
.cover {{
    text-align: center;
    padding-top: 80px;
}}
.cover h1 {{ font-size: 26px; margin-bottom: 12px; }}
.cover-meta {{
    color: #6b7280;
    margin-top: 16px;
}}
.score-badge {{
    display: inline-block;
    margin-top: 24px;
    padding: 18px 32px;
    border-radius: 12px;
    background: {score_bg};
    border: 1px solid {score_color}33;
}}
.score-value {{
    font-size: 36px;
    font-weight: 700;
    color: {score_color};
}}
.score-grade {{
    font-size: 18px;
    font-weight: 600;
    color: {score_color};
}}
.score-label {{
    font-size: 12px;
    color: #4b5563;
    margin-top: 4px;
}}
.risk-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 8px;
}}
.risk-card {{
    flex: 1 1 120px;
    border-radius: 8px;
    padding: 10px;
    text-align: center;
    border: 1px solid #e5e7eb;
}}
.risk-card.high {{ background: #fef2f2; border-color: #fecaca; }}
.risk-card.medium {{ background: #fefce8; border-color: #fde047; }}
.risk-card.low {{ background: #f0fdf4; border-color: #bbf7d0; }}
.risk-card.unknown {{ background: #f9fafb; border-color: #e5e7eb; }}
.risk-card.failed {{ background: #fef2f2; border-color: #fecaca; }}
.risk-card.scored {{ background: #eff6ff; border-color: #bfdbfe; }}
.risk-number {{ font-size: 20px; font-weight: 700; margin: 0; }}
.risk-label {{ font-size: 10px; color: #4b5563; margin: 2px 0 0; }}
.recommendations {{ margin-top: 6px; padding-left: 18px; }}
.recommendations li {{ margin-bottom: 6px; }}
.clause-section {{
    margin-top: 20px;
    padding: 14px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    page-break-inside: avoid;
}}
.clause-chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
}}
.chip {{
    font-size: 9px;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid #e5e7eb;
    background: #f9fafb;
    color: #374151;
}}
.chip.risk-high {{ background: #fef2f2; color: #991b1b; border-color: #fecaca; }}
.chip.risk-medium {{ background: #fefce8; color: #854d0e; border-color: #fde047; }}
.chip.risk-low {{ background: #f0fdf4; color: #166534; border-color: #bbf7d0; }}
.chip.risk-unknown {{ background: #f3f4f6; color: #374151; border-color: #d1d5db; }}
.chip.status-failed {{ background: #fef2f2; color: #991b1b; border-color: #fecaca; }}
.clause-body .label {{
    font-size: 10px;
    font-weight: 600;
    color: #6b7280;
    margin-top: 10px;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}
.box {{
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 8px;
}}
.box.mono {{
    font-family: monospace;
    font-size: 10px;
    white-space: pre-wrap;
    word-wrap: break-word;
}}
.box.alert {{ background: #fff7ed; border-color: #fed7aa; }}
.box.fix {{ background: #f0fdf4; border-color: #bbf7d0; }}
.rag-panel {{
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    padding: 10px;
    margin-top: 10px;
}}
.benchmark-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 6px;
    font-size: 10px;
}}
.benchmark-table th, .benchmark-table td {{
    border: 1px solid #e5e7eb;
    padding: 4px 6px;
    text-align: left;
}}
.benchmark-table th {{
    background: #f3f4f6;
    font-weight: 600;
}}
</style>
</head>
<body>

<div class="cover">
    <h1>Contract Risk Analysis Report</h1>
    <p class="cover-meta">{escaped_filename} &bull; {contract_type} &bull; {generated}</p>
    <div class="score-badge">
        <div class="score-value">{score}</div>
        <div class="score-grade">Grade {grade}</div>
        <div class="score-label">{label}</div>
    </div>
</div>

<h2>Risk Breakdown</h2>
{risk_breakdown}

<p style="margin-top:8px; color:#6b7280;">Total clauses: {total} &bull; Scored: {scored}</p>

{recs_html}

{top_risky_html}

{failed_html}

<h2>Full Clause Analysis</h2>
{clauses_html}

</body>
</html>"""

    return html_report


# =============================================================================
# Fallback text-based PDF builder for environments without WeasyPrint
# =============================================================================


def _fallback_build_report_lines(report: Dict[str, Any]) -> List[str]:
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
        lines.extend(_fallback_wrap_block(clause.get("original_text", ""), width=92))
        lines.extend(["", "Plain English:"])
        lines.extend(_fallback_wrap_block(clause.get("plain_english", "No explanation provided."), width=92))
        lines.extend(["", "Risk Reason:"])
        lines.extend(_fallback_wrap_block(clause.get("risk_reason", "No risk reason provided."), width=92))
        if clause.get("risk_rule_applied") or clause.get("evidence_summary") or clause.get("benchmark_alignment"):
            lines.extend(["", "RAG Evidence:"])
            lines.extend(_fallback_wrap_block(
                f"Alignment: {clause.get('benchmark_alignment', 'none')}",
                width=92,
            ))
            if clause.get("risk_rule_applied"):
                lines.extend(_fallback_wrap_block(
                    f"Rule Applied: {clause.get('risk_rule_applied')}",
                    width=92,
                ))
            if clause.get("evidence_summary"):
                lines.extend(_fallback_wrap_block(
                    f"Evidence Summary: {clause.get('evidence_summary')}",
                    width=92,
                ))
            cited_ids = clause.get("cited_benchmark_ids") or []
            if cited_ids:
                lines.extend(_fallback_wrap_block(
                    f"Cited Benchmarks: {', '.join(str(item) for item in cited_ids)}",
                    width=92,
                ))
        lines.extend(["", "Key Concerns:"])
        if concerns:
            for concern in concerns:
                lines.extend(_fallback_wrap_block(f"- {concern}", width=92))
        else:
            lines.append("- None listed.")
        lines.extend(["", "Suggested Fix:"])
        lines.extend(_fallback_wrap_block(clause.get("suggested_fix", "No suggested fix provided."), width=92))
        benchmarks = clause.get("retrieved_benchmarks") or []
        if benchmarks:
            lines.extend(["", "Retrieved Benchmarks:"])
            for benchmark in benchmarks[:3]:
                lines.extend(_fallback_wrap_block(
                    "- "
                    f"{benchmark.get('id', 'benchmark')} | "
                    f"{benchmark.get('contract_type', 'unknown')} | "
                    f"{benchmark.get('clause_type', 'unknown')} | "
                    f"{benchmark.get('risk_level', 'unknown')} | "
                    f"similarity {benchmark.get('similarity', 'n/a')} | "
                    f"{benchmark.get('risk_rule') or benchmark.get('risk_notes', '')}",
                    width=92,
                ))
                if benchmark.get("source_name"):
                    lines.extend(_fallback_wrap_block(
                        f"  Source: {benchmark.get('source_name')} ({benchmark.get('source_type', 'unknown')})",
                        width=92,
                    ))
        lines.extend(["", "-" * 92, ""])

    return lines


def _fallback_wrap_block(text: Any, width: int = 92) -> List[str]:
    lines: List[str] = []
    for raw_line in _plain_text(text).splitlines() or [""]:
        if not raw_line.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw_line, width=width) or [""])
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
async def export_report(
    contract_id: str,
    user: Dict[str, Any] = Depends(require_user),
):
    """
    Export a completed contract analysis as a polished PDF report.
    Requires authentication and ownership of the contract.
    """
    user_id = user.get("id")
    _require_supabase_persistable_user(user_id)
    report = await _load_report_data(contract_id, user_id)
    if not report:
        raise HTTPException(status_code=404, detail="Contract not found")

    if report.get("status") != "complete" or not report.get("health"):
        raise HTTPException(status_code=400, detail="Analysis is not complete, cannot export")

    try:
        from weasyprint import HTML
        html_content = _build_html_report(report)
        pdf_bytes = HTML(string=html_content).write_pdf()
    except ImportError:
        logger.info("WeasyPrint is unavailable, using fallback PDF renderer")
        pdf_bytes = _build_pdf(_fallback_build_report_lines(report))
    except Exception as exc:
        logger.error(f"Failed to generate PDF with WeasyPrint, using fallback renderer: {exc}")
        pdf_bytes = _build_pdf(_fallback_build_report_lines(report))

    filename = f"risk-report-{_safe_filename(report.get('filename', 'contract'))}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )

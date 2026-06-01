"""
Export API Route
Download a styled PDF risk report (placeholder for Week 1).
"""

from fastapi import APIRouter, HTTPException, Response

from api.routes.upload import contract_store

router = APIRouter()


@router.get("/export/{contract_id}")
async def export_report(contract_id: str):
    """
    Export a contract analysis as a PDF report.
    Week 1 placeholder: Returns a simple text report.
    Week 2 will use WeasyPrint for styled PDF generation.
    """
    if contract_id not in contract_store:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    record = contract_store[contract_id]
    
    if record["status"] == "failed":
        raise HTTPException(status_code=400, detail="Analysis failed, cannot export")
    
    # Week 1: Simple text export
    clauses_text = ""
    if record["clauses"]:
        for i, clause in enumerate(record["clauses"], 1):
            clauses_text += f"\n\n{'='*60}\nCLAUSE {i}\n{'='*60}\n{clause[:500]}..."
    
    report_content = f"""
CONTRACT RISK ANALYSIS REPORT
=============================

Contract: {record['filename']}
Contract ID: {contract_id}
Type: {record['contract_type']}
Status: {record['status']}
Total Clauses: {len(record['clauses']) if record['clauses'] else 0}

NOTE: This is a Week 1 placeholder report. 
Full risk analysis with LLM scoring coming in Week 2.

{clauses_text}

=============================
End of Report
=============================
"""
    
    return Response(
        content=report_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename=report_{contract_id[:8]}.txt"
        }
    )

"""Deterministic clause-type classification for benchmark retrieval."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


CLAUSE_TYPE_CONFIDENCE_THRESHOLD = 0.45


CLAUSE_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "employment": {
        "commencement": ["commencement", "start date", "effective date", "begin employment", "joining date"],
        "job_duties": ["duties", "responsibilities", "job description", "position", "role", "perform"],
        "reporting_structure": ["report to", "reports to", "supervisor", "manager", "direction", "supervision"],
        "workplace": ["place of work", "workplace", "remote", "relocate", "location", "office"],
        "work_hours": ["normal hours", "working hours", "overtime", "schedule", "hours of work"],
        "leave": ["annual leave", "vacation", "holiday", "public holiday", "leave entitlement"],
        "sick_leave": ["sick leave", "illness", "medical certificate", "sickness", "medical absence"],
        "company_policies": ["policies", "handbook", "company rules", "code of conduct", "procedures"],
        "probation": ["probation", "probationary", "confirmation", "trial period"],
        "role_changes": ["change duties", "change role", "role changes", "title", "material changes"],
        "compensation": ["salary", "base pay", "remuneration", "wages", "compensation"],
        "bonus": ["bonus", "incentive", "commission", "discretionary payment"],
        "benefits": ["benefits", "insurance", "pension", "retirement", "allowance"],
        "termination_notice": ["termination", "notice period", "resignation", "terminate"],
        "confidentiality": ["confidential", "confidential information", "non-disclosure", "proprietary"],
        "ip_assignment": ["intellectual property", "work product", "inventions", "assign", "copyright"],
        "non_compete": ["non-compete", "compete", "competitor", "restricted business"],
        "expense_reimbursement": ["expenses", "reimburse", "receipts", "business expense"],
        "dispute_resolution": ["dispute", "arbitration", "court", "jurisdiction", "claims"],
        "at_will_employment": ["at-will", "without cause", "any time"],
    },
    "nda": {
        "definitions": ["definitions", "meaning", "defined terms"],
        "definition": ["confidential information means", "definition", "includes", "marked confidential"],
        "term": ["term", "duration", "years", "effective date", "expires"],
        "permitted_use": ["permitted purpose", "use only", "evaluate", "purpose"],
        "disclosure": ["disclose", "disclosure", "share", "release"],
        "return_destroy": ["return", "destroy", "delete", "certify destruction"],
        "residuals": ["residual", "memory", "unaided memory", "retained ideas"],
        "remedies": ["injunction", "equitable relief", "damages", "liquidated"],
        "exceptions": ["already known", "public", "independently developed", "third party"],
        "assignment": ["assign", "assignment", "successor", "transfer"],
        "governing_law": ["governing law", "venue", "jurisdiction", "courts"],
        "ownership": ["ownership", "own", "retains", "title", "property rights"],
        "ip_assignment": ["assign", "assignment", "inventions", "work product", "developed during", "intellectual property"],
        "non_compete": ["non-compete", "compete", "competition", "competitor", "competing business", "direct competition"],
        "non_solicitation": ["non-solicit", "solicit", "hire", "customers", "employees", "divert"],
        "business_opportunity": ["business opportunity", "opportunity", "introduced", "contacts", "pursue", "dealings"],
        "fees_costs": ["legal fees", "attorney fees", "attorneys' fees", "costs", "expenses", "enforcement costs"],
        "notices": ["notice", "notices", "address", "delivery", "deemed received"],
        "waiver": ["waiver", "waive", "failure to enforce", "no waiver"],
        "severability": ["severability", "severable", "unenforceable", "invalid provision"],
        "entire_agreement": ["entire agreement", "supersedes", "prior agreements", "complete agreement"],
        "counterparts": ["counterparts", "electronic signature", "facsimile", "same instrument"],
        "authorized_recipients": ["representatives", "advisors", "affiliates", "need to know", "employees"],
        "compelled_disclosure": ["subpoena", "court order", "required by law", "regulator", "compelled"],
        "no_license": ["no license", "ownership", "intellectual property", "rights granted"],
        "no_warranty": ["no warranty", "accuracy", "completeness", "reliance"],
        "standard_of_care": ["reasonable care", "standard of care", "safeguard", "protect"],
        "data_security": ["security", "technical safeguards", "administrative safeguards", "incident"],
        "oral_disclosure_marking": ["oral", "verbal", "summarized in writing", "identified as confidential"],
        "third_party_disclosure": ["third party", "contractor", "service provider", "downstream"],
        "non_circumvention": ["non-circumvention", "circumvent", "introduced", "contacts"],
        "survival": ["survive", "survival", "after termination", "trade secrets"],
    },
    "vendor": {
        "scope_of_services": ["scope of services", "services provided", "deliverables", "statement of work", "sow"],
        "payment_terms": [
            "payment", "payment due", "invoice", "invoices", "invoice receipt", "fees",
            "withhold", "late fee", "late fees", "late payment", "late payments",
            "late charge", "overdue", "amount still owing", "due within",
        ],
        "acceptance": ["acceptance", "reject", "accept", "criteria", "defect"],
        "service_levels": ["service level", "sla", "uptime", "response time", "credits"],
        "warranty": ["warranty", "warrants", "defect", "conform"],
        "indemnification": [
            "indemnify", "indemnifies", "indemnifies the other", "indemnification", "hold harmless",
            "third-party claims", "claims losses damages liabilities", "legal fees and costs", "defend",
        ],
        "limitation_of_liability": ["limitation of liability", "liability cap", "consequential", "damages"],
        "data_security": ["data security", "security", "personal data", "breach", "safeguards"],
        "termination": ["termination", "terminate", "notice", "for convenience", "for cause"],
        "intellectual_property": ["intellectual property", "ip", "ownership", "work product", "vendor technology"],
        "change_orders": ["change order", "change request", "scope change", "additional fees"],
        "subcontracting": ["subcontract", "subcontractor", "third party", "assign services"],
        "audit_rights": ["audit", "inspect", "records", "books", "facilities"],
        "confidentiality": ["confidential", "confidentiality", "proprietary", "customer information"],
        "insurance": ["insurance", "coverage", "certificate", "policy"],
        "dispute_resolution": ["dispute", "arbitration", "court", "venue", "claims"],
        "force_majeure": ["force majeure", "beyond reasonable control", "disaster", "delay"],
        "compliance_with_laws": ["comply with laws", "compliance", "regulations", "anti-bribery", "privacy laws"],
        "transition_assistance": ["transition", "handover", "migration", "termination assistance"],
        "taxes_expenses": [
            "taxes", "sales tax", "duties", "expenses", "expense", "reimbursement",
            "reimbursed", "out-of-pocket", "travel", "pre-approved", "pre-approval",
            "receipts", "reasonable and necessary expenses",
        ],
    },
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def classify_clause_type(clause_text: str, contract_type: str) -> Dict[str, Any]:
    """Return the most likely clause type from deterministic keyword signals."""
    normalized_type = (contract_type or "").lower()
    keyword_map = CLAUSE_KEYWORDS.get(normalized_type, {})
    text = _normalize(clause_text)
    if not text or not keyword_map:
        return {
            "predicted_clause_type": None,
            "clause_type_confidence": 0.0,
            "clause_type_matched_terms": [],
        }

    scores: List[Tuple[str, int, List[str]]] = []
    for clause_type, keywords in keyword_map.items():
        matched = [term for term in keywords if term in text]
        if matched:
            score = sum(3 if " " in term else 1 for term in matched)
            scores.append((clause_type, score, matched))

    if not scores:
        return {
            "predicted_clause_type": None,
            "clause_type_confidence": 0.0,
            "clause_type_matched_terms": [],
        }

    scores.sort(key=lambda item: item[1], reverse=True)
    best_type, best_score, matched_terms = scores[0]
    total_score = sum(score for _, score, _ in scores)
    confidence = best_score / total_score if total_score else 0.0
    return {
        "predicted_clause_type": best_type,
        "clause_type_confidence": round(confidence, 4),
        "clause_type_matched_terms": matched_terms[:8],
    }

from pipeline.llm_analyser import build_prompt, calibrate_risk_response, validate_response


def test_prompt_includes_benchmark_evidence_metadata():
    prompt = build_prompt(
        "Vendor may withhold payment for any reason.",
        [
            {
                "benchmark_id": "vendor_006",
                "contract_type": "vendor",
                "clause_type": "payment_terms",
                "risk_level": "high",
                "clause_text": "Customer may withhold payment for any reason.",
                "risk_rule": "Unrestricted withholding creates major cash-flow risk.",
                "why_risky": "Vendor may be forced to work without payment.",
                "safe_version": "Limit withholding to disputed amounts.",
                "source_name": "Curated Contract Risk Benchmark Library v1",
                "similarity": 0.94,
            }
        ],
        "vendor",
    )

    assert "vendor_006" in prompt
    assert "Unrestricted withholding creates major cash-flow risk." in prompt
    assert "cited_benchmark_ids" in prompt
    assert "benchmark_alignment" in prompt


def test_validate_response_requires_evidence_fields():
    response = {
        "clause_title": "Payment Withholding",
        "risk_level": "high",
        "risk_score": 90,
        "risk_reason": "The clause allows broad withholding.",
        "plain_english": "The customer can avoid paying too easily.",
        "key_concerns": ["Cash-flow risk"],
        "suggested_fix": "Limit withholding to disputed amounts.",
        "cited_benchmark_ids": ["vendor_006"],
        "risk_rule_applied": "Unrestricted withholding creates major cash-flow risk.",
        "evidence_summary": "The clause aligns closely with the high-risk payment benchmark.",
        "benchmark_alignment": "strong",
    }

    assert validate_response(response) is True

    response.pop("evidence_summary")
    assert validate_response(response) is False


def test_prompt_includes_strict_severity_rubric():
    prompt = build_prompt("This Agreement is governed by New York law.", [], "nda")

    assert "RISK SEVERITY RUBRIC" in prompt
    assert "Do not mark ordinary NDA boilerplate as high risk" in prompt
    assert "risk_reason must explicitly name the high-severity category" in prompt


def test_calibration_downgrades_unsupported_high_risk():
    response = {
        "clause_title": "Standard Governing Law",
        "risk_level": "high",
        "risk_score": 88,
        "risk_reason": "This clause is one-sided and may be unfavorable.",
        "plain_english": "The contract picks one governing law.",
        "key_concerns": ["One-sided language"],
        "suggested_fix": "Choose a mutually acceptable venue.",
        "cited_benchmark_ids": [],
        "risk_rule_applied": "",
        "evidence_summary": "No direct benchmark met the relevance threshold.",
        "benchmark_alignment": "none",
    }

    calibrated = calibrate_risk_response(response, "This Agreement is governed by New York law.", "nda")

    assert calibrated["risk_level"] == "medium"
    assert calibrated["risk_score"] == 69
    assert "severity calibration" in calibrated["risk_reason"]


def test_calibration_preserves_concrete_high_risk_trigger():
    response = {
        "clause_title": "Unlimited Enforcement Costs",
        "risk_level": "high",
        "risk_score": 92,
        "risk_reason": "The recipient must pay all legal fees and enforcement costs without limitation.",
        "plain_english": "One party can recover all enforcement costs.",
        "key_concerns": ["Unlimited fee shifting"],
        "suggested_fix": "Limit recovery to reasonable fees awarded by a court.",
        "cited_benchmark_ids": [],
        "risk_rule_applied": "",
        "evidence_summary": "No direct benchmark met the relevance threshold.",
        "benchmark_alignment": "none",
    }

    calibrated = calibrate_risk_response(response, "Recipient pays all legal fees.", "nda")

    assert calibrated["risk_level"] == "high"
    assert calibrated["risk_score"] == 92


def test_calibration_downgrades_high_when_only_low_or_medium_benchmarks_are_cited():
    response = {
        "clause_title": "Vague Monthly Invoicing",
        "risk_level": "high",
        "risk_score": 90,
        "risk_reason": "The invoicing language is vague.",
        "plain_english": "The customer is invoiced monthly without detail.",
        "key_concerns": ["Vague payment timing"],
        "suggested_fix": "Define payment terms.",
        "cited_benchmark_ids": ["vendor_004"],
        "risk_rule_applied": "Payment terms should set due dates.",
        "evidence_summary": "The benchmark addresses clearer payment timing.",
        "benchmark_alignment": "partial",
    }

    calibrated = calibrate_risk_response(
        response,
        "For the remaining amount, the Client will be invoiced every month.",
        "vendor",
        eligible_benchmarks=[{"benchmark_id": "vendor_004", "risk_level": "low"}],
    )

    assert calibrated["risk_level"] == "medium"
    assert calibrated["risk_score"] == 69


def test_calibration_preserves_high_when_cited_eligible_high_benchmark_supports_it():
    response = {
        "clause_title": "Broad Indemnity",
        "risk_level": "high",
        "risk_score": 91,
        "risk_reason": "The indemnity is broad.",
        "plain_english": "The party covers broad losses.",
        "key_concerns": ["Broad indemnity"],
        "suggested_fix": "Limit to third-party claims.",
        "cited_benchmark_ids": ["vendor_018"],
        "risk_rule_applied": "All-loss indemnity is overbroad.",
        "evidence_summary": "The benchmark directly supports the finding.",
        "benchmark_alignment": "strong",
    }

    calibrated = calibrate_risk_response(
        response,
        "Each Party indemnifies the other for any act or omission.",
        "vendor",
        eligible_benchmarks=[{"benchmark_id": "vendor_018", "risk_level": "high"}],
    )

    assert calibrated["risk_level"] == "high"
    assert calibrated["risk_score"] == 91


def test_calibration_preserves_excessive_monthly_late_fee_as_high_trigger():
    response = {
        "clause_title": "Excessive Late Fee",
        "risk_level": "high",
        "risk_score": 94,
        "risk_reason": "The monthly late fee is excessive.",
        "plain_english": "Late payments accrue a large monthly fee.",
        "key_concerns": ["Excessive late fee"],
        "suggested_fix": "Use a lawful annual rate.",
        "cited_benchmark_ids": [],
        "risk_rule_applied": "",
        "evidence_summary": "No direct benchmark met the relevance threshold.",
        "benchmark_alignment": "none",
    }

    calibrated = calibrate_risk_response(
        response,
        "Any late payments will trigger a fee of 18.00% per month on the amount still owing.",
        "vendor",
    )

    assert calibrated["risk_level"] == "high"
    assert calibrated["risk_score"] == 94

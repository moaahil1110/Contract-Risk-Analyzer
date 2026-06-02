from pipeline.llm_analyser import build_prompt, validate_response


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

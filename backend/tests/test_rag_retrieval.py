from pipeline import rag_engine


def test_retrieve_benchmarks_returns_rich_metadata(monkeypatch):
    class FakeCollection:
        def query(self, **_kwargs):
            return {
                "ids": [["vendor_006"]],
                "metadatas": [[
                    {
                        "benchmark_id": "vendor_006",
                        "contract_type": "vendor",
                        "clause_type": "payment_terms",
                        "risk_level": "high",
                        "clause_text": "Customer may withhold payment for any reason.",
                        "risk_rule": "Unrestricted withholding creates major cash-flow risk.",
                        "why_risky": "Vendor may be forced to work without payment.",
                        "risk_notes": "Vendor may be forced to work without payment.",
                        "safe_version": "Limit withholding to disputed amounts.",
                        "source_name": "Curated Contract Risk Benchmark Library v1",
                        "source_type": "curated",
                        "source_url": "local://backend/benchmarks/curated-v1",
                        "source_license_note": "Curated benchmark.",
                        "jurisdiction": "general/common-law",
                        "tags": "[\"payment\", \"withholding\"]",
                    }
                ]],
                "distances": [[0.2]],
            }

    monkeypatch.setattr(rag_engine, "get_benchmark_collection", lambda: FakeCollection())
    monkeypatch.setattr(rag_engine, "embed_text", lambda _text: [0.1, 0.2])

    results = rag_engine.retrieve_benchmarks(
        "Customer may withhold payment for any reason.",
        k=1,
        contract_type="vendor",
    )

    assert results[0]["benchmark_id"] == "vendor_006"
    assert results[0]["risk_rule"] == "Unrestricted withholding creates major cash-flow risk."
    assert results[0]["source_type"] == "curated"
    assert results[0]["tags"] == ["payment", "withholding"]

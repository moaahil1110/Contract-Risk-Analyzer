from main import _check_weasyprint_health


def test_weasyprint_health_check_returns_structured_result():
    result = _check_weasyprint_health()
    assert "usable" in result
    # On CI with system deps installed it should be True; on macOS without brew it may be False.
    # We only assert shape, not value, so the test is portable.
    if result["usable"]:
        assert isinstance(result.get("pdf_bytes"), int)
        assert result["pdf_bytes"] > 0
    else:
        assert "error" in result

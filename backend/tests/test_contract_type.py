from api.routes.analyse import detect_contract_type, resolve_contract_type


def test_detects_employment_contract():
    detection = detect_contract_type([
        "The employee will receive salary and benefits from the employer.",
        "Termination, severance, and non-compete terms apply to employment.",
    ])

    assert detection["detected_contract_type"] == "employment"
    assert detection["contract_type_confidence"] >= 0.55


def test_detects_nda_contract():
    detection = detect_contract_type([
        "This non-disclosure agreement protects confidential information.",
        "The receiving party must protect trade secret and proprietary information.",
    ])

    assert detection["detected_contract_type"] == "nda"
    assert detection["contract_type_confidence"] >= 0.55


def test_low_confidence_detection_falls_back_to_selected_type():
    metadata = resolve_contract_type(
        "vendor",
        {"detected_contract_type": "employment", "contract_type_confidence": 0.4},
    )

    assert metadata["contract_type"] == "vendor"
    assert metadata["selected_contract_type"] == "vendor"
    assert metadata["detected_contract_type"] == "employment"
    assert metadata["contract_type_conflict"] is True


def test_confident_detection_can_override_selected_type():
    metadata = resolve_contract_type(
        "nda",
        {"detected_contract_type": "employment", "contract_type_confidence": 0.9},
    )

    assert metadata["contract_type"] == "employment"
    assert metadata["contract_type_conflict"] is True

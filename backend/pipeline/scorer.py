"""
Health Score Aggregator (Week 2)
Calculates overall contract health score from individual clause analyses.
Uses weighted scoring algorithm based on risk levels.

Blueprint weights:
- Score map: high = 0, medium = 60, low = 100
- Weights: high = 3x, medium = 1.5x, low = 1x
- Grades: >=80 = A, >=60 = B, >=40 = C, <40 = D
"""

import logging
from typing import List, Dict, Any, Literal

from models.contract import HealthScore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Risk score values (base score contribution)
RISK_SCORE_MAP = {
    "high": 0,
    "medium": 60,
    "low": 100,
}

# Clause weights by risk level
RISK_WEIGHTS = {
    "high": 3.0,
    "medium": 1.5,
    "low": 1.0,
}

# Critical clause types that have higher impact on health score
CRITICAL_CLAUSE_TYPES = [
    "termination",
    "liability_cap",
    "indemnification",
    "ip_assignment",
    "non_compete",
    "payment_terms",
    "definition",  # For NDAs - scope of confidential info
]


def is_critical_clause(clause_title: str) -> bool:
    """
    Check if a clause is critical based on its title/type.
    
    Args:
        clause_title: The title/type of the clause
    
    Returns:
        True if clause is critical, False otherwise
    """
    title_lower = clause_title.lower()
    return any(critical in title_lower for critical in CRITICAL_CLAUSE_TYPES)


def calculate_clause_weight(clause: Dict[str, Any]) -> float:
    """
    Calculate weight for a clause based on criticality.
    
    Args:
        clause: Clause analysis dict
    
    Returns:
        Weight multiplier (1.0 for normal, 1.5 for critical)
    """
    if is_critical_clause(clause.get("clause_title", "")):
        return 1.5
    return 1.0


def calculate_health_score(clause_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate overall contract health score from individual clause analyses.
    
    Scoring Algorithm (Blueprint):
    - Base scores: high = 0, medium = 60, low = 100
    - Clause weights by risk: high = 3x, medium = 1.5x, low = 1x
    - Weighted average formula: sum(score * weight) / sum(weights)
    - Grades: >=80 = A, >=60 = B, >=40 = C, <40 = D
    
    Args:
        clause_analyses: List of clause analysis results
    
    Returns:
        HealthScore dict with score, grade, label, and risk counts
    """
    if not clause_analyses:
        logger.warning("No clause analyses provided, returning default health score")
        return {
            "score": 0,
            "grade": "N/A",
            "label": "No Clauses Analyzed",
            "risk_counts": {"high": 0, "medium": 0, "low": 0},
            "total_clauses": 0,
        }
    
    # Count risk levels
    risk_counts = {"high": 0, "medium": 0, "low": 0}
    
    weighted_score_sum = 0.0
    total_weight = 0.0
    
    for clause in clause_analyses:
        risk_level = clause.get("risk_level", "medium")
        
        # Count
        if risk_level in risk_counts:
            risk_counts[risk_level] += 1
        else:
            risk_counts["medium"] += 1  # Default to medium for unknown
            risk_level = "medium"
        
        # Get base score (0, 60, or 100)
        base_score = RISK_SCORE_MAP.get(risk_level, 60)
        # Get weight (3x, 1.5x, or 1x)
        weight = RISK_WEIGHTS.get(risk_level, 1.5)
        
        weighted_score_sum += base_score * weight
        total_weight += weight
    
    # Calculate weighted average health score (0-100)
    if total_weight == 0:
        health_score = 0
    else:
        health_score = int(round(weighted_score_sum / total_weight))
        health_score = max(0, min(100, health_score))
    
    # Determine grade and label based on blueprint thresholds
    grade, label = _get_grade_and_label(health_score)
    
    result = {
        "score": health_score,
        "grade": grade,
        "label": label,
        "risk_counts": risk_counts,
        "total_clauses": len(clause_analyses),
    }
    
    logger.info(f"Health score calculated: {health_score} ({grade} - {label})")
    logger.info(f"Risk distribution: {risk_counts}")
    
    return result


def _get_grade_and_label(score: int) -> tuple:
    """
    Get grade letter and risk label based on health score.
    
    Args:
        score: Health score (0-100)
    
    Returns:
        Tuple of (grade, label)
    """
    if score >= 90:
        return ("A", "Low Risk")
    elif score >= 75:
        return ("B", "Moderate Risk")
    elif score >= 60:
        return ("C", "Elevated Risk")
    elif score >= 40:
        return ("D", "High Risk")
    else:
        return ("F", "Critical Risk")


def get_score_summary(clause_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get detailed summary of contract health analysis.
    
    Args:
        clause_analyses: List of clause analysis results
    
    Returns:
        Extended summary with recommendations
    """
    health = calculate_health_score(clause_analyses)
    
    # Generate recommendations based on findings
    recommendations = []
    
    if health["risk_counts"]["high"] > 0:
        recommendations.append(
            f"Review and renegotiate {health['risk_counts']['high']} high-risk clauses before signing"
        )
    
    if health["risk_counts"]["medium"] > health["risk_counts"]["low"]:
        recommendations.append(
            "Consider requesting modifications to medium-risk clauses"
        )
    
    if health["score"] < 60:
        recommendations.append(
            "Consider having a legal professional review this contract"
        )
    
    if not recommendations:
        recommendations.append("This contract appears well-balanced. Proceed with standard review.")
    
    # Find top risk clauses
    high_risk_clauses = [
        c for c in clause_analyses 
        if c.get("risk_level") == "high"
    ]
    
    critical_clauses = [
        c for c in clause_analyses
        if is_critical_clause(c.get("clause_title", ""))
    ]
    
    return {
        **health,
        "recommendations": recommendations,
        "high_risk_count": len(high_risk_clauses),
        "critical_clause_count": len(critical_clauses),
        "high_risk_highlights": [
            {
                "title": c.get("clause_title", ""),
                "risk_reason": c.get("risk_reason", "")[:100] + "...",
            }
            for c in high_risk_clauses[:3]  # Top 3
        ],
    }


# Convenience function that returns a HealthScore model
def calculate_health_score_model(clause_analyses: List[Dict[str, Any]]) -> HealthScore:
    """
    Calculate health score and return as HealthScore Pydantic model.
    
    Args:
        clause_analyses: List of clause analysis results
    
    Returns:
        HealthScore Pydantic model instance
    """
    result = calculate_health_score(clause_analyses)
    return HealthScore(**result)


# Testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with sample clause analyses
    test_analyses = [
        {
            "clause_title": "Confidential Information Definition",
            "risk_level": "high",
            "risk_score": 85,
        },
        {
            "clause_title": "Indemnification Clause",
            "risk_level": "medium",
            "risk_score": 50,
        },
        {
            "clause_title": "Term Duration",
            "risk_level": "low",
            "risk_score": 20,
        },
        {
            "clause_title": "Return of Information",
            "risk_level": "low",
            "risk_score": 15,
        },
        {
            "clause_title": "Termination Notice",
            "risk_level": "medium",
            "risk_score": 45,
        },
    ]
    
    print("\n" + "=" * 50)
    print("Testing Scorer")
    print("=" * 50 + "\n")
    
    result = calculate_health_score(test_analyses)
    print(f"\nHealth Score Result:")
    import json
    print(json.dumps(result, indent=2))
    
    print("\n\nDetailed Summary:")
    summary = get_score_summary(test_analyses)
    print(json.dumps(summary, indent=2))

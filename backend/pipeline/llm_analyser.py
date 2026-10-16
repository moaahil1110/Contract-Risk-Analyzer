"""
LLM Analyser Module
Unified LLM interface with fallback chain and circuit breaker:
1. Groq qwen/qwen3.8-27b (primary)
2. OpenRouter google/gemma-4-31b-it:free (fallback 1)
3. NVIDIA NIM nvidia/nemotron-3-super-120b-a12b (fallback 2)
OpenCode Go is still supported but no longer in the default order.

All calls use temperature=0.1 for consistent output.
JSON parsing is wrapped in try/catch with retry logic.
429 responses open a provider circuit breaker to avoid burning quota.
"""

import os
import re
import json
import logging
import asyncio
import time
import traceback
from typing import Dict, Any, List, Optional

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")
# Nemotron reasons for longer than the free endpoint's ~30s window on full
# analysis prompts, so thinking is off unless explicitly enabled.
NVIDIA_ENABLE_THINKING = os.getenv("NVIDIA_ENABLE_THINKING", "false").lower() == "true"
OPENCODE_GO_API_KEY = os.getenv("OPENCODE_GO_API_KEY")
OPENCODE_GO_BASE_URL = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1").rstrip("/")
OPENCODE_GO_MODEL = os.getenv("OPENCODE_GO_MODEL", "deepseek-v4-flash")
LLM_TEMPERATURE = 0.1

LLM_PROVIDER_ORDER = [p.strip() for p in os.getenv("LLM_PROVIDER_ORDER", "groq,openrouter,nvidia").split(",") if p.strip()]
LLM_PROVIDER_MAX_RETRIES = max(1, int(os.getenv("LLM_PROVIDER_MAX_RETRIES", "2")))
LLM_PROVIDER_COOLDOWN_SECONDS = max(1, int(os.getenv("LLM_PROVIDER_COOLDOWN_SECONDS", "60")))
LLM_PROVIDER_MAX_COOLDOWN_SECONDS = max(
    LLM_PROVIDER_COOLDOWN_SECONDS,
    int(os.getenv("LLM_PROVIDER_MAX_COOLDOWN_SECONDS", "900")),
)
LLM_REQUEST_DELAY_MS = max(0, int(os.getenv("LLM_REQUEST_DELAY_MS", "250")))

# Circuit breaker state: provider -> available_after (monotonic timestamp)
_provider_circuits: Dict[str, float] = {}

HIGH_SEVERITY_RUBRIC = """
RISK SEVERITY RUBRIC:
- high: reserve for severe exposure such as unlimited or uncapped liability, confidentiality obligations ending too early, missing core confidentiality exclusions, broad non-compete/non-solicit/non-circumvention restraints, overbroad IP or ownership assignment, automatic injunctions, punitive damages, or one-sided fee-shifting/enforcement remedies.
- medium: broad, ambiguous, or one-sided boilerplate that should be negotiated but does not independently create severe exposure.
- low: standard administrative language or balanced clauses with normal carve-outs and reasonable limits.

Do not mark ordinary NDA boilerplate as high risk unless it matches one of the high-severity categories above.
"""

HIGH_SEVERITY_PATTERNS = [
    r"\bunlimited\b.*\bliabil",
    r"\buncapped\b.*\bliabil",
    r"\bwithout\s+limit(?:ation)?\b",
    r"\ball\s+(?:legal\s+)?(?:fees|costs|expenses)\b",
    r"\battorneys?'?\s+fees\b",
    r"\bconfidential(?:ity)?\b.*\b(?:ends?|terminates?|expires?)\b",
    r"\b(?:ends?|terminates?|expires?)\b.*\b(?:employment|termination|agreement)\b",
    r"\bno\s+(?:survival|continuing obligation)\b",
    r"\bmissing\s+(?:core\s+)?(?:exclusions|carve-outs|exceptions)\b",
    r"\bno\s+(?:public|prior|independent|compelled|required by law)\b",
    r"\bnon[-\s]compete\b",
    r"\bcompeting?\b",
    r"\bcompetitor\b",
    r"\bnon[-\s]solicit",
    r"\bsolicit(?:ation)?\b",
    r"\bdivert(?:ing)?\b",
    r"\bnon[-\s]circumvention\b",
    r"\bcircumvent",
    r"\bbusiness\s+opportunit",
    r"\bassign(?:ment)?\b.*\b(?:all|any|ownership|intellectual property|ip|work product)\b",
    r"\bownership\b.*\b(?:all|any|confidential information|inventions|work product)\b",
    r"\bautomatic(?:ally)?\b.*\b(?:injunction|injunctive|equitable relief)\b",
    r"\bliquidated damages\b",
    r"\bpunitive damages\b",
    r"\b(?:1[0-9]|[2-9]\d)(?:\.\d+)?%\s*(?:per|a)\s*month\b",
    r"\b(?:usur(?:y|ious)|unlawful interest|illegal interest|penalty rate|excessive late fee)\b",
    r"\blate payments?\b.*\b(?:fee|charge|penalt(?:y|ies))\b.*\b(?:per month|monthly)\b",
    r"\b(?:fee|charge|penalt(?:y|ies))\b.*\b(?:late payments?|overdue)\b.*\b(?:per month|monthly)\b",
    r"\bunlimited\b.*\b(?:expense|expenses|reimbursement)\b",
    r"\b(?:expense|expenses|reimbursement)\b.*\b(?:unlimited|uncapped|without limit)\b",
]

HIGH_SEVERITY_RE = re.compile("|".join(HIGH_SEVERITY_PATTERNS), re.IGNORECASE)


def _is_provider_available(provider: str) -> bool:
    available_after = _provider_circuits.get(provider)
    if available_after is None:
        return True
    if time.monotonic() >= available_after:
        del _provider_circuits[provider]
        return True
    return False


def _mark_provider_unavailable(provider: str, retry_after: Optional[int] = None) -> None:
    cooldown = retry_after if retry_after is not None else LLM_PROVIDER_COOLDOWN_SECONDS
    cooldown = max(1, min(cooldown, LLM_PROVIDER_MAX_COOLDOWN_SECONDS))
    _provider_circuits[provider] = time.monotonic() + cooldown
    logger.warning("Provider %s marked unavailable for %s seconds", provider, cooldown)


def _parse_retry_after(exc: Exception) -> Optional[int]:
    """Extract Retry-After seconds from an httpx HTTPStatusError if present."""
    if hasattr(exc, "response") and exc.response is not None:
        header = exc.response.headers.get("retry-after") or exc.response.headers.get("x-ratelimit-reset")
        if header:
            try:
                val = int(header)
                now = int(time.time())
                if val > 10_000_000_000:
                    # Some providers return epoch milliseconds.
                    val = val // 1000
                if val > now + 60:
                    # Likely epoch timestamp; convert to delta
                    return max(1, val - now)
                return val
            except (ValueError, TypeError):
                pass
    return None


def reset_provider_circuits() -> None:
    _provider_circuits.clear()


def build_prompt(clause_text: str, benchmarks: List[Dict[str, Any]], contract_type: str = "unknown") -> str:
    """
    Build a structured prompt for LLM analysis with clause and benchmarks.
    
    Args:
        clause_text: The clause text to analyze
        benchmarks: List of similar benchmark clauses from RAG
        contract_type: Type of contract (nda, employment, vendor, etc.)
    
    Returns:
        Formatted prompt string
    """
    # Format benchmarks for the prompt
    benchmark_text = ""
    for i, bench in enumerate(benchmarks[:3], 1):
        # Safely extract values and convert to strings to avoid type errors
        benchmark_id = str(bench.get("benchmark_id") or bench.get("id") or f"benchmark_{i}")
        bench_text = str(bench.get("clause_text") or bench.get("text", ""))[:450]
        risk_level = str(bench.get("risk_level", "unknown"))
        risk_rule = str(bench.get("risk_rule", ""))
        why_risky = str(bench.get("why_risky") or bench.get("risk_notes", ""))
        safe_version = str(bench.get("safe_version", ""))
        source_name = str(bench.get("source_name") or bench.get("standard_version", ""))
        similarity = bench.get("similarity", "n/a")
        
        benchmark_text += f"\nBenchmark {i}:\n"
        benchmark_text += f"  ID: {benchmark_id}\n"
        benchmark_text += f"  Contract Type: {bench.get('contract_type', 'unknown')}\n"
        benchmark_text += f"  Clause Type: {bench.get('clause_type', 'unknown')}\n"
        benchmark_text += f"  Benchmark Risk Level: {risk_level}\n"
        benchmark_text += f"  Similarity: {similarity}\n"
        benchmark_text += f"  Text: {bench_text}...\n"
        benchmark_text += f"  Risk Rule: {risk_rule}\n"
        benchmark_text += f"  Why It Matters: {why_risky}\n"
        benchmark_text += f"  Safer Version: {safe_version}\n"
        benchmark_text += f"  Source: {source_name}\n"
    
    prompt = f"""You are a legal contract risk analyst. Analyze the following contract clause and compare it against standard industry benchmarks.

CONTRACT TYPE: {contract_type.upper()}

{HIGH_SEVERITY_RUBRIC}

CLAUSE TO ANALYZE:
{clause_text}

SIMILAR BENCHMARK CLAUSES:
{benchmark_text if benchmark_text else "No strong benchmark match found. Do not cite benchmark IDs for this clause."}

Analyze this clause and respond with ONLY a valid JSON object in this exact format:
{{
  "clause_title": "Brief descriptive title for this clause (5-10 words)",
  "risk_level": "low|medium|high",
  "risk_score": 0-100 (0=no risk, 100=critical risk),
  "risk_reason": "2-3 sentences explaining the specific legal/financial risks",
  "plain_english": "Explain this clause in simple, non-legal language that a layperson would understand",
  "key_concerns": ["concern 1", "concern 2", "concern 3"],
  "suggested_fix": "Provide a rewritten, safer version of this clause",
  "cited_benchmark_ids": ["benchmark_id_1", "benchmark_id_2"],
  "risk_rule_applied": "The specific benchmark rule or legal/commercial standard used",
  "evidence_summary": "1-2 sentences explaining how retrieved benchmarks support the risk decision",
  "benchmark_alignment": "strong|partial|weak|none"
}}

IMPORTANT RULES:
1. Output ONLY valid JSON - no markdown, no code blocks, no extra text
2. risk_level must be exactly "low", "medium", or "high"
3. risk_score must be an integer between 0 and 100
4. key_concerns must be an array of strings (1-4 items)
5. cited_benchmark_ids must only contain IDs from the retrieved benchmarks shown above
6. benchmark_alignment must describe how directly the benchmarks support your decision
7. If benchmarks show this is standard language, score should be low (0-40)
8. If benchmarks show this is overly broad or risky, score should be high (70-100)
9. Consider the contract type context when assessing risk
10. If no benchmark directly applies, set benchmark_alignment to "weak" or "none" and explain the gap
11. If no strong benchmark match is shown, cited_benchmark_ids must be [] and benchmark_alignment must be "none"
12. If risk_level is "high", risk_reason must explicitly name the high-severity category that applies

Respond with JSON only:"""
    
    return prompt


def clean_and_parse(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Clean LLM response and parse as JSON.
    Wraps json.loads() in try/catch and retries on parse failure.
    
    Args:
        response_text: Raw text response from LLM
    
    Returns:
        Parsed dict or None if parsing fails
    """
    if not response_text:
        return None
    
    # Try multiple cleaning strategies
    strategies = [
        # Strategy 1: Direct JSON parse
        lambda x: x.strip(),
        
        # Strategy 2: Remove markdown code blocks
        lambda x: re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', x).strip(),
        
        # Strategy 3: Extract JSON from between curly braces
        lambda x: re.search(r'\{[\s\S]*\}', x).group(0) if re.search(r'\{[\s\S]*\}', x) else x,
        
        # Strategy 4: Remove any text before first '{' and after last '}'
        lambda x: x[x.find('{'):x.rfind('}')+1] if '{' in x and '}' in x else x,
        
        # Strategy 5: Fix common JSON issues (trailing commas)
        lambda x: re.sub(r',(\s*[}\]])', r'\1', x),
    ]
    
    for attempt, strategy in enumerate(strategies, 1):
        try:
            cleaned = strategy(response_text)
            if cleaned:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    logger.debug(f"Successfully parsed JSON using strategy {attempt}")
                    return parsed
        except Exception as e:
            logger.debug(f"Strategy {attempt} failed: {e}")
            continue
    
    logger.warning("All JSON parsing strategies failed")
    logger.exception("Full traceback for JSON parsing failure:")
    return None


def validate_response(response: Dict[str, Any]) -> bool:
    """
    Validate that LLM response has required fields.
    
    Args:
        response: Parsed dict from LLM
    
    Returns:
        True if valid, False otherwise
    """
    required_fields = [
        "clause_title",
        "risk_level",
        "risk_score",
        "risk_reason",
        "plain_english",
        "key_concerns",
        "suggested_fix",
        "cited_benchmark_ids",
        "risk_rule_applied",
        "evidence_summary",
        "benchmark_alignment",
    ]
    
    for field in required_fields:
        if field not in response:
            logger.warning(f"Missing required field: {field}")
            return False
    
    # Validate risk_level
    if response["risk_level"] not in ["low", "medium", "high"]:
        logger.warning(f"Invalid risk_level: {response['risk_level']}")
        return False
    
    # Validate risk_score
    try:
        score = int(response["risk_score"])
        if score < 0 or score > 100:
            logger.warning(f"risk_score out of range: {score}")
            return False
    except (ValueError, TypeError):
        logger.warning(f"Invalid risk_score: {response['risk_score']}")
        return False
    
    # Validate key_concerns is a list
    if not isinstance(response["key_concerns"], list):
        logger.warning(f"key_concerns is not a list: {type(response['key_concerns'])}")
        return False

    if not isinstance(response["cited_benchmark_ids"], list):
        logger.warning(f"cited_benchmark_ids is not a list: {type(response['cited_benchmark_ids'])}")
        return False

    if response["benchmark_alignment"] not in ["strong", "partial", "weak", "none"]:
        logger.warning(f"Invalid benchmark_alignment: {response['benchmark_alignment']}")
        return False
    
    return True


def _combined_risk_text(response: Dict[str, Any], clause_text: str) -> str:
    # Scan only the actual clause text and its generated title — not the LLM's
    # reasoning output.  Including risk_reason / evidence_summary / key_concerns
    # lets the model's own words accidentally satisfy the trigger check and block
    # a legitimate calibration downgrade (e.g. "creates unlimited financial risk"
    # appearing in the reasoning for a vague invoicing clause).
    return " ".join([
        clause_text,
        str(response.get("clause_title", "")),
    ])


def _has_high_severity_trigger(response: Dict[str, Any], clause_text: str) -> bool:
    return bool(HIGH_SEVERITY_RE.search(_combined_risk_text(response, clause_text)))


def _has_cited_high_risk_benchmark(
    response: Dict[str, Any],
    eligible_benchmarks: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    if not eligible_benchmarks:
        return False

    cited_ids = {str(benchmark_id) for benchmark_id in (response.get("cited_benchmark_ids") or [])}
    if not cited_ids:
        return False

    for benchmark in eligible_benchmarks:
        benchmark_ids = {
            str(benchmark.get("id", "")),
            str(benchmark.get("benchmark_id", "")),
        }
        if cited_ids.intersection(benchmark_ids) and benchmark.get("risk_level") == "high":
            return True
    return False


def calibrate_risk_response(
    response: Dict[str, Any],
    clause_text: str,
    contract_type: str = "unknown",
    eligible_count: int = 0,
    eligible_benchmarks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Prevent unsupported high-risk labels from distorting health scores.

    A high rating is kept when:
    1. the clause text itself contains a concrete high-severity trigger, OR
    2. the LLM cites a citation-eligible high-risk benchmark.

    Without either, high is downgraded to medium.
    """
    if response.get("risk_level") != "high":
        return response

    if _has_high_severity_trigger(response, clause_text):
        return response

    if _has_cited_high_risk_benchmark(response, eligible_benchmarks):
        return response

    calibrated = dict(response)
    calibrated["risk_level"] = "medium"
    try:
        calibrated["risk_score"] = min(int(calibrated.get("risk_score", 60)), 69)
    except (TypeError, ValueError):
        calibrated["risk_score"] = 60

    reason = str(calibrated.get("risk_reason", "")).strip()
    calibrated["risk_reason"] = (
        f"{reason} severity calibration downgraded this to medium risk because no concrete "
        "high-severity trigger or eligible high-risk benchmark supported a high label."
    ).strip()
    concerns = calibrated.get("key_concerns")
    if isinstance(concerns, list):
        calibrated["key_concerns"] = concerns + ["High-risk label downgraded by severity calibration"]
    return calibrated


def _evidence_failure_fields() -> Dict[str, Any]:
    return {
        "cited_benchmark_ids": [],
        "risk_rule_applied": "",
        "evidence_summary": "No benchmark-supported analysis was produced.",
        "benchmark_alignment": "none",
    }


def _try_groq(prompt: str) -> Optional[str]:
    """Try Groq and return raw response text. Returns None on 429 to open circuit."""
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set")
        return None

    try:
        logger.info("Calling Groq (%s)...", GROQ_MODEL)

        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": LLM_TEMPERATURE,
            },
            timeout=30,
        )
        logger.info("Groq status: %s", response.status_code)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            retry_after = _parse_retry_after(e)
            _mark_provider_unavailable("groq", retry_after)
            logger.warning("Groq returned 429, cooling down for %s seconds", retry_after or LLM_PROVIDER_COOLDOWN_SECONDS)
            return None
        logger.error("Groq HTTP error: %s", e)
        raise
    except Exception as e:
        logger.error("Groq error: %s", e)
        raise


def _try_openrouter(prompt: str) -> Optional[str]:
    """Try OpenRouter API and return raw response text. Returns None on 429 to open circuit."""
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set")
        return None

    try:
        logger.info("Calling OpenRouter (%s)...", OPENROUTER_MODEL)

        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": LLM_TEMPERATURE,
            },
            timeout=60,
        )
        logger.info("OpenRouter status: %s", response.status_code)
        logger.info("OpenRouter response: %s", response.text[:500])
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            retry_after = _parse_retry_after(e)
            _mark_provider_unavailable("openrouter", retry_after)
            logger.warning("OpenRouter returned 429, cooling down for %s seconds", retry_after or LLM_PROVIDER_COOLDOWN_SECONDS)
            return None
        logger.error("OpenRouter HTTP error: %s", e)
        raise
    except Exception as e:
        logger.error("OpenRouter error: %s", e)
        raise


def _try_nvidia(prompt: str) -> Optional[str]:
    """Try NVIDIA NIM and return raw response text. Returns None on 429 to open circuit."""
    if not NVIDIA_API_KEY:
        logger.warning("NVIDIA_API_KEY not set")
        return None

    try:
        logger.info("Calling NVIDIA NIM (%s)...", NVIDIA_MODEL)

        response = httpx.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": NVIDIA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": LLM_TEMPERATURE,
                "chat_template_kwargs": {"enable_thinking": NVIDIA_ENABLE_THINKING},
            },
            timeout=60,
        )
        logger.info("NVIDIA NIM status: %s", response.status_code)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            retry_after = _parse_retry_after(e)
            _mark_provider_unavailable("nvidia", retry_after)
            logger.warning("NVIDIA NIM returned 429, cooling down for %s seconds", retry_after or LLM_PROVIDER_COOLDOWN_SECONDS)
            return None
        logger.error("NVIDIA NIM HTTP error: %s", e)
        raise
    except Exception as e:
        logger.error("NVIDIA NIM error: %s", e)
        raise


def _try_opencode_go(prompt: str) -> Optional[str]:
    """Try OpenCode Go and return raw response text. Returns None on 429 to open circuit."""
    if not OPENCODE_GO_API_KEY:
        logger.warning("OPENCODE_GO_API_KEY not set")
        return None

    try:
        logger.info("Calling OpenCode Go (%s)...", OPENCODE_GO_MODEL)

        response = httpx.post(
            f"{OPENCODE_GO_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENCODE_GO_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENCODE_GO_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": LLM_TEMPERATURE,
            },
            timeout=60,
        )
        logger.info("OpenCode Go status: %s", response.status_code)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            retry_after = _parse_retry_after(e)
            _mark_provider_unavailable("opencode_go", retry_after)
            logger.warning("OpenCode Go returned 429, cooling down for %s seconds", retry_after or LLM_PROVIDER_COOLDOWN_SECONDS)
            return None
        logger.error("OpenCode Go HTTP error: %s", e)
        raise
    except Exception as e:
        logger.error("OpenCode Go error: %s", e)
        raise


def _call_provider(provider: str, prompt: str) -> Optional[str]:
    """Route to the appropriate provider."""
    if provider == "groq":
        return _try_groq(prompt)
    elif provider == "openrouter":
        return _try_openrouter(prompt)
    elif provider == "nvidia":
        return _try_nvidia(prompt)
    elif provider in {"opencode_go", "opencode"}:
        return _try_opencode_go(prompt)
    return None


def _mock_analyse_clause(contract_type: str = "unknown") -> Dict[str, Any]:
    """Return deterministic mock analysis for CI-safe E2E."""
    return {
        "clause_title": "Mock Confidentiality Clause",
        "risk_level": "medium",
        "risk_score": 55,
        "risk_reason": "This clause is overly broad in defining confidential information.",
        "plain_english": "The agreement protects all information shared between parties without clear boundaries.",
        "key_concerns": ["Overly broad definition", "No carve-outs for public information"],
        "suggested_fix": "Limit confidential information to explicitly marked or orally designated items.",
        "cited_benchmark_ids": ["mock-bench-1"],
        "risk_rule_applied": "Confidential information should be clearly defined and marked.",
        "evidence_summary": "Benchmark indicates standard NDAs require explicit marking.",
        "benchmark_alignment": "partial",
        "provider_used": "mock",
        "analysis_status": "success",
        "retry_count": 0,
        "error_message": None,
    }

async def analyse_clause(
    clause_text: str,
    benchmarks: List[Dict[str, Any]],
    contract_type: str = "unknown",
) -> Dict[str, Any]:
    """
    Analyze a clause using LLM with fallback chain.
    """
    if os.getenv("E2E_MOCK_PROVIDER", "").lower() == "true":
        return _mock_analyse_clause(contract_type)

    try:
        prompt = build_prompt(clause_text, benchmarks, contract_type)
    except Exception as e:
        logger.error("Full error in build_prompt: %s", traceback.format_exc())
        return {
            "clause_title": "Analysis Failed",
            "risk_level": "unknown",
            "risk_score": None,
            "risk_reason": f"Analysis failed: {str(e)}",
            "plain_english": "This clause could not be analyzed.",
            "key_concerns": ["Prompt building error"],
            "suggested_fix": "Please retry the analysis.",
            "analysis_status": "failed",
            "retry_count": 0,
            "error_message": str(e),
            "provider_used": "error",
            **_evidence_failure_fields(),
        }
    # Provider chain with circuit breaker and fallbacks.
    providers = [p for p in LLM_PROVIDER_ORDER if p in ("groq", "openrouter", "nvidia", "opencode_go", "opencode")]
    failed_attempts = 0
    last_error = None
    providers_tried = 0

    for provider in providers:
        if not _is_provider_available(provider):
            logger.info("Skipping provider %s (circuit open)", provider)
            continue

        logger.info("Trying provider: %s", provider)
        providers_tried += 1

        if LLM_REQUEST_DELAY_MS > 0 and providers_tried > 1:
            await asyncio.sleep(LLM_REQUEST_DELAY_MS / 1000.0)

        for attempt in range(LLM_PROVIDER_MAX_RETRIES):
            if not _is_provider_available(provider):
                logger.info("Stopping retries for provider %s (circuit opened)", provider)
                break

            try:
                response_text = await asyncio.to_thread(_call_provider, provider, prompt)

                if not response_text:
                    logger.warning("%s returned empty response (attempt %s)", provider, attempt + 1)
                    failed_attempts += 1
                    last_error = f"{provider} returned empty response"
                    if not _is_provider_available(provider):
                        break
                    continue

                parsed = clean_and_parse(response_text)

                if parsed and validate_response(parsed):
                    parsed = calibrate_risk_response(
                        parsed,
                        clause_text,
                        contract_type,
                        eligible_count=len(benchmarks),
                        eligible_benchmarks=benchmarks,
                    )
                    parsed["provider_used"] = provider
                    parsed["analysis_status"] = "retried" if failed_attempts > 0 else "success"
                    parsed["retry_count"] = failed_attempts
                    parsed["error_message"] = None
                    logger.info("Successfully analyzed with %s", provider)
                    return parsed
                else:
                    logger.warning("%s returned invalid response (attempt %s)", provider, attempt + 1)
                    failed_attempts += 1
                    last_error = f"{provider} returned invalid response"

            except Exception as e:
                logger.error("Full error in %s: %s", provider, traceback.format_exc())
                failed_attempts += 1
                last_error = str(e)
                continue

    # All providers failed - return fallback response
    logger.error("All LLM providers failed, returning fallback response")
    return {
        "clause_title": "Analysis Failed",
        "risk_level": "unknown",
        "risk_score": None,
        "risk_reason": "Unable to analyze due to LLM service unavailability. Please try again later.",
        "plain_english": "This clause could not be analyzed at this time.",
        "key_concerns": ["Analysis service temporarily unavailable"],
        "suggested_fix": "Please retry the analysis.",
        "analysis_status": "failed",
        "retry_count": failed_attempts,
        "error_message": last_error or "All LLM providers failed",
        "provider_used": "fallback",
        **_evidence_failure_fields(),
    }


# Synchronous wrapper for convenience
def analyse_clause_sync(
    clause_text: str,
    benchmarks: List[Dict[str, Any]],
    contract_type: str = "unknown",
) -> Dict[str, Any]:
    """Synchronous wrapper for analyse_clause."""
    return asyncio.run(analyse_clause(clause_text, benchmarks, contract_type))


# Testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # Test with sample clause
    test_clause = "Employee shall indemnify Company against all claims regardless of cause or fault."
    test_benchmarks = [
        {
            "benchmark_id": "vendor_016",
            "clause_text": "Vendor shall indemnify Customer against third-party claims arising from Vendor's breach.",
            "risk_rule": "Indemnity should be limited to defined third-party claims.",
            "why_risky": "Standard indemnification. Fair and reasonable.",
            "safe_version": "Limit indemnity to third-party claims with notice and control rights.",
            "risk_level": "low",
            "source_name": "Curated Contract Risk Benchmark Library v1",
            "clause_type": "indemnification",
        }
    ]
    
    print("\n" + "=" * 50)
    print("Testing LLM Analyser")
    print("=" * 50 + "\n")
    
    result = analyse_clause_sync(test_clause, test_benchmarks, "employment")
    
    print(f"\nResult:")
    print(json.dumps(result, indent=2))

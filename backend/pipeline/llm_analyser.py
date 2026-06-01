"""
LLM Analyser Module
Unified LLM interface with fallback chain:
1. Groq llama-3.3-70b-versatile (primary)
2. OpenRouter Gemma 4 (fallback 1)
3. Gemini 2.0 Flash (fallback 2)
4. Claude Sonnet (fallback 3)

All calls use temperature=0.1 for consistent output.
JSON parsing is wrapped in try/catch with retry logic.
"""

import os
import re
import json
import logging
import asyncio
import traceback
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_TEMPERATURE = 0.1
MAX_RETRIES = 3


def _get_gemini_client():
    """Lazy import and configure Gemini client."""
    try:
        import google.generativeai as genai
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
        return genai
    except ImportError:
        logger.error("google-generativeai package not installed")
        return None


def _get_anthropic_client():
    """Lazy import and return Anthropic client."""
    try:
        from anthropic import Anthropic
        if ANTHROPIC_API_KEY:
            return Anthropic(api_key=ANTHROPIC_API_KEY)
        return None
    except ImportError:
        logger.error("anthropic package not installed")
        return None


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
        bench_text = str(bench.get('text', ''))[:300]
        risk_notes = str(bench.get('risk_notes', ''))
        standard_version = str(bench.get('standard_version', ''))
        
        benchmark_text += f"\nBenchmark {i}:\n"
        benchmark_text += f"  Text: {bench_text}...\n"
        benchmark_text += f"  Risk Notes: {risk_notes}\n"
        benchmark_text += f"  Standard: {standard_version}\n"
    
    prompt = f"""You are a legal contract risk analyst. Analyze the following contract clause and compare it against standard industry benchmarks.

CONTRACT TYPE: {contract_type.upper()}

CLAUSE TO ANALYZE:
{clause_text}

SIMILAR BENCHMARK CLAUSES:
{benchmark_text if benchmark_text else "No similar benchmarks found."}

Analyze this clause and respond with ONLY a valid JSON object in this exact format:
{{
  "clause_title": "Brief descriptive title for this clause (5-10 words)",
  "risk_level": "low|medium|high",
  "risk_score": 0-100 (0=no risk, 100=critical risk),
  "risk_reason": "2-3 sentences explaining the specific legal/financial risks",
  "plain_english": "Explain this clause in simple, non-legal language that a layperson would understand",
  "key_concerns": ["concern 1", "concern 2", "concern 3"],
  "suggested_fix": "Provide a rewritten, safer version of this clause"
}}

IMPORTANT RULES:
1. Output ONLY valid JSON - no markdown, no code blocks, no extra text
2. risk_level must be exactly "low", "medium", or "high"
3. risk_score must be an integer between 0 and 100
4. key_concerns must be an array of strings (1-4 items)
5. If benchmarks show this is standard language, score should be low (0-40)
6. If benchmarks show this is overly broad or risky, score should be high (70-100)
7. Consider the contract type context when assessing risk

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
    
    return True


def _try_groq(prompt: str) -> Optional[str]:
    """Try Groq and return raw response text."""
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set")
        return None

    try:
        logger.info(f"Calling Groq ({GROQ_MODEL})...")

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
        logger.info(f"Groq status: {response.status_code}")
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error(f"Groq error: {e}")
        raise


def _try_openrouter(prompt: str) -> Optional[str]:
    """Try OpenRouter API and return raw response text."""
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set")
        return None

    try:
        logger.info(f"Calling OpenRouter ({OPENROUTER_MODEL})...")

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
        logger.info(f"OpenRouter status: {response.status_code}")
        logger.info(f"OpenRouter response: {response.text[:500]}")
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        raise


def _try_gemini(prompt: str) -> Optional[str]:
    """Try Gemini 2.0 Flash and return raw response text."""
    try:
        genai = _get_gemini_client()
        if not genai or not GEMINI_API_KEY:
            return None
        
        logger.info("Calling Gemini 2.0 Flash...")
        
        # Configure model
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config={
                "temperature": LLM_TEMPERATURE,
            },
        )
        
        response = model.generate_content(prompt)
        
        if response and response.text:
            return response.text
        return None
        
    except Exception as e:
        logger.warning(f"Gemini call failed: {e}")
        return None


def _try_claude(prompt: str) -> Optional[str]:
    """Try Claude and return raw response text."""
    try:
        client = _get_anthropic_client()
        if not client or not ANTHROPIC_API_KEY:
            return None
        
        logger.info("Calling Claude...")
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            temperature=LLM_TEMPERATURE,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )
        
        if response and response.content:
            return response.content[0].text
        return None
        
    except Exception as e:
        logger.warning(f"Claude call failed: {e}")
        return None


def _call_provider(provider: str, prompt: str) -> Optional[str]:
    """Route to the appropriate provider."""
    if provider == "groq":
        return _try_groq(prompt)
    elif provider == "openrouter":
        return _try_openrouter(prompt)
    elif provider == "gemini":
        return _try_gemini(prompt)
    elif provider == "claude":
        return _try_claude(prompt)
    return None


async def analyse_clause(
    clause_text: str,
    benchmarks: List[Dict[str, Any]],
    contract_type: str = "unknown",
) -> Dict[str, Any]:
    """
    Analyze a clause using LLM with fallback chain.
    
    Args:
        clause_text: The clause to analyze
        benchmarks: Similar benchmark clauses from RAG
        contract_type: Type of contract (nda, employment, vendor)
    
    Returns:
        Analysis dict matching the Clause model
    """
    try:
        prompt = build_prompt(clause_text, benchmarks, contract_type)
    except Exception as e:
        logger.error(f"Full error in build_prompt: {traceback.format_exc()}")
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
        }
    
    # Provider chain with fallbacks
    providers = ["groq", "openrouter", "gemini", "claude"]
    failed_attempts = 0
    last_error = None
    
    for provider in providers:
        logger.info(f"Trying provider: {provider}")
        
        # Try multiple times with different parsing strategies
        for attempt in range(MAX_RETRIES):
            try:
                # Call the provider
                response_text = await asyncio.to_thread(_call_provider, provider, prompt)
                
                if not response_text:
                    logger.warning(f"{provider} returned empty response (attempt {attempt + 1})")
                    failed_attempts += 1
                    last_error = f"{provider} returned empty response"
                    continue
                
                # Parse and validate
                parsed = clean_and_parse(response_text)
                
                if parsed and validate_response(parsed):
                    # Add metadata
                    parsed["provider_used"] = provider
                    parsed["analysis_status"] = "retried" if failed_attempts > 0 else "success"
                    parsed["retry_count"] = failed_attempts
                    parsed["error_message"] = None
                    logger.info(f"Successfully analyzed with {provider}")
                    return parsed
                else:
                    logger.warning(f"{provider} returned invalid response (attempt {attempt + 1})")
                    failed_attempts += 1
                    last_error = f"{provider} returned invalid response"
                    
            except Exception as e:
                logger.error(f"Full error in {provider}: {traceback.format_exc()}")
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
            "text": "Vendor shall indemnify Customer against third-party claims arising from Vendor's breach.",
            "risk_notes": "Standard indemnification. Fair and reasonable.",
            "standard_version": "Standard",
            "clause_type": "indemnification",
        }
    ]
    
    print("\n" + "=" * 50)
    print("Testing LLM Analyser")
    print("=" * 50 + "\n")
    
    result = analyse_clause_sync(test_clause, test_benchmarks, "employment")
    
    print(f"\nResult:")
    print(json.dumps(result, indent=2))

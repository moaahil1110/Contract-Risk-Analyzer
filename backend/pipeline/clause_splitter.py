"""
Clause Splitter Module
Segments contract text into individual clauses using regex first, 
with Qwen3.5 fallback for complex or narrative-style contracts.
"""

import re
import json
import logging
from collections import Counter
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import ollama
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available. LLM fallback disabled.")


# Regex patterns for clause detection
CLAUSE_PATTERNS = [
    # Numbered sections: "1.", "1.1", "1.1.1"
    r'(?:^|\n)\s*(?:\d+\.)+\s+',
    # Article/Section/Clause headings: "Article 1", "Section 1", "Clause 1"
    r'(?:^|\n)\s*(?:ARTICLE|Article|SECTION|Section|CLAUSE|Clause)\s+\d+[.:]?\s*',
    # Roman numerals: "I.", "II.", "(i)", "(ii)"
    r'(?:^|\n)\s*(?:[IVX]+\.|[ivx]+\.|\([ivx]+\))\s+',
    # Lettered sections: "(a)", "(b)", "A.", "B."
    r'(?:^|\n)\s*\([a-z]\)\s+',
]

# Combined pattern
CLAUSE_SPLIT_PATTERN = r'(' + '|'.join(CLAUSE_PATTERNS) + r')'
TOP_LEVEL_CLAUSE_PATTERN = re.compile(
    r"(?m)^\s*((?:\d+)\.|(?:ARTICLE|Article|SECTION|Section|CLAUSE|Clause)\s+\d+[.:]?)\s*"
)
SECTION_MARKER_PATTERN = re.compile(
    r"(?m)^\s*((?:\d+(?:\.\d+)+\.?)|(?:\([a-z]\)|\([ivx]+\)|[ivx]+\.|[A-Z]\.))\s*"
)

# Matches a lone section heading that leaked in from the next clause boundary:
# e.g. "Confidentiality", "Ownership of Intellectual Property", "Governing Law"
_ORPHAN_HEADING_RE = re.compile(
    r"(?:\n[ \t]*){1,3}([A-Z][A-Za-z /()&-]{0,69})\s*$"
)


def _strip_trailing_heading(text: str) -> str:
    """Remove a lone section heading that bled in from the next clause's boundary.

    The contract PDF text often has the *next* section's heading sitting on its
    own line right before the next numbered clause marker, so it ends up appended
    to the preceding clause's text during regex splitting.  This causes the
    keyword classifier to predict the wrong clause type (e.g. 'confidentiality'
    for a payment clause that ends with 'Confidentiality').
    """
    m = _ORPHAN_HEADING_RE.search(text)
    if not m:
        return text
    candidate = m.group(1).strip()
    words = candidate.split()
    # Accept as a heading: 1–5 words, no terminal punctuation, no function words
    # that signal a genuine sentence fragment worth keeping.
    if (
        1 <= len(words) <= 5
        and candidate[-1] not in ".,:;?!"
        and not re.search(
            r"\b(will|shall|must|may|is|are|was|were|has|have|had|the|a|an)\b",
            candidate,
        )
    ):
        stripped = text[: m.start()].rstrip()
        if len(stripped.strip()) >= 30:
            return stripped
    return text


def _line_key(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().lower())


def _looks_like_clause_start(line: str) -> bool:
    return bool(re.match(
        r"^\s*(?:\d+(?:\.\d+)*\.?|[A-Z]\.|[IVX]+\.|\([a-z]\)|(?:article|section|clause)\s+\d+)",
        line,
        flags=re.IGNORECASE,
    ))


def clean_extracted_text(text: str) -> str:
    """Remove deterministic PDF page artifacts without changing clause numbering."""
    if not text:
        return ""

    raw_lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    keys = [
        _line_key(line)
        for line in raw_lines
        if 0 < len(_line_key(line)) <= 90 and not _looks_like_clause_start(line)
    ]
    repeated = {key for key, count in Counter(keys).items() if count >= 2}

    cleaned_lines: List[str] = []
    for line in raw_lines:
        stripped = line.strip()
        key = _line_key(line)
        if not stripped:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if re.fullmatch(r"page\s+\d+(?:\s+of\s+\d+)?", stripped, flags=re.IGNORECASE):
            continue
        if re.fullmatch(r"\d+\s*(?:of\s*\d+)?", stripped, flags=re.IGNORECASE):
            continue
        if key in repeated:
            continue
        cleaned_lines.append(stripped)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def split_clauses_regex(text: str, min_clause_length: int = 50) -> List[str]:
    """
    Split contract text into clauses using regex patterns.
    
    Args:
        text: Full contract text
        min_clause_length: Minimum character length to consider a valid clause
    
    Returns:
        List of clause strings
    """
    if not text or not text.strip():
        return []
    
    text = clean_extracted_text(text)

    # Combined regex pattern for all clause markers
    pattern = r'(?=(?:^|\n)\s*(?:(?:\d+\.)+|(?:ARTICLE|Article|SECTION|Section|CLAUSE|Clause)\s+\d+[.:]?\s*|(?:[IVX]+\.|[ivx]+\.|\([ivx]+\))\s*|\([a-z]\)\s+))'
    
    # Split the text
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    
    # Filter and clean clauses
    clauses = []
    for part in parts:
        if not part:
            continue
        
        # Clean up whitespace
        clean = part.strip()
        
        # Skip if too short
        if len(clean) < min_clause_length:
            continue
        
        # Skip common headers/footers
        if _is_likely_header_or_footer(clean):
            continue
        
        clauses.append(clean)
    
    logger.info(f"Regex splitter found {len(clauses)} clauses")
    return clauses


def _normalize_marker(marker: str) -> str:
    marker = re.sub(r"\s+", " ", marker.strip())
    marker = re.sub(r"\.$", "", marker)
    return marker


def _heading_from_clause(text: str, marker: str) -> str:
    first_line = re.sub(r"\s+", " ", text.strip().splitlines()[0] if text.strip() else "")
    first_line = re.sub(rf"^\s*{re.escape(marker)}\.?\s*", "", first_line).strip()
    return first_line[:120]


def _section_level(marker: str) -> int:
    normalized = _normalize_marker(marker)
    if re.fullmatch(r"\d+", normalized):
        return 1
    if re.fullmatch(r"\d+(?:\.\d+)+", normalized):
        return normalized.count(".") + 1
    return 2


def _extract_subclauses(parent_text: str, parent_number: str) -> List[Dict[str, Any]]:
    subclauses: List[Dict[str, Any]] = []
    matches = list(SECTION_MARKER_PATTERN.finditer(parent_text))
    for idx, match in enumerate(matches):
        marker = _normalize_marker(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(parent_text)
        section_text = parent_text[start:end].strip()
        if len(section_text) < 20:
            continue
        subclauses.append({
            "clause_number": marker,
            "parent_clause_number": parent_number,
            "clause_level": _section_level(marker),
            "heading": _heading_from_clause(section_text, marker),
            "section_type": "subclause",
            "is_scored": False,
            "original_text": section_text,
        })
    return subclauses


def split_clauses_structured(text: str, min_clause_length: int = 50) -> List[Dict[str, Any]]:
    """Split into scored top-level clauses while preserving nested sections."""
    if not text or not text.strip():
        return []

    text = clean_extracted_text(text)
    matches = list(TOP_LEVEL_CLAUSE_PATTERN.finditer(text))
    if not matches:
        return []

    clauses: List[Dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        clause_text = _strip_trailing_heading(text[start:end].strip())
        if len(clause_text) < min(20, min_clause_length) or _is_likely_header_or_footer(clause_text):
            continue

        marker = _normalize_marker(match.group(1))
        subclauses = _extract_subclauses(clause_text, marker)
        clauses.append({
            "clause_index": len(clauses),
            "clause_number": marker,
            "parent_clause_number": None,
            "clause_level": 1,
            "heading": _heading_from_clause(clause_text, marker),
            "section_type": "clause",
            "is_scored": True,
            "text": clause_text,
            "original_text": clause_text,
            "subclauses": subclauses,
            "parsed_section_count": 1 + len(subclauses),
        })

    logger.info(
        "Structured splitter found %s top-level clauses and %s parsed sections",
        len(clauses),
        sum(c.get("parsed_section_count", 1) for c in clauses),
    )
    return clauses


def _is_likely_header_or_footer(text: str) -> bool:
    """Check if text is likely a page header, footer, or boilerplate."""
    text_lower = text.lower()
    
    # Common header/footer patterns
    skip_patterns = [
        r'^\d+$',  # Just a page number
        r'^page\s+\d+',  # "Page 1"
        r'^page\s+\d+\s+of\s+\d+',  # "Page 1 of 10"
        r'^confidential',  # Just "Confidential"
        r'^draft',  # Just "Draft"
        r'^©\s*\d{4}',  # Copyright
        r'^all rights reserved',
    ]
    
    for pattern in skip_patterns:
        if re.match(pattern, text_lower):
            return True
    
    return False


async def split_clauses_llm(text: str, max_chars: int = 8000) -> List[str]:
    """
    Fall back to Qwen3.5 via Ollama to extract clauses from messy contracts.
    
    Args:
        text: Full contract text
        max_chars: Maximum characters to send to LLM (to avoid token limits)
    
    Returns:
        List of clause strings
    """
    if not OLLAMA_AVAILABLE:
        logger.warning("Ollama not available, cannot use LLM fallback")
        return []
    
    # Truncate if too long
    truncated = text[:max_chars]
    
    prompt = f"""You are a legal document analyzer. Extract each distinct clause or provision from the following contract as a separate item.

Instructions:
- Identify clear logical breaks between different provisions
- Each clause should be a complete legal statement or paragraph
- Preserve the original text as much as possible
- Skip headers, footers, page numbers, and boilerplate
- Return ONLY a valid JSON array of strings, nothing else

CONTRACT TEXT:
{truncated}

Return format: ["clause 1 text", "clause 2 text", ...]

Respond with only the JSON array. No markdown, no explanation."""

    try:
        logger.info("Calling Qwen3.5 via Ollama for clause extraction...")
        
        response = ollama.chat(
            model="qwen3.5:9b",
            messages=[
                {"role": "system", "content": "You are a precise legal document analyzer. Output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            options={
                "temperature": 0.1,
            }
        )
        
        response_text = response['message']['content']
        
        # Parse JSON from response
        clauses = _extract_json_from_text(response_text)
        
        if clauses and isinstance(clauses, list):
            # Filter out short clauses
            clauses = [c for c in clauses if isinstance(c, str) and len(c.strip()) >= 50]
            logger.info(f"LLM splitter found {len(clauses)} clauses")
            return clauses
        else:
            logger.warning("LLM did not return a valid list of clauses")
            return []
            
    except Exception as e:
        logger.error(f"LLM clause extraction failed: {e}")
        return []


def _extract_json_from_text(text: str) -> Optional[List]:
    """Extract and parse JSON array from text that may contain markdown or other content."""
    # Try to find JSON array in the text
    json_match = re.search(r'\[.*?\]', text, re.DOTALL)
    
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Try the whole text
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    
    return None


async def split_clauses(text: str, min_clause_length: int = 50, min_clauses_threshold: int = 3) -> List[Any]:
    """
    Hybrid clause splitter: regex first, LLM fallback if needed.
    
    Args:
        text: Full contract text
        min_clause_length: Minimum length for valid clauses
        min_clauses_threshold: If regex finds fewer clauses than this, try LLM
    
    Returns:
        List of clause strings
    """
    if not text or not text.strip():
        logger.warning("Empty text provided to clause splitter")
        return []
    
    # Stage 1: Try structured top-level regex first
    structured_clauses = split_clauses_structured(text, min_clause_length)
    if len(structured_clauses) >= min_clauses_threshold:
        return structured_clauses

    # Stage 2: Try legacy flat regex
    clauses = split_clauses_regex(text, min_clause_length)
    
    # Stage 3: If regex found too few clauses, try LLM
    if len(clauses) < min_clauses_threshold:
        logger.info(f"Regex found only {len(clauses)} clauses, trying LLM fallback...")
        llm_clauses = await split_clauses_llm(text)
        
        if len(llm_clauses) >= len(clauses):
            logger.info(f"Using LLM results: {len(llm_clauses)} clauses")
            return llm_clauses
        else:
            logger.info("LLM did not improve results, using regex output")
    
    return clauses


if __name__ == "__main__":
    import asyncio
    import sys
    
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            sample_text = f.read()
    else:
        # Sample contract text for testing
        sample_text = """
1. DEFINITIONS
"Confidential Information" means any and all non-public information disclosed by either party.

2. TERM
This Agreement shall commence on the Effective Date and continue for a period of one year.

3. OBLIGATIONS OF THE PARTIES
Each party agrees to maintain the confidentiality of all Confidential Information.

This is just some boilerplate footer text.
"""
    
    async def test():
        print(f"Input text length: {len(sample_text)}\n")
        
        # Test regex
        print("--- Regex Splitter ---")
        regex_clauses = split_clauses_regex(sample_text)
        for i, c in enumerate(regex_clauses, 1):
            print(f"Clause {i}: {c[:100]}...")
        
        print(f"\nTotal: {len(regex_clauses)} clauses")
        
        # Test hybrid
        print("\n--- Hybrid Splitter ---")
        all_clauses = await split_clauses(sample_text)
        for i, c in enumerate(all_clauses, 1):
            print(f"Clause {i}: {c[:100]}...")
        
        print(f"\nTotal: {len(all_clauses)} clauses")
    
    asyncio.run(test())

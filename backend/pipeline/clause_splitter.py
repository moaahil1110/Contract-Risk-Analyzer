"""
Clause Splitter Module
Segments contract text into individual clauses using regex first, 
with Qwen3.5 fallback for complex or narrative-style contracts.
"""

import re
import json
import logging
from typing import List, Optional

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


def _is_likely_header_or_footer(text: str) -> bool:
    """Check if text is likely a page header, footer, or boilerplate."""
    text_lower = text.lower()
    
    # Common header/footer patterns
    skip_patterns = [
        r'^\d+$',  # Just a page number
        r'^page\s+\d+',  # "Page 1"
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


async def split_clauses(text: str, min_clause_length: int = 50, min_clauses_threshold: int = 3) -> List[str]:
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
    
    # Stage 1: Try regex first
    clauses = split_clauses_regex(text, min_clause_length)
    
    # Stage 2: If regex found too few clauses, try LLM
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

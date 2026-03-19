import re
import json
import httpx
import asyncio
import logging
import os
from typing import AsyncGenerator
from models import Claim

logger = logging.getLogger(__name__)

# ── Groq API Config ────────────────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama3-8b-8192"
# Other options: "mixtral-8x7b-32768" | "llama3-70b-8192"

# ── Sentence Boundary ──────────────────────────────────────────────────────────
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

# ── Claim Detection Patterns ───────────────────────────────────────────────────
PATTERNS = {
    "number": re.compile(
        r'\$[\d,.]+\s*(?:billion|million|trillion|thousand)?'
        r'|\d+(?:\.\d+)?%'
        r'|\d+(?:\.\d+)?\s*(?:billion|million|trillion)'
        r'|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b',
        re.IGNORECASE
    ),
    "date": re.compile(
        r'\bQ[1-4]\s*\d{4}\b'
        r'|\b(?:January|February|March|April|May|June|July|'
        r'August|September|October|November|December)\s+\d{4}\b'
        r'|\bFY\s*\d{4}\b'
        r'|\bfiscal\s+year\s+\d{4}\b',
        re.IGNORECASE
    ),
    "name": re.compile(
        r'\b(?:Apple|Microsoft|Google|Amazon|Tesla|Nvidia|'
        r'Goldman Sachs|JPMorgan|Meta|Netflix|OpenAI|'
        r'Federal Reserve|Fed|S&P\s*500|Nasdaq|Dow Jones)\b',
        re.IGNORECASE
    ),
    "policy": re.compile(
        r'\b(?:interest rate|inflation rate|CPI|GDP|'
        r'federal funds rate|prime rate|unemployment rate|'
        r'trade deficit|budget deficit)\b',
        re.IGNORECASE
    ),
    "statistic": re.compile(
        r'\b\d+(?:\.\d+)?\s*(?:percent|basis points?|bps|times)\b'
        r'|\bgrew?\s+(?:by\s+)?\d+(?:\.\d+)?%'
        r'|\b(?:increased?|decreased?|rose?|fell?|dropped?)\s+\d+',
        re.IGNORECASE
    ),
}


# ── Claim Extractor ────────────────────────────────────────────────────────────
def extract_claims(sentence: str) -> list[Claim]:
    """Scan a completed sentence for factual claims using regex."""
    claims = []
    seen_positions = set()

    for claim_type, pattern in PATTERNS.items():
        for match in pattern.finditer(sentence):
            pos = match.start()
            if pos in seen_positions:
                continue
            seen_positions.add(pos)
            claims.append(Claim(
                text=match.group().strip(),
                type=claim_type,
                position=pos,
                sentence=sentence.strip()
            ))

    return claims


# ── Groq Stream ────────────────────────────────────────────────────────────────
async def _stream_groq(query: str) -> AsyncGenerator[str, None]:
    """
    Stream tokens from Groq API.
    Get your free API key at: https://console.groq.com
    Add to backend/.env as: GROQ_API_KEY=gsk_...
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. "
            "Get a free key at console.groq.com and add to backend/.env"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a financial analysis assistant. "
                    "Answer questions about company financials, market data, "
                    "and economic indicators using specific numbers, "
                    "percentages, and statistics."
                )
            },
            {"role": "user", "content": query}
        ],
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 500,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST", GROQ_API_URL,
            headers=headers,
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


# ── Mock Stream ────────────────────────────────────────────────────────────────
async def _stream_mock(query: str) -> AsyncGenerator[str, None]:
    """
    Mock stream for testing without a Groq API key.
    Contains deliberate hallucinations to demo the correction pipeline.
    Enable by setting USE_MOCK=true in backend/.env
    """
    mock_response = (
        "Apple Inc reported revenue of $523 billion in fiscal year 2022. "
        "Microsoft Azure cloud revenue grew 45% year-over-year in Q4 2023. "
        "Tesla delivered 2.1 million vehicles in 2023, marking a record year. "
        "The Federal Reserve held interest rates at 4.75% in December 2023. "
        "Nvidia revenue for fiscal year 2024 reached $45.2 billion. "
        "JPMorgan Chase reported net income of $38.2 billion in 2023."
    )
    for word in mock_response.split(" "):
        yield word + " "
        await asyncio.sleep(0.04)


# ── Core Interceptor Generator ─────────────────────────────────────────────────
async def stream_and_detect(
    query: str
) -> AsyncGenerator[tuple[str, list[Claim]], None]:
    """
    Main interceptor generator — called by main.py firewall pipeline.

    Yields:
      ("TOKEN:<text>", [])         → raw token, stream to frontend immediately
      ("<sentence>",  [Claim, …])  → completed sentence + detected claims
      ("ERROR:<msg>", [])          → on any failure
    """
    use_mock = os.getenv("USE_MOCK", "false").lower() == "true"
    buffer = ""
    token_count = 0
    stream_fn = _stream_mock if use_mock else _stream_groq

    try:
        async for token in stream_fn(query):
            buffer += token
            token_count += 1

            # Yield raw token IMMEDIATELY for live frontend streaming
            yield (f"TOKEN:{token}", [])

            # Detect completed sentences in buffer
            parts = SENTENCE_END.split(buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    claims = extract_claims(sentence)
                    logger.debug(
                        f"Sentence complete | "
                        f"'{sentence[:60]}' | "
                        f"Claims: {len(claims)}"
                    )
                    yield (sentence, claims)
                buffer = parts[-1]

        # Flush remaining buffer after stream ends
        if buffer.strip():
            claims = extract_claims(buffer.strip())
            yield (buffer.strip(), claims)

    except ValueError as e:
        logger.error(f"Config error: {e}")
        yield (f"ERROR:{str(e)}", [])

    except httpx.HTTPStatusError as e:
        logger.error(f"Groq API error {e.response.status_code}")
        yield (f"ERROR:Groq API returned {e.response.status_code}", [])

    except httpx.ConnectError:
        logger.error("Could not connect to Groq API")
        yield ("ERROR:Cannot reach Groq API. Check internet connection.", [])

    except Exception as e:
        logger.error(f"Interceptor error: {e}", exc_info=True)
        yield (f"ERROR:{str(e)}", [])

    logger.info(f"Stream complete. Total tokens: {token_count}")
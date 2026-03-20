"""
interceptor.py — Streaming Interceptor with OpenAI Logprob-Based Entropy Detection

Uses the OpenAI API with logprobs=True and top_logprobs=5 to compute
Shannon entropy at every token position.

H(t) = -sum( p_i * log2(p_i) ) over top-k candidate tokens at position t

High-entropy tokens signal model uncertainty — contiguous high-entropy spans
are flagged as potential claims to verify. Combined with regex-based detection
for financial entities and named companies.

References:
  - Semantic Entropy (Kuhn et al., 2023)
  - Kernel Language Entropy (ICLR 2024)
"""

import re
import json
import math
import httpx
import asyncio
import logging
import os
from typing import AsyncGenerator
from models import Claim

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL   = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()

# Shannon entropy threshold — tokens above this are "uncertain"
# gpt-4o-mini default: 0 = perfectly confident, ~3.0 = very uncertain
ENTROPY_THRESHOLD = 1.2

# Number of top candidate tokens to request for entropy computation
TOP_LOGPROBS = 5

# Sentence boundary detector
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

# Regex patterns for financial entities (backup/complement to entropy)
NUMBER_PATTERN = re.compile(
    r'\$?\b\d+(?:\.\d+)?\s?(?:billion|million|trillion|%|percent)?\b',
    re.IGNORECASE
)
DATE_PATTERN = re.compile(
    r'\b(?:Q[1-4]\s+\d{4}|FY\s?\d{4}|'
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})\b',
    re.IGNORECASE
)
NAME_PATTERN = re.compile(
    r'\b(?:Apple|Microsoft|Tesla|Amazon|Nvidia|JPMorgan|Goldman Sachs|'
    r'Federal Reserve|AWS|Azure|S&P 500|US CPI|OpenAI|Google|Meta|Alphabet)\b',
    re.IGNORECASE
)


# ─────────────────────────────────────────────────────────────────────────────
# Shannon Entropy
# ─────────────────────────────────────────────────────────────────────────────
def compute_entropy(top_logprobs: list[dict]) -> float:
    """
    Compute Shannon entropy from the top-k logprob distribution.
    H = -sum( p_i * log2(p_i) )
    Returns 0.0 if no logprobs available.
    """
    if not top_logprobs:
        return 0.0

    entropy = 0.0
    for entry in top_logprobs:
        logprob = entry.get("logprob", -100)
        p = math.exp(logprob)   # convert log-prob → probability
        if p > 1e-10:
            entropy -= p * math.log2(p)

    return entropy


# ─────────────────────────────────────────────────────────────────────────────
# Claim Detection (regex)
# ─────────────────────────────────────────────────────────────────────────────
def detect_claims(sentence: str) -> list[Claim]:
    claims: list[Claim] = []

    for match in NUMBER_PATTERN.finditer(sentence):
        claims.append(Claim(
            text=match.group().strip(),
            type="number",
            position=match.start(),
            sentence=sentence.strip(),
        ))

    for match in DATE_PATTERN.finditer(sentence):
        claims.append(Claim(
            text=match.group().strip(),
            type="date",
            position=match.start(),
            sentence=sentence.strip(),
        ))

    for match in NAME_PATTERN.finditer(sentence):
        claims.append(Claim(
            text=match.group().strip(),
            type="name",
            position=match.start(),
            sentence=sentence.strip(),
        ))

    # Deduplicate
    deduped, seen = [], set()
    for claim in claims:
        key = (claim.text.lower(), claim.type, claim.position)
        if key not in seen:
            seen.add(key)
            deduped.append(claim)

    return deduped


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Streaming (with logprobs)
# ─────────────────────────────────────────────────────────────────────────────
async def _stream_openai(query: str) -> AsyncGenerator[tuple[str, float], None]:
    """
    Streams tokens from OpenAI with logprobs.
    Yields (token_text, entropy) tuples.
    """
    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not set in backend/.env")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    payload = {
        "model":       MISTRAL_MODEL,
        "messages": [
            {
                "role":    "system",
                "content": (
                    "You are a financial analysis assistant. "
                    "Answer questions about company financials, market data, "
                    "economic indicators, and uploaded documents clearly and concisely."
                ),
            },
            {"role": "user", "content": query},
        ],
        "stream":       True,
        "temperature":  0.3,
        "max_tokens":   500,
        "logprobs":     True,
        "top_logprobs": TOP_LOGPROBS,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            MISTRAL_API_URL,
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise httpx.HTTPStatusError(
                    f"Mistral returned {response.status_code}: "
                    f"{body.decode(errors='ignore')[:300]}",
                    request=response.request,
                    response=response,
                )

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data = line[6:].strip()
                if data == "[DONE]":
                    break

                try:
                    chunk  = json.loads(data)
                    choice = chunk["choices"][0]
                    delta  = choice.get("delta", {})
                    content = delta.get("content", "")
                    if not content:
                        continue

                    # Extract logprobs for entropy computation
                    logprobs_data = choice.get("logprobs") or {}
                    token_logprobs = logprobs_data.get("content") or []

                    entropy = 0.0
                    if token_logprobs:
                        top_lp = token_logprobs[0].get("top_logprobs", [])
                        entropy = compute_entropy(top_lp)

                    yield (content, entropy)

                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue


# ─────────────────────────────────────────────────────────────────────────────
# Mock Streaming (for offline demo)
# ─────────────────────────────────────────────────────────────────────────────
async def _stream_mock(query: str) -> AsyncGenerator[tuple[str, float], None]:
    """
    Mock stream with deliberate hallucinations.
    Assigns synthetic entropy values — high entropy on wrong numbers.
    """
    mock_tokens = [
        ("Apple",     0.1),
        (" reported", 0.2),
        (" revenue",  0.3),
        (" of",       0.1),
        (" $523",     2.8),   # ← high entropy — hallucinated number
        (" billion",  2.5),
        (" in",       0.2),
        (" fiscal",   0.3),
        (" year",     0.2),
        (" 2022",     0.4),
        (".",         0.1),
        (" Microsoft",0.1),
        (" Azure",    0.2),
        (" grew",     0.3),
        (" 45%",      2.9),   # ← high entropy — hallucinated percentage
        (" in",       0.2),
        (" Q4",       0.4),
        (" 2023",     0.3),
        (".",         0.1),
        (" Tesla",    0.1),
        (" delivered",0.3),
        (" 2.1",      2.6),   # ← high entropy — hallucinated delivery count
        (" million",  2.4),
        (" vehicles", 0.2),
        (" in",       0.1),
        (" 2023",     0.3),
        (".",         0.1),
    ]
    for token, entropy in mock_tokens:
        yield (token, entropy)
        await asyncio.sleep(0.04)


# ─────────────────────────────────────────────────────────────────────────────
# Main Generator: stream_and_detect()
# Called by main.py's firewall pipeline
# ─────────────────────────────────────────────────────────────────────────────
async def stream_and_detect(query: str) -> AsyncGenerator[tuple, None]:
    """
    Streams tokens with entropy scores.
    Yields:
      ("TOKEN:<text>", [])            — for every incoming token
      ("<sentence>",  [Claim, ...])   — for each completed sentence
    """
    use_mock   = os.getenv("USE_MOCK", "false").lower() == "true"
    stream_fn  = _stream_mock if use_mock else _stream_openai

    text_buffer       = ""
    token_count       = 0
    high_entropy_span = []   # accumulates uncertain tokens

    try:
        async for token, entropy in stream_fn(query):
            token_count  += 1
            text_buffer  += token

            # Always yield the raw token for streaming display
            yield (f"TOKEN:{token}", [])

            # Track high-entropy spans
            if entropy >= ENTROPY_THRESHOLD:
                high_entropy_span.append(token)
                logger.debug(
                    f"High entropy token: '{token.strip()}' H={entropy:.3f}"
                )
            else:
                if high_entropy_span:
                    span_text = "".join(high_entropy_span).strip()
                    logger.info(
                        f"High-entropy span detected: '{span_text}' "
                        f"({len(high_entropy_span)} tokens)"
                    )
                high_entropy_span = []

            # Check for sentence completion
            parts = SENTENCE_END.split(text_buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    claims = detect_claims(sentence)
                    yield (sentence, claims)

                text_buffer = parts[-1]

        # Flush remaining buffer
        if text_buffer.strip():
            claims = detect_claims(text_buffer.strip())
            yield (text_buffer.strip(), claims)

    except ValueError as e:
        logger.error(f"Config error: {e}")
        yield (f"ERROR:{str(e)}", [])

    except httpx.HTTPStatusError as e:
        logger.error(f"OpenAI API error: {e}")
        yield (f"ERROR:{str(e)}", [])

    except httpx.ConnectError:
        logger.error("Cannot reach Mistral API")
        yield ("ERROR:Cannot reach Mistral API. Check your internet connection.", [])

    except Exception as e:
        logger.error(f"Interceptor error: {e}", exc_info=True)
        yield (f"ERROR:{str(e)}", [])

    logger.info(f"Stream done | tokens: {token_count}")
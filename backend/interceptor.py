"""
interceptor.py — Streaming Interceptor with Entropy-Based Claim Detection

Groq returns per-token logprob (log probability of the chosen token).
We compute single-token uncertainty from that value:

    p     = exp(logprob)
    H(t)  = -p * log(p)

High H(t) means the model assigned lower confidence to its chosen token,
which we use as an uncertainty signal for possible factual claims.

Updated to use the current Groq model via environment variable,
with a safe default that is not deprecated.
"""

import re
import json
import math
import httpx
import asyncio
import logging
import os
from collections import deque
from typing import AsyncGenerator
from models import Claim

logger = logging.getLogger(__name__)

# ── Groq Config ────────────────────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

# ── Entropy Thresholds ─────────────────────────────────────────────────────────
ENTROPY_THRESHOLD = 0.25
WINDOW_SIZE = 6
BURST_MIN_TOKENS = 2

# ── Sentence boundary ──────────────────────────────────────────────────────────
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


def compute_token_entropy(logprob: float) -> float:
    if logprob is None:
        return 0.0
    p = math.exp(max(logprob, -20.0))
    if p <= 0:
        return 0.0
    return round(-p * math.log(p + 1e-12), 6)


def smooth_entropy(window: deque) -> float:
    if not window:
        return 0.0
    return sum(window) / len(window)


def detect_claim_from_span(
    span_tokens: list,
    span_entropies: list,
    sentence: str,
    position: int
) -> Claim | None:
    claim_text = "".join(span_tokens).strip()
    if not claim_text:
        return None

    avg_entropy = sum(span_entropies) / len(span_entropies)

    if avg_entropy > 0.32:
        claim_type = "statistic"
    elif avg_entropy > 0.29:
        claim_type = "number"
    elif avg_entropy > 0.27:
        claim_type = "name"
    elif avg_entropy > 0.25:
        claim_type = "date"
    else:
        claim_type = "general"

    return Claim(
        text=claim_text,
        type=claim_type,
        position=position,
        sentence=sentence.strip()
    )


def extract_claims_from_entropy(
    tokens: list,
    entropies: list,
    sentence: str
) -> list:
    if not tokens or not entropies:
        return []

    claims = []
    in_span = False
    span_tokens = []
    span_entropies = []
    span_start = 0

    for i, (token, entropy) in enumerate(zip(tokens, entropies)):
        if entropy > ENTROPY_THRESHOLD:
            if not in_span:
                in_span = True
                span_start = i
                span_tokens = [token]
                span_entropies = [entropy]
            else:
                span_tokens.append(token)
                span_entropies.append(entropy)
        else:
            if in_span and len(span_tokens) >= BURST_MIN_TOKENS:
                claim = detect_claim_from_span(
                    span_tokens, span_entropies, sentence, span_start
                )
                if claim:
                    claims.append(claim)
            in_span = False
            span_tokens = []
            span_entropies = []

    if in_span and len(span_tokens) >= BURST_MIN_TOKENS:
        claim = detect_claim_from_span(
            span_tokens, span_entropies, sentence, span_start
        )
        if claim:
            claims.append(claim)

    return claims


async def _stream_groq(query: str) -> AsyncGenerator[tuple, None]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Get a free key at console.groq.com and add it to backend/.env"
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
                    "percentages, dates, and statistics."
                ),
            },
            {"role": "user", "content": query},
        ],
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 500,
        "logprobs": True,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            GROQ_API_URL,
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise httpx.HTTPStatusError(
                    f"Groq returned {response.status_code}: {body.decode(errors='ignore')[:300]}",
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
                    chunk = json.loads(data)
                    choice = chunk["choices"][0]
                    content = choice.get("delta", {}).get("content", "")
                    if not content:
                        continue

                    entropy = 0.0
                    logprobs_obj = choice.get("logprobs")
                    if logprobs_obj and logprobs_obj.get("content"):
                        lp_entry = logprobs_obj["content"][0]
                        lp_val = lp_entry.get("logprob")
                        if lp_val is not None:
                            entropy = compute_token_entropy(lp_val)

                    yield (content, entropy)

                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue


async def _stream_mock(query: str) -> AsyncGenerator[tuple, None]:
    mock_tokens = [
        ("Apple", 0.05), (" Inc", 0.04), (" reported", 0.08),
        (" revenue", 0.09), (" of", 0.06),
        (" $", 0.22), ("523", 0.34), (" billion", 0.31),
        (" in", 0.05), (" fiscal", 0.07), (" year", 0.06), (" 2022", 0.12),
        (".", 0.02), (" ", 0.01),
        ("Microsoft", 0.06), (" Azure", 0.07), (" revenue", 0.08),
        (" grew", 0.09),
        (" 45", 0.35), ("%", 0.33),
        (" year", 0.06), ("-over-", 0.05), ("year", 0.05),
        (" in", 0.05), (" Q4", 0.10), (" 2023", 0.11),
        (".", 0.02), (" ", 0.01),
        ("Tesla", 0.06), (" delivered", 0.08),
        (" 2.1", 0.34), (" million", 0.31),
        (" vehicles", 0.07), (" in", 0.05), (" 2023", 0.09),
        (".", 0.02), (" ", 0.01),
        ("The", 0.04), (" Federal", 0.06), (" Reserve", 0.06),
        (" held", 0.08), (" interest", 0.07), (" rates", 0.08),
        (" at", 0.06),
        (" 4", 0.33), (".", 0.30), ("75", 0.34), ("%", 0.32),
        (" in", 0.05), (" December", 0.08), (" 2023", 0.10),
        (".", 0.02),
    ]
    for token, entropy in mock_tokens:
        yield (token, entropy)
        await asyncio.sleep(0.04)


async def stream_and_detect(query: str) -> AsyncGenerator[tuple, None]:
    use_mock = os.getenv("USE_MOCK", "false").lower() == "true"
    text_buffer = ""
    token_buffer = []
    entropy_buffer = []
    entropy_window = deque(maxlen=WINDOW_SIZE)
    token_count = 0
    stream_fn = _stream_mock if use_mock else _stream_groq

    try:
        async for token, entropy in stream_fn(query):
            token_count += 1
            text_buffer += token
            token_buffer.append(token)
            entropy_buffer.append(entropy)
            entropy_window.append(entropy)

            yield (f"TOKEN:{token}", [])

            parts = SENTENCE_END.split(text_buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    char_count = 0
                    sentence_tokens = []
                    sentence_entropies = []

                    for tok, ent in zip(token_buffer, entropy_buffer):
                        if char_count >= len(sentence):
                            break
                        sentence_tokens.append(tok)
                        sentence_entropies.append(ent)
                        char_count += len(tok)

                    claims = extract_claims_from_entropy(
                        sentence_tokens, sentence_entropies, sentence
                    )

                    logger.debug(
                        f"Sentence: '{sentence[:60]}' | Claims: {len(claims)} | "
                        f"Peak H: {max(sentence_entropies, default=0):.3f}"
                    )
                    yield (sentence, claims)

                text_buffer = parts[-1]
                remaining_len = len(text_buffer)
                char_count = 0
                new_toks, new_ents = [], []

                for tok, ent in zip(reversed(token_buffer), reversed(entropy_buffer)):
                    if char_count >= remaining_len:
                        break
                    new_toks.insert(0, tok)
                    new_ents.insert(0, ent)
                    char_count += len(tok)

                token_buffer = new_toks
                entropy_buffer = new_ents

        if text_buffer.strip():
            claims = extract_claims_from_entropy(
                token_buffer, entropy_buffer, text_buffer.strip()
            )
            yield (text_buffer.strip(), claims)

    except ValueError as e:
        logger.error(f"Config error: {e}")
        yield (f"ERROR:{str(e)}", [])

    except httpx.HTTPStatusError as e:
        logger.error(f"Groq API error: {e}")
        yield (f"ERROR:{str(e)}", [])

    except httpx.ConnectError:
        logger.error("Cannot reach Groq API")
        yield ("ERROR:Cannot reach Groq API. Check internet.", [])

    except Exception as e:
        logger.error(f"Interceptor error: {e}", exc_info=True)
        yield (f"ERROR:{str(e)}", [])

    logger.info(f"Stream done | tokens: {token_count}")
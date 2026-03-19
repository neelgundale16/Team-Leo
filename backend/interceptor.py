"""
interceptor.py — Streaming Interceptor

Fallback-safe version for Groq models that do not support logprobs.
Streams tokens normally and performs lightweight sentence-level claim detection
without relying on unsupported API parameters.

This keeps the full pipeline working end-to-end for the demo.
"""

import re
import json
import httpx
import asyncio
import logging
import os
from typing import AsyncGenerator
from models import Claim

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

NUMBER_PATTERN = re.compile(r'\$?\b\d+(?:\.\d+)?\s?(?:billion|million|%|percent)?\b', re.IGNORECASE)
DATE_PATTERN = re.compile(r'\b(?:Q[1-4]\s+\d{4}|FY\s?\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})\b', re.IGNORECASE)
NAME_PATTERN = re.compile(r'\b(?:Apple|Microsoft|Tesla|Amazon|Nvidia|JPMorgan|Goldman Sachs|Federal Reserve|AWS|Azure|S&P 500|US CPI)\b', re.IGNORECASE)


def detect_claims(sentence: str) -> list[Claim]:
    claims: list[Claim] = []

    for match in NUMBER_PATTERN.finditer(sentence):
        claims.append(
            Claim(
                text=match.group().strip(),
                type="number",
                position=match.start(),
                sentence=sentence.strip(),
            )
        )

    for match in DATE_PATTERN.finditer(sentence):
        claims.append(
            Claim(
                text=match.group().strip(),
                type="date",
                position=match.start(),
                sentence=sentence.strip(),
            )
        )

    for match in NAME_PATTERN.finditer(sentence):
        claims.append(
            Claim(
                text=match.group().strip(),
                type="name",
                position=match.start(),
                sentence=sentence.strip(),
            )
        )

    deduped = []
    seen = set()
    for claim in claims:
        key = (claim.text.lower(), claim.type, claim.position)
        if key not in seen:
            seen.add(key)
            deduped.append(claim)

    return deduped


async def _stream_groq(query: str) -> AsyncGenerator[str, None]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in backend/.env")

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
                    "economic indicators, and uploaded documents clearly."
                ),
            },
            {"role": "user", "content": query},
        ],
        "stream": True,
        "temperature": 0.3,
        "max_tokens": 400,
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
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue


async def _stream_mock(query: str) -> AsyncGenerator[str, None]:
    mock_text = (
        "Apple reported revenue of $523 billion in fiscal year 2022. "
        "Microsoft Azure grew 45% in Q4 2023. "
        "Tesla delivered 2.1 million vehicles in 2023."
    )
    for token in re.findall(r'\S+|\s+', mock_text):
        yield token
        await asyncio.sleep(0.03)


async def stream_and_detect(query: str) -> AsyncGenerator[tuple, None]:
    use_mock = os.getenv("USE_MOCK", "false").lower() == "true"
    text_buffer = ""
    token_count = 0
    stream_fn = _stream_mock if use_mock else _stream_groq

    try:
        async for token in stream_fn(query):
            token_count += 1
            text_buffer += token

            yield (f"TOKEN:{token}", [])

            parts = SENTENCE_END.split(text_buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    claims = detect_claims(sentence)
                    yield (sentence, claims)

                text_buffer = parts[-1]

        if text_buffer.strip():
            claims = detect_claims(text_buffer.strip())
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
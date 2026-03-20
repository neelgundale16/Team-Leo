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

OLLAMA_API_URL = "http://localhost:11434/v1/chat/completions"
OLLAMA_MODEL = "llama3"

ENTROPY_THRESHOLD = 0.08
WINDOW_SIZE = 6
BURST_MIN_TOKENS = 1

SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


def compute_token_entropy(logprob: float) -> float:
    if logprob is None:
        return 0.0
    p = math.exp(max(logprob, -20.0))
    if p <= 0:
        return 0.0
    return round(-p * math.log(p + 1e-12), 6)


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

    if avg_entropy > 0.20:
        claim_type = "statistic"
    elif avg_entropy > 0.16:
        claim_type = "number"
    elif avg_entropy > 0.12:
        claim_type = "name"
    elif avg_entropy > 0.08:
        claim_type = "date"
    else:
        claim_type = "general"

    return Claim(
        text=claim_text,
        type=claim_type,
        position=position,
        sentence=sentence.strip()
    )


def extract_claims_from_entropy(tokens: list, entropies: list, sentence: str) -> list:
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


async def _stream_ollama(query: str) -> AsyncGenerator[tuple, None]:
    # Ollama runs locally — no API key needed

    headers = {
        "Content-Type": "application/json",
    }

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a financial analysis assistant with deep expertise. "
                    "Always answer with specific numbers, dollar amounts, percentages, "
                    "dates, and statistics. Never say you don't have data — provide "
                    "your best analysis using concrete figures. Include revenue numbers, "
                    "growth rates, profit margins, and quarterly comparisons. "
                    "Be assertive and detailed in your response."
                )
            },
            {"role": "user", "content": query}
        ],
        "stream": True,
        "temperature": 0.9,
        "max_tokens": 800,
        "logprobs": True,
        "top_logprobs": 1
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            OLLAMA_API_URL,
            headers=headers,
            json=payload
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise httpx.HTTPStatusError(
                    f"Ollama returned {response.status_code}: {body.decode()[:500]}",
                    request=response.request,
                    response=response
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
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
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
        ("Apple", 0.05), (" reported", 0.06), (" revenue", 0.08), (" of", 0.05),
        (" $", 0.21), ("523", 0.34), (" billion", 0.31), (".", 0.02),
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
    stream_fn = _stream_mock if use_mock else _stream_ollama

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
                        f"Sentence: '{sentence[:60]}' | "
                        f"Claims: {len(claims)} | "
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
        logger.error(f"Ollama API error: {e}")
        yield (f"ERROR:{str(e)}", [])

    except httpx.ConnectError:
        logger.error("Cannot reach Ollama server")
        yield ("ERROR:Cannot reach Ollama. Run: ollama serve", [])

    except Exception as e:
        logger.error(f"Interceptor error: {e}", exc_info=True)
        yield (f"ERROR:{str(e)}", [])

    logger.info(f"Stream done | tokens: {token_count}")
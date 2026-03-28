"""
main.py — FastAPI entry point for Project Veracity v2.0
AI4Dev'26, PSG Tech Coimbatore

Wires: Gemini streamer → entropy detector → vault verifier → NLI sentinel → rewriter → SSE
Includes /evaluate endpoint for dual-model comparison.
Rate-limited for Gemini free tier (15 RPM).
"""

import os
import json
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s │ %(name)s │ %(message)s")
logger = logging.getLogger(__name__)

# ── Lazy imports ─────────────────────────────────────────────────────────────
try:
    from models import ChatRequest, SSEEvent, SessionStats, StreamToken
    from vault import vault, load_demo_financial_data
    from sentinel import sentinel
    from rewriter import rewriter
    from interceptor import stream_and_detect, generate_full_response
    from evaluator import build_model_eval, llm_judge_comparison
except ImportError as e:
    logger.error("Import error: %s — run: pip install -r requirements.txt", e)
    raise

# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Project Veracity v2.0 ...")
    try:
        vault.initialize()
        logger.info("✅ Vault initialised (%d docs)", vault.get_count())
        if vault.get_count() == 0:
            load_demo_financial_data(vault)
            logger.info("✅ Demo financial data loaded (%d docs)", vault.get_count())
        sentinel.initialize()
        logger.info("✅ Sentinel NLI model loaded")
        logger.info("🛡️  All systems go. Hallucination firewall is active.")
    except Exception as e:
        logger.error("Startup failed: %s", e)
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Project Veracity",
    description="Self-Healing Hallucination Firewall — AI4Dev'26, PSG Tech Coimbatore",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SSE helper ───────────────────────────────────────────────────────────────
def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'event_type': event_type, 'data': data})}\n\n"


def _build_system_prompt_with_context(query: str) -> str:
    """
    Build a system prompt that includes relevant vault context.
    This ensures the LLM generates responses grounded in uploaded documents.
    """
    context = vault.get_context_for_query(query, n=5)

    if context:
        return (
            "You are a knowledgeable assistant. Answer the user's question using the "
            "REFERENCE DOCUMENTS provided below as your primary source of information. "
            "Include specific numbers, dates, and facts from the documents. "
            "If the documents don't contain relevant information, answer based on your "
            "general knowledge but be clear about what is from documents vs general knowledge.\n\n"
            "REFERENCE DOCUMENTS:\n"
            f"{context}\n\n"
            "Answer the user's question precisely and concisely."
        )
    else:
        return (
            "You are a knowledgeable assistant. Answer the user's question with specific "
            "details, numbers, and facts. Be confident and precise in your response."
        )


# ── Core firewall pipeline ──────────────────────────────────────────────────
async def firewall_generator(query: str) -> AsyncGenerator[str, None]:
    try:
        stats = SessionStats()
        token_id = 0

        # Build context-aware system prompt from vault
        system_prompt = _build_system_prompt_with_context(query)
        logger.info(f"Starting firewall stream for query: {query[:50]}...")
        
        # Send an immediate connection keep-alive token to prevent Next.js proxy timeout
        yield _sse("token", {
            "id": "init",
            "text": "",
            "status": "streaming",
            "entropy": 0.0,
        })

        async for sentence, claims, entropies in stream_and_detect(query, system_prompt):

            # ── raw token passthrough
            if sentence.startswith("TOKEN:"):
                raw_text = sentence[6:]
                avg_ent = entropies[0] if entropies else 0.0
                yield _sse("token", {
                    "id": f"t{token_id}",
                    "text": raw_text,
                    "status": "streaming",
                    "entropy": round(avg_ent, 3),
                })
                token_id += 1
                continue

            stats.total_claims_detected += len(claims)

            if not claims:
                yield _sse("token", {
                    "id": f"s{token_id}",
                    "text": sentence + " ",
                    "status": "verified",
                    "entropy": 0.0,
                })
                token_id += 1
                continue

            # ── verify each claim against vault
            corrected_sentence = sentence
            sentence_was_corrected = False

            for claim in claims:
                if not sentinel.is_fact_seeking(claim.sentence):
                    stats.claims_skipped += 1
                    continue

                t0 = time.perf_counter()
                vault_result = vault.search(claim.text)

                if vault_result is None:
                    stats.claims_skipped += 1
                    continue

                stats.claims_verified += 1
                nli_result = sentinel.classify(claim.text, vault_result.matched_text)
                latency_ms = (time.perf_counter() - t0) * 1000

                if nli_result.is_hallucination:
                    stats.hallucinations_found += 1
                    corrected = rewriter.rewrite(corrected_sentence, vault_result, nli_result)
                    correction_payload = rewriter.build_correction_payload(
                        corrected_sentence, corrected, vault_result.source_document
                    )
                    corrected_sentence = corrected
                    sentence_was_corrected = True
                    stats.corrections_made += 1

                    yield _sse("correction", {
                        "id": f"c{token_id}",
                        "original": correction_payload["original"],
                        "corrected": correction_payload["corrected"],
                        "source": correction_payload["source"],
                        "diff_ratio": correction_payload["diff_ratio"],
                        "claim": claim.text,
                        "vault_match": vault_result.matched_text[:120],
                        "nli_label": nli_result.label,
                        "nli_confidence": round(nli_result.confidence, 3),
                        "latency_ms": round(latency_ms, 1),
                    })

            # yield the (possibly corrected) sentence
            avg_ent = sum(entropies) / len(entropies) if entropies else 0.0
            yield _sse("token", {
                "id": f"s{token_id}",
                "text": corrected_sentence + " ",
                "status": "corrected" if sentence_was_corrected else "verified",
                "entropy": round(avg_ent, 3),
            })
            token_id += 1

        # ── stream final stats
        yield _sse("stats", stats.model_dump())
        yield _sse("done", {"message": "Stream complete", "stats": stats.model_dump()})

    except Exception as e:
        logger.exception("Pipeline error")
        yield _sse("error", {"message": str(e)})


# ── Evaluation pipeline (dual-model comparison) ──────────────────────────────
async def eval_generator(query: str, models: list[str]) -> AsyncGenerator[str, None]:
    """
    Run the same query through two Gemini models, score each, compare.
    Yields SSE events: eval_start → eval_progress → eval_complete
    """
    try:
        system_prompt = _build_system_prompt_with_context(query)

        yield _sse("eval_start", {
            "query": query,
            "models": models,
            "message": f"Evaluating {len(models)} models..."
        })

        eval_results = []

        for i, model_name in enumerate(models):
            yield _sse("eval_progress", {
                "model": model_name,
                "step": f"Generating response from {model_name}...",
                "index": i,
                "total": len(models),
            })

            try:
                t0 = time.perf_counter()
                response_text, token_entropies = await generate_full_response(
                    query, system_prompt, model=model_name
                )
                gen_latency = (time.perf_counter() - t0) * 1000

                # Run firewall verification on the response
                corrections_applied = 0
                total_claims = 0
                vault_matches = 0
                corrected_response = response_text

                # Split response into sentences and verify each
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response_text) if s.strip()]
                for sent in sentences:
                    if not sentinel.is_fact_seeking(sent):
                        continue
                    # Extract claims from the sentence
                    from interceptor import _detect_claims
                    sent_claims = _detect_claims(sent, [1.5] * len(sent.split()))
                    total_claims += len(sent_claims)

                    for claim in sent_claims:
                        vault_result = vault.search(claim.text)
                        if vault_result is None:
                            continue
                        vault_matches += 1
                        nli_result = sentinel.classify(claim.text, vault_result.matched_text)
                        if nli_result.is_hallucination:
                            corrected = rewriter.rewrite(corrected_response, vault_result, nli_result)
                            corrected_response = corrected
                            corrections_applied += 1

                # Build evaluation result
                eval_result = build_model_eval(
                    model_id=model_name,
                    model_label=model_name.replace("gemini-", "Gemini ").replace("-", " ").title(),
                    response_text=response_text,
                    token_entropies=token_entropies,
                    corrections_applied=corrections_applied,
                    total_claims=total_claims,
                    vault_matches=vault_matches,
                    corrected_response=corrected_response if corrections_applied > 0 else None,
                    latency_ms=gen_latency,
                    query=query,
                )
                eval_results.append(eval_result)

                yield _sse("eval_progress", {
                    "model": model_name,
                    "step": f"{model_name} complete — score: {eval_result.overall_score:.2f}",
                    "index": i,
                    "total": len(models),
                    "score": eval_result.overall_score,
                })

            except Exception as e:
                logger.error("Eval error for %s: %s", model_name, e)
                yield _sse("eval_progress", {
                    "model": model_name,
                    "step": f"Error: {str(e)[:100]}",
                    "index": i,
                    "total": len(models),
                    "error": str(e),
                })

        if len(eval_results) >= 2:
            # LLM-as-judge comparison
            try:
                winner, verdict, rationale = await llm_judge_comparison(
                    query=query,
                    response_a=eval_results[0].response_text,
                    model_a=eval_results[0].model_id,
                    response_b=eval_results[1].response_text,
                    model_b=eval_results[1].model_id,
                    scores_a=eval_results[0].overall_score,
                    scores_b=eval_results[1].overall_score,
                )
            except Exception as e:
                logger.warning("Judge failed: %s", e)
                winner = max(eval_results, key=lambda r: r.overall_score).model_id
                verdict = f"Winner by score: {winner}"
                rationale = "LLM judge unavailable — winner determined by score"

            # Build dimension winners
            dimension_winner = {}
            if len(eval_results) >= 2:
                for dim_name in eval_results[0].dimensions:
                    if dim_name in eval_results[1].dimensions:
                        if eval_results[0].dimensions[dim_name].score >= eval_results[1].dimensions[dim_name].score:
                            dimension_winner[dim_name] = eval_results[0].model_id
                        else:
                            dimension_winner[dim_name] = eval_results[1].model_id

            yield _sse("eval_complete", {
                "query": query,
                "models": [r.model_dump() for r in eval_results],
                "winner": winner,
                "verdict": verdict,
                "rationale": rationale,
                "dimension_winner": dimension_winner,
            })
        elif len(eval_results) == 1:
            yield _sse("eval_complete", {
                "query": query,
                "models": [r.model_dump() for r in eval_results],
                "winner": eval_results[0].model_id,
                "verdict": f"Only one model responded: {eval_results[0].model_id}",
                "rationale": "Single model evaluation",
                "dimension_winner": {},
            })
        else:
            yield _sse("error", {"message": "No models produced results"})

    except Exception as e:
        logger.exception("Evaluation suite failure")
        yield _sse("error", {"message": f"Evaluation system error: {str(e)}"})



# We need re for sentence splitting in eval
import re


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    """Main SSE endpoint — query → stream hallucination-corrected response."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    return StreamingResponse(
        firewall_generator(request.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.post("/evaluate")
async def evaluate(request: ChatRequest):
    """
    Evaluation endpoint — run query through multiple Gemini models,
    score each on 4 dimensions, compare via LLM-as-judge.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    models = request.models or ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

    return StreamingResponse(
        eval_generator(request.query, models),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/health")
async def health():
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    api_key_set  = bool(os.getenv("GEMINI_API_KEY", ""))
    return {
        "status": "ok",
        "llm_provider": "Google Gemini",
        "llm_model": gemini_model,
        "api_key_configured": api_key_set,
        "vault_documents": vault.get_count(),
        "hackathon": "AI4Dev'26, PSG Tech Coimbatore",
    }


@app.get("/vault/count")
async def vault_count():
    return {"count": vault.get_count()}


@app.post("/vault/add")
async def vault_add(payload: dict):
    """Add a single text fact to the vault."""
    text   = payload.get("text", "").strip()
    source = payload.get("source", "manual_entry")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    vault.add_document(text, source)
    return {"status": "added", "vault_count": vault.get_count()}


@app.post("/vault/upload")
async def vault_upload(file: UploadFile = File(...)):
    """
    Upload a PDF or text file and chunk it into the vault.
    Supports .pdf and .txt files.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = file.filename.lower()
    content  = await file.read()

    if filename.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            full_text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="pypdf not installed — run: pip install pypdf"
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF parse error: {e}")

    elif filename.endswith(".txt"):
        full_text = content.decode("utf-8", errors="ignore")

    else:
        raise HTTPException(
            status_code=415,
            detail="Only .pdf and .txt files are supported"
        )

    if not full_text.strip():
        raise HTTPException(status_code=422, detail="File appears to be empty or unreadable")

    # chunk into ~300-word segments
    words   = full_text.split()
    chunk_size = 300
    chunks  = [
        " ".join(words[i : i + chunk_size])
        for i in range(0, len(words), chunk_size)
    ]

    vault.add_documents_bulk(chunks, file.filename)
    logger.info("Uploaded %s → %d chunks added to vault", file.filename, len(chunks))

    return {
        "status": "success",
        "filename": file.filename,
        "chunks_added": len(chunks),
        "vault_total": vault.get_count(),
    }


@app.delete("/vault/clear")
async def vault_clear():
    vault.clear_vault()
    load_demo_financial_data(vault)
    return {"status": "cleared and reloaded", "vault_count": vault.get_count()}


# ── Dev entry ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
# Project Veracity

## Self-Healing Hallucination Firewall

Project Veracity is a real-time hallucination detection and correction system designed for large language models. It acts as a middleware firewall between the language model and the user, intercepting streaming responses token-by-token, identifying uncertain factual claims using entropy-based uncertainty estimation, verifying them against a trusted knowledge vault, and correcting hallucinations before they reach the user interface.

The system preserves the natural streaming experience while ensuring higher factual reliability in generated responses.

---

# Features

- Real-time token streaming
- Entropy-based hallucination detection
- Semantic claim verification
- Automatic hallucination correction
- Retrieval-augmented fact validation
- Live correction visualization
- Source-grounded response rewriting
- Streaming-safe verification pipeline
- Document upload support for custom knowledge grounding

---

# How It Works

Project Veracity operates as a multi-stage verification pipeline:

```text
User Query
    |
LLM Streaming Response
    |
Interceptor
    ├─ Captures tokens in real time
    ├─ Computes entropy from token probabilities
    └─ Detects uncertain factual spans
    |
Sentinel
    └─ Filters factual vs non-factual statements
    |
Vault
    └─ Performs semantic similarity search against verified data
    |
Rewriter
    └─ Replaces hallucinated claims with verified facts
    |
Frontend
    └─ Streams corrected response with live highlighting
```

---

# Entropy-Based Claim Detection

Instead of relying on hardcoded patterns or regular expressions, Project Veracity uses token-level uncertainty estimation.

For each generated token:

```text
H(t) = -Σ( pᵢ log pᵢ )
```

Where:

- `pᵢ` represents candidate token probabilities
- `H(t)` represents entropy at token position `t`

Higher entropy indicates the model is uncertain about its next prediction. Consecutive high-entropy spans are treated as potential factual claims requiring verification.

This allows the system to dynamically detect uncertain outputs across:

- numbers
- dates
- statistics
- entities
- financial values
- percentages
- structured factual claims

without domain-specific hardcoding.

---

# Architecture Components

## Interceptor

Streams LLM output in real time and computes entropy from token probabilities.

## Sentinel

Natural Language Inference (NLI) classifier that determines whether a sentence contains factual content worth verifying.

## Vault

Semantic retrieval engine powered by vector embeddings and similarity search for ground-truth validation.

## Rewriter

Correction engine that replaces hallucinated claims with verified factual information.

## Frontend

Interactive streaming interface that visualizes corrections and verification status in real time.

---

# Tech Stack

## Backend

- Python
- FastAPI
- asyncio
- uvicorn

## Frontend

- Next.js 14
- React 18
- TypeScript
- Tailwind CSS

## Machine Learning

- HuggingFace Transformers
- sentence-transformers
- cross-encoder NLI models

## Vector Database

- ChromaDB

## LLM Integration

- OpenAI-compatible streaming APIs
- Token log probability support

---

# Performance

| Pipeline Stage | Typical Latency |
|---|---|
| Token entropy computation | < 1ms |
| NLI classification | < 15ms |
| Semantic retrieval | < 100ms |
| Correction rewrite | < 20ms |
| End-to-end verification | < 200ms |

The system skips non-factual conversational text automatically, reducing unnecessary verification overhead.

---

# Project Structure

```text
backend/
│
├── interceptor.py
├── sentinel.py
├── vault.py
├── rewriter.py
├── evaluator.py
├── models.py
├── main.py
└── requirements.txt

frontend/veracity-ui/
│
├── src/app/
├── src/components/
├── src/types/
└── public/
```

---

# Setup Instructions

## Requirements

- Python 3.10+
- Node.js 18+
- API key for an LLM provider supporting streaming and token log probabilities

---

# Backend Setup

```bash
cd backend

python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file inside `backend/`:

```env
OPENAI_API_KEY=your_api_key_here
USE_MOCK=false
```

Start backend server:

```bash
uvicorn main:app --reload --port 8000
```

---

# Frontend Setup

```bash
cd frontend/veracity-ui

npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

---

# Mock Mode

To test the pipeline without external API calls:

```env
USE_MOCK=true
```

Mock mode generates synthetic hallucinations and entropy spikes to demonstrate the full verification and correction workflow.

---

# Supported Capabilities

- Financial fact verification
- Statistical claim correction
- Document-grounded retrieval
- Real-time response auditing
- Streaming-safe correction
- Semantic contradiction detection
- Dynamic knowledge vault updates

---

# Future Improvements

- Multi-document grounding
- Adaptive entropy calibration per model
- Persistent correction memory
- Enterprise audit logs
- Knowledge graph integration
- Medical and legal domain verification
- Visual entropy heatmaps
- Multi-agent verification pipelines

---


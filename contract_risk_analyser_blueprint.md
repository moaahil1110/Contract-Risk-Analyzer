# Contract Risk Analyser — Full Project Blueprint
> Built for: Aahil | BTech CSE, PES University | Portfolio Project for Placements

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [System Architecture](#3-system-architecture)
4. [Repository Structure](#4-repository-structure)
5. [Component Deep Dive](#5-component-deep-dive)
6. [Database Schema](#6-database-schema)
7. [API Endpoints](#7-api-endpoints)
8. [LLM Prompt Design](#8-llm-prompt-design)
9. [Frontend UI Screens](#9-frontend-ui-screens)
10. [6-Week Build Plan](#10-6-week-build-plan)
11. [Deployment Guide](#12-deployment-guide)
12. [Portfolio Packaging](#13-portfolio-packaging)
13. [Interview Prep](#14-interview-prep)

---

## 1. Project Overview

### Problem
Legal contracts are dense, jargon-heavy documents. Startups, freelancers, and SMEs sign NDAs, employment agreements, and vendor contracts without understanding the risks buried inside — because hiring a lawyer costs ₹5,000–₹20,000 per contract review.

### Solution
A web app where any user uploads a contract PDF → the system:
- Extracts and segments every clause
- Compares each clause against legal benchmarks using RAG
- Scores each clause: 🔴 High Risk / 🟡 Medium Risk / 🟢 Low Risk
- Explains the risk in plain English (no legal jargon)
- Suggests a safer alternative clause
- Generates an overall Contract Health Score (0–100)
- Exports a downloadable risk report

### Target Users
- Startup founders reviewing investor agreements
- Freelancers signing client contracts
- HR managers reviewing employment contracts
- Small businesses signing vendor/supplier agreements

### Why This Is a Real Industry Problem
- LegalTech startups like SpotDraft, Leegality, and Ironclad are valued at $100M+ solving this exact problem for enterprises
- The SME and individual market is completely underserved
- Every engineering company, every startup Aahil interviews at has signed dozens of contracts — the interviewer *personally* relates to this problem

---

## 2. Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | React + TailwindCSS + shadcn/ui | Fast UI development, clean components |
| Backend | FastAPI (Python) | Async support, auto docs, fast |
| PDF Parsing | PyMuPDF (fitz) + Tesseract OCR | Best Python PDF library, handles scanned docs |
| RAG Engine | LangChain + ChromaDB | Standard RAG stack, well documented |
| LLM | Claude API (claude-sonnet) | Best instruction-following for structured JSON |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Free, fast, runs locally |
| Database | Supabase (PostgreSQL) | Free tier, built-in auth, easy SDK |
| Auth | Supabase Auth | Email/password, easy to integrate |
| PDF Export | WeasyPrint (backend) | Generate styled PDF reports |
| Deployment | Railway (backend) + Vercel (frontend) | Both free tier, easy CI/CD |
| Version Control | GitHub | Portfolio visibility |

### Cost at Launch: ₹0
All services above have free tiers sufficient for a portfolio project with light usage.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vercel)                        │
│                    React + TailwindCSS                          │
│         Upload UI | Results Dashboard | Report Export           │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS REST API
┌───────────────────────────▼─────────────────────────────────────┐
│                      BACKEND (Railway)                          │
│                         FastAPI                                 │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────────────┐  │
│  │ PDF Parser  │→ │   Clause    │→ │     RAG + LLM Engine   │  │
│  │  PyMuPDF   │  │  Splitter   │  │  LangChain + ChromaDB  │  │
│  │ + Tesseract │  │             │  │  + Claude API          │  │
│  └─────────────┘  └─────────────┘  └────────────────────────┘  │
│                                              │                  │
│                              ┌───────────────▼──────────────┐  │
│                              │     Scoring & Aggregation    │  │
│                              │  Clause scores → Health Score│  │
│                              └───────────────┬──────────────┘  │
└──────────────────────────────────────────────┼─────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────┐
                    │                          │              │
          ┌─────────▼──────┐      ┌────────────▼──────┐      │
          │   Supabase DB  │      │   ChromaDB        │      │
          │  (PostgreSQL)  │      │ (Vector Store)    │      │
          │  Users         │      │ Benchmark clauses │      │
          │  Contracts     │      │ embeddings        │      │
          │  Clauses       │      └───────────────────┘      │
          │  Alerts        │                                  │
          └────────────────┘                                  │
```

### Data Flow (Step by Step)
1. User uploads PDF via React frontend
2. FastAPI `/upload` endpoint receives file
3. PyMuPDF extracts raw text; Tesseract OCR fallback for scanned PDFs
4. Clause Splitter segments text into individual clauses
5. For each clause: LangChain retrieves top-3 similar benchmark clauses from ChromaDB
6. Claude API receives clause + benchmarks → returns structured JSON risk analysis
7. All clause results aggregated into overall health score
8. Results stored in Supabase
9. Frontend polls `/analyse/{doc_id}` and renders results
10. User can export PDF report via `/export/{doc_id}`

---

## 4. Repository Structure

```
contract-risk-analyser/
│
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── upload.py          # POST /upload
│   │   │   ├── analyse.py         # GET /analyse/{doc_id}
│   │   │   ├── history.py         # GET /history
│   │   │   └── export.py          # GET /export/{doc_id}
│   │   └── middleware/
│   │       └── auth.py            # Supabase auth middleware
│   │
│   ├── pipeline/
│   │   ├── pdf_parser.py          # PyMuPDF + Tesseract
│   │   ├── clause_splitter.py     # Regex + LLM hybrid
│   │   ├── rag_engine.py          # LangChain + ChromaDB
│   │   ├── llm_analyser.py        # Claude API calls
│   │   └── scorer.py              # Health score aggregation
│   │
│   ├── models/
│   │   ├── contract.py            # Pydantic models
│   │   └── clause.py
│   │
│   ├── db/
│   │   ├── supabase_client.py
│   │   └── queries.py
│   │
│   └── benchmarks/                # Legal benchmark clause library
│       ├── nda_benchmarks.json
│       ├── employment_benchmarks.json
│       └── vendor_benchmarks.json
│
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx      # Upload + history
│   │   │   └── Results.jsx        # Clause-by-clause results
│   │   ├── components/
│   │   │   ├── UploadZone.jsx
│   │   │   ├── ClauseCard.jsx
│   │   │   ├── HealthMeter.jsx
│   │   │   └── RiskBadge.jsx
│   │   └── lib/
│   │       ├── api.js             # API call functions
│   │       └── supabase.js        # Supabase client
│   └── public/
│
├── notebooks/
│   └── benchmark_builder.ipynb    # Build ChromaDB from benchmark clauses
│
└── README.md
```

---

## 5. Component Deep Dive

### 5.1 PDF Parser (`pipeline/pdf_parser.py`)

```python
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

def extract_text_from_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    full_text = ""
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        
        # If page has no text (scanned PDF), use OCR
        if not text.strip():
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))
            text = pytesseract.image_to_string(img)
        
        full_text += text + "\n"
    
    return full_text.strip()
```

### 5.2 Clause Splitter (`pipeline/clause_splitter.py`)

Two-stage approach:

**Stage 1 — Regex (fast, handles well-formatted contracts):**
```python
import re

def split_clauses_regex(text: str) -> list[str]:
    # Match numbered clauses: "1.", "1.1", "Article 1", "Section 1", "CLAUSE 1"
    pattern = r'(?=(?:Section|Article|Clause|\d+\.)\s+\w)'
    clauses = re.split(pattern, text, flags=re.IGNORECASE)
    return [c.strip() for c in clauses if len(c.strip()) > 50]
```

**Stage 2 — LLM fallback (for messy or narrative-style contracts):**
```python
async def split_clauses_llm(text: str) -> list[str]:
    prompt = f"""
    The following is a legal contract. Extract each distinct clause or provision 
    as a separate item. Return a JSON array of strings, each string being one clause.
    Only return the JSON array, nothing else.
    
    CONTRACT:
    {text[:8000]}  # Limit to avoid token overflow
    
    Return format: ["clause 1 text", "clause 2 text", ...]
    """
    # Call Claude API, parse JSON response
    ...
```

### 5.3 RAG Engine (`pipeline/rag_engine.py`)

**Building the benchmark vector store (run once):**
```python
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
import json

def build_benchmark_store():
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    
    # Load all benchmark clauses
    benchmarks = []
    for file in ["nda_benchmarks.json", "employment_benchmarks.json", "vendor_benchmarks.json"]:
        with open(f"benchmarks/{file}") as f:
            data = json.load(f)
            benchmarks.extend(data["clauses"])
    
    # texts = clause text, metadatas = type, risk_notes, standard_version
    texts = [b["text"] for b in benchmarks]
    metadatas = [{"type": b["type"], "risk_notes": b["risk_notes"]} for b in benchmarks]
    
    vectorstore = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        persist_directory="./chroma_db"
    )
    vectorstore.persist()
```

**Querying at runtime:**
```python
def retrieve_benchmarks(clause_text: str, k: int = 3) -> list[dict]:
    vectorstore = Chroma(
        persist_directory="./chroma_db",
        embedding_function=embeddings
    )
    results = vectorstore.similarity_search_with_score(clause_text, k=k)
    return [
        {"text": doc.page_content, "metadata": doc.metadata, "score": score}
        for doc, score in results
    ]
```

### 5.4 LLM Analyser (`pipeline/llm_analyser.py`)

```python
import anthropic
import json

client = anthropic.Anthropic()

async def analyse_clause(
    clause_text: str, 
    benchmarks: list[dict],
    contract_type: str
) -> dict:
    
    benchmark_text = "\n\n".join([
        f"Benchmark {i+1}:\n{b['text']}\nNotes: {b['metadata']['risk_notes']}"
        for i, b in enumerate(benchmarks)
    ])
    
    prompt = f"""You are an expert contract risk analyst. Analyse the following contract clause.

CONTRACT TYPE: {contract_type}

CLAUSE TO ANALYSE:
{clause_text}

STANDARD BENCHMARK CLAUSES FOR REFERENCE:
{benchmark_text}

Analyse the clause and return ONLY a valid JSON object with this exact structure:
{{
  "clause_title": "Short descriptive title for this clause",
  "risk_level": "high" | "medium" | "low",
  "risk_score": <integer 0-100>,
  "risk_reason": "Clear explanation of what makes this risky, in 2-3 sentences. No legal jargon.",
  "plain_english": "What this clause actually means for the person signing it, in simple terms.",
  "key_concerns": ["concern 1", "concern 2", "concern 3"],
  "suggested_fix": "A safer alternative version of this clause, or specific changes to request."
}}

Return only the JSON object. No preamble, no explanation outside the JSON."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    response_text = message.content[0].text
    return json.loads(response_text)
```

### 5.5 Health Score Aggregator (`pipeline/scorer.py`)

```python
def calculate_health_score(clause_analyses: list[dict]) -> dict:
    if not clause_analyses:
        return {"score": 0, "grade": "F", "summary": "No clauses analysed"}
    
    # Weighted scoring: high=0, medium=60, low=100
    score_map = {"high": 0, "medium": 60, "low": 100}
    weight_map = {"high": 3, "medium": 1.5, "low": 1}  # High risk clauses penalise more
    
    total_weighted_score = 0
    total_weight = 0
    
    risk_counts = {"high": 0, "medium": 0, "low": 0}
    
    for clause in clause_analyses:
        risk = clause["risk_level"]
        score = score_map[risk]
        weight = weight_map[risk]
        total_weighted_score += score * weight
        total_weight += weight
        risk_counts[risk] += 1
    
    final_score = int(total_weighted_score / total_weight)
    
    if final_score >= 80:
        grade, label = "A", "Low Risk"
    elif final_score >= 60:
        grade, label = "B", "Moderate Risk"
    elif final_score >= 40:
        grade, label = "C", "High Risk"
    else:
        grade, label = "D", "Critical Risk"
    
    return {
        "score": final_score,
        "grade": grade,
        "label": label,
        "risk_counts": risk_counts,
        "total_clauses": len(clause_analyses)
    }
```

---

## 6. Database Schema

```sql
-- Users (managed by Supabase Auth, extended here)
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    email TEXT NOT NULL,
    analyses_used INTEGER DEFAULT 0,
    plan TEXT DEFAULT 'free',  -- 'free' | 'paid'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Contracts
CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id),
    filename TEXT NOT NULL,
    contract_type TEXT,          -- 'nda' | 'employment' | 'vendor' | 'other'
    status TEXT DEFAULT 'processing',  -- 'processing' | 'complete' | 'failed'
    health_score INTEGER,
    health_grade TEXT,
    health_label TEXT,
    total_clauses INTEGER,
    high_risk_count INTEGER DEFAULT 0,
    medium_risk_count INTEGER DEFAULT 0,
    low_risk_count INTEGER DEFAULT 0,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Individual Clause Analyses
CREATE TABLE clause_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id UUID REFERENCES contracts(id) ON DELETE CASCADE,
    clause_index INTEGER,         -- Order in document
    clause_title TEXT,
    original_text TEXT NOT NULL,
    risk_level TEXT NOT NULL,     -- 'high' | 'medium' | 'low'
    risk_score INTEGER,
    risk_reason TEXT,
    plain_english TEXT,
    key_concerns JSONB,           -- Array of strings
    suggested_fix TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_contracts_user ON contracts(user_id);
CREATE INDEX idx_clauses_contract ON clause_analyses(contract_id);
CREATE INDEX idx_clauses_risk ON clause_analyses(risk_level);
```

---

## 7. API Endpoints

### POST `/upload`
Upload a PDF contract and trigger analysis.

**Request:** `multipart/form-data`
```
file: <PDF file>
contract_type: "nda" | "employment" | "vendor" | "other"
```

**Response:**
```json
{
  "contract_id": "uuid-here",
  "status": "processing",
  "message": "Analysis started. Poll /analyse/{contract_id} for results."
}
```

---

### GET `/analyse/{contract_id}`
Get full analysis results for a contract.

**Response:**
```json
{
  "contract_id": "uuid",
  "filename": "contract.pdf",
  "status": "complete",
  "health": {
    "score": 42,
    "grade": "C",
    "label": "High Risk",
    "risk_counts": { "high": 4, "medium": 3, "low": 6 },
    "total_clauses": 13
  },
  "clauses": [
    {
      "id": "uuid",
      "clause_index": 1,
      "clause_title": "IP Assignment",
      "original_text": "Employee assigns all IP...",
      "risk_level": "high",
      "risk_score": 12,
      "risk_reason": "This clause assigns all IP you create — even on personal time — to the employer.",
      "plain_english": "Anything you invent, write, or build while employed here belongs to the company.",
      "key_concerns": [
        "Covers IP created outside work hours",
        "No carve-out for prior personal projects",
        "No geographic limitation"
      ],
      "suggested_fix": "Add: 'excluding inventions developed entirely on Employee's own time without Company resources, unless directly related to Company's business.'"
    }
  ]
}
```

---

### GET `/history`
Get authenticated user's past contract analyses.

**Response:**
```json
{
  "contracts": [
    {
      "id": "uuid",
      "filename": "vendor_agreement.pdf",
      "contract_type": "vendor",
      "health_score": 67,
      "health_grade": "B",
      "uploaded_at": "2025-03-15T10:30:00Z",
      "high_risk_count": 2
    }
  ]
}
```

---

### GET `/export/{contract_id}`
Download a styled PDF risk report.

**Response:** `application/pdf` file download

---

## 8. LLM Prompt Design

### Contract Type Detection Prompt
Run this first on the full document to classify the contract:

```
Classify the following contract into one of these categories:
nda, employment, vendor, investment, freelance, lease, other

Return ONLY the category word, nothing else.

CONTRACT (first 2000 chars):
{text[:2000]}
```

### Clause Risk Analysis Prompt
(See Section 5.4 above for full prompt)

### Key Design Decisions
- **Structured JSON output:** Always request JSON — prevents hallucinated formats
- **No legal jargon rule:** Explicitly stated in prompt — otherwise LLM defaults to legalese
- **Benchmark grounding:** Providing reference clauses dramatically improves scoring consistency
- **Suggested fix requirement:** Forces the model to be constructive, not just critical — makes the product more useful

---

## 9. Frontend UI Screens

### Screen 1 — Login / Signup
- Clean centered card
- Email + password fields
- "Sign in with Google" (Supabase OAuth)
- No clutter

### Screen 2 — Dashboard (Home)
- Top: "Analyse a Contract" — large drag-and-drop upload zone
- Contract type selector (NDA / Employment / Vendor / Other)
- Below: Past analyses table with columns: Filename | Type | Health Score | Date | Actions
- Health score shown as coloured badge (🔴 < 50, 🟡 50–75, 🟢 > 75)

### Screen 3 — Results Page
**Header:**
- Contract filename + type
- Large circular health score gauge (animated, colour-coded)
- Summary stats: X High Risk | Y Medium Risk | Z Low Risk clauses

**Clause List (main content):**
- Each clause rendered as a card
- Card header: Clause title + Risk Badge (🔴/🟡/🟢)
- Collapsed by default, expandable
- Expanded view shows:
  - Original Text (grey background, monospace)
  - Plain English explanation (white background, readable font)
  - Key Concerns (bulleted list in red/orange)
  - Suggested Fix (green background, italic)
- Filter bar at top: "Show All | High Risk Only | Medium Risk Only"

**Sidebar (sticky):**
- Jump-to-clause navigation
- "Export Report" button (downloads PDF)
- "Analyse Another" button

### Screen 4 — Exported PDF Report
- Cover page: Contract name, date, health score
- Executive Summary: 1-paragraph plain English overview
- Clause-by-clause breakdown (same structure as UI)
- Branded footer

---

## 10. 6-Week Build Plan

### Week 1 — Foundation & PDF Pipeline
**Goal:** PDF in → structured clause array out

| Day | Task |
|---|---|
| 1 | Set up GitHub repo, FastAPI project structure, virtual environment |
| 2 | Implement PyMuPDF text extractor, test on 5 real contract PDFs |
| 3 | Add Tesseract OCR fallback for scanned PDFs |
| 4 | Build regex clause splitter, test on 3 contract types |
| 5 | Build LLM fallback clause splitter (for messy contracts) |
| 6–7 | Test pipeline end-to-end, output clean JSON clause arrays |

**✅ Checkpoint:** Upload 3 different contract types → get clean clause arrays from all 3

**Resources:**
- Download 10 free contract templates: [LawDepot](https://www.lawdepot.com), [Docracy](https://www.docracy.com)
- PyMuPDF docs: https://pymupdf.readthedocs.io

---

### Week 2 — Intelligence Layer (RAG + LLM)
**Goal:** Each clause gets a scored, explained risk analysis

| Day | Task |
|---|---|
| 1 | Manually curate 30–50 benchmark clauses across NDA/employment/vendor types |
| 2 | Build ChromaDB vector store from benchmarks using Jupyter notebook |
| 3 | Build LangChain retrieval pipeline — test retrieval quality |
| 4 | Write and test Claude API prompt — iterate until JSON output is consistent |
| 5 | Build health score aggregation logic |
| 6–7 | Run full pipeline on 3 complete contracts, evaluate quality manually |

**✅ Checkpoint:** Feed 1 full contract → get complete JSON risk report with clause-level scores

**Tip:** For benchmark clauses, use freely available contract templates from ISDA, SHRM (for employment), and standard NDA templates. Extract the "standard" version of common clauses as your benchmark library.

---

### Week 3 — Backend API + Database
**Goal:** Proper async API, persistent storage, auth

| Day | Task |
|---|---|
| 1 | Set up Supabase project — create tables per schema above |
| 2 | Implement Supabase Auth in FastAPI (JWT middleware) |
| 3 | Build `/upload` endpoint with background task processing |
| 4 | Build `/analyse/{id}` and `/history` endpoints |
| 5 | Add contract type auto-detection call |
| 6 | Postman test all endpoints, fix bugs |
| 7 | Add rate limiting (free tier: 5 analyses per user per day) |

**✅ Checkpoint:** Hit API via Postman with a real PDF → results appear in Supabase dashboard

---

### Week 4 — Frontend
**Goal:** Non-technical people can use it without guidance

| Day | Task |
|---|---|
| 1 | React + Vite setup, TailwindCSS, shadcn/ui install |
| 2 | Login/signup page with Supabase Auth |
| 3 | Dashboard page — upload zone + history table |
| 4 | Results page — health score gauge + clause cards (collapsed) |
| 5 | Results page — expandable clause detail (plain English + fix) |
| 6 | Filter bar (All / High / Medium), risk badges, responsive layout |
| 7 | Polish UI, test on mobile, fix layout issues |

**✅ Checkpoint:** Full browser flow works — upload PDF, see results, looks clean on both desktop and mobile

**Component libraries to use:**
- `shadcn/ui` — for cards, badges, buttons
- `recharts` — for the health score radial chart
- `react-dropzone` — for the PDF upload zone
- `react-pdf` — to preview the uploaded contract

---

### Week 5 — Polish, Edge Cases & Deployment
**Goal:** Production-ready, zero crashes, live URL

| Day | Task |
|---|---|
| 1 | Handle edge cases: image-only PDFs, very short docs, non-English contracts |
| 2 | Build PDF export (WeasyPrint — generate styled report from clause data) |
| 3 | Dockerise FastAPI backend |
| 4 | Deploy backend to Railway, set environment variables |
| 5 | Deploy frontend to Vercel, connect to Railway backend URL |
| 6 | End-to-end test on live deployment, fix any prod bugs |
| 7 | Share live URL with 3 non-technical people — watch them use it, note friction points |

**✅ Checkpoint:** Live URL works. PDF export works. Share with family — can they use it without help?

---

### Week 6 — Portfolio Packaging & Launch
**Goal:** Maximum recruiter and community visibility

| Day | Task |
|---|---|
| 1 | Record 5-min demo video (screen record + voiceover) |
| 2 | Write clean README with architecture diagram + demo GIF |
| 3 | Write blog post draft ("How I built a Contract Risk Analyser") |
| 4 | Publish blog on Dev.to or Hashnode |
| 5 | Draft and schedule LinkedIn launch post |
| 6 | Add Razorpay payment link (₹99 for 10 analyses — stretch goal) |
| 7 | Post on LinkedIn, share in relevant communities |

**✅ Checkpoint:** Live URL + GitHub + blog post + LinkedIn post all published

---

## 11. Deployment Guide

### Backend (Railway)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up

# Set environment variables in Railway dashboard:
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
CHROMA_PERSIST_PATH=/app/chroma_db
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install Tesseract for OCR
RUN apt-get update && apt-get install -y tesseract-ocr

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend (Vercel)
```bash
# Install Vercel CLI
npm install -g vercel

# In frontend directory
vercel

# Set environment variable in Vercel dashboard:
VITE_API_URL=https://your-railway-url.railway.app
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
```

---

## 12. Portfolio Packaging

### GitHub README Must-Haves
- [ ] Project description + problem statement (3 sentences)
- [ ] Architecture diagram (ASCII or image)
- [ ] Demo GIF (record with Loom or QuickTime, convert with ezgif.com)
- [ ] Tech stack badges (shields.io)
- [ ] Live demo link (prominent, top of README)
- [ ] Setup instructions (someone should be able to run it in 5 mins)
- [ ] Model/approach explanation
- [ ] Screenshots

### LinkedIn Launch Post Template
```
I spent 6 weeks building something I wish existed when I was reviewing my internship contract.

Most people sign legal contracts without really understanding what's in them.
Not because they're careless — but because legal language is designed to confuse.

So I built a Contract Risk Analyser:
→ Upload any contract PDF
→ AI reads every clause and scores it: 🔴 High / 🟡 Medium / 🟢 Low risk
→ Explains each risk in plain English
→ Suggests safer alternative language

Built with: FastAPI · LangChain · ChromaDB · Claude API · React

[Screenshot 1: Upload screen]
[Screenshot 2: Risk dashboard]
[Screenshot 3: Clause detail with suggested fix]

Live demo: [link]
GitHub: [link]

This is the kind of tool that could have saved me from signing away my side-project IP in an internship contract.

#GenAI #LegalTech #BuildInPublic #PESUniversity
```

### Blog Post Outline (Dev.to / Hashnode)
**Title:** "How I Built a Contract Risk Analyser Using RAG, LangChain, and Claude"

1. The Problem (personal story — why contracts are scary for non-lawyers)
2. The Solution Architecture (diagram + explanation)
3. The Hardest Part: Clause Segmentation (what I tried, what failed, what worked)
4. RAG vs. Pure LLM: Why benchmarks matter for consistency
5. Prompt Engineering for Structured Legal Analysis
6. What I'd Do Differently
7. What's Next (monetisation? multi-language support?)

---

## 13. Interview Prep

### Questions You'll Get — And How to Answer Them

**"Walk me through how this works technically."**
> "A user uploads a PDF contract. My backend extracts and segments the text into individual clauses using a hybrid regex and LLM approach. Each clause is then run through a RAG pipeline — I retrieve similar standard benchmark clauses from a vector database, then send the clause plus those benchmarks to Claude with a structured prompt. The model returns a JSON risk assessment — score, plain English explanation, and a suggested fix. All results are stored in Supabase and rendered in a React dashboard."

**"Why RAG? Why not just send the whole contract to the LLM?"**
> "Two reasons. First, grounding — without reference benchmarks, the LLM has no consistent standard to compare against. Risk scoring becomes subjective and inconsistent. RAG gives it an anchor. Second, accuracy — the retrieved benchmarks act as few-shot examples specific to each clause type, which dramatically improves the quality of risk reasoning compared to zero-shot analysis of the raw clause."

**"How did you evaluate whether the risk scoring is accurate?"**
> "I manually reviewed 50 clauses across 10 contracts and scored them myself before running them through the system. I then compared my scores to the model's outputs. I iterated on the prompt until agreement on high-risk clauses was above 85%. I also tested edge cases — extremely one-sided clauses, standard market clauses, and missing clauses — to make sure the model didn't hallucinate risks."

**"What would you do differently at production scale?"**
> "A few things. I'd fine-tune a smaller model on labelled contract clause data rather than relying purely on prompting — more consistent and cheaper at scale. I'd add a lawyer review layer for high-risk flagged clauses to create a human-in-the-loop product. I'd also build jurisdiction detection — Indian Contract Act has different implications than US common law or UK law, and the risk scoring should adapt."

**"Did anyone actually use it?"**
> *If yes:* "Yes — I got [X] signups after my LinkedIn post, including [notable type of user]. I even charged ₹99/analysis and got [Y] paying users, which validated that the problem is real."
> *If no paying users yet:* "I shared it with 5 startup founders in my network and got strong positive feedback — two of them said they'd pay for it. I'm planning to add a payment tier next."

---

## Quick Reference — Key Metrics to Target

| Metric | Target |
|---|---|
| PDF parsing success rate | > 95% on text PDFs |
| Clause extraction accuracy | > 90% (manually validated on 10 contracts) |
| Risk scoring consistency | > 85% agreement on high-risk clauses |
| API response time | < 30 seconds for a 10-page contract |
| Frontend Lighthouse score | > 85 |
| Uptime (Railway free tier) | > 95% |

---

*Built by Aahil | PES University BTech CSE 2025*
*Stack: FastAPI · LangChain · ChromaDB · Claude API · React · Supabase*

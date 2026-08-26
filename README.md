# AI-Powered Sports Engagement Content Agent (v7)

Generates 5 types of Instagram-ready sports content — MCQ, True/False, This-or-That
polls, Fill-in-the-Blank, and Guess-the-Number — grounded in web search (fresh facts)
and ChromaDB (stable historical facts), independently re-verified against a live
web search at generation time, with schema validation and semantic dedup/freshness
tracking across sessions.

## USP

Most quiz generators trust the LLM's first answer. This one doesn't — **every
single fact is independently re-verified against a live web search at
generation time**, not just retrieved once and assumed correct, and the
verification reason is visible on both the dashboard and the exported
Instagram card itself (✓ WEB-VERIFIED / ⚠ UNVERIFIED badge).

## What's new in v7

- **Weekly Content Calendar**: one click generates a full 7-day posting plan,
  rotating content types across the week (This-or-That to open/close for
  organic engagement, MCQ/T-F/Fill-blank midweek, Guess-the-Number as a
  change-of-pace) — directly targets the assignment's goal of "vary content
  strategy so followers don't get bored," instead of a flat list of quizzes.
- **Visible verification badge on the Instagram card itself** (not just the
  dashboard) — "✓ WEB-VERIFIED" or "⚠ UNVERIFIED" printed in the top corner
  of every exported PNG, making the grounding/anti-hallucination work a
  demoable, visible feature rather than an invisible backend check.
- **"Show me why" transparency expander** per item — reveals the retrieval
  source, the verification pass/fail, and the specific reason the web search
  did or didn't corroborate the fact.
- **Batch ZIP export** — download an entire batch or full week as Instagram
  cards in one ZIP file instead of clicking each item individually.

## What's new in v6

- **Fixed pre-marked answers**: the dashboard no longer shows the correct answer
  upfront. Each item now has a "Reveal Answer" button (This-or-That is exempt —
  it has no correct answer by design). Regenerating an item resets its reveal state.
- **Instagram post card generator** (`core/insta_card.py`): every item can be
  downloaded as a ready-to-post 1080x1080 PNG, styled per sport, with the
  content-type labeled (Quiz Time / True or False? / This or That? / etc.) —
  and critically, **the correct answer is never printed on the image**, matching
  how a real Instagram quiz/poll post works (viewers answer before finding out).

## What's new in v5 (web verification) and v4 (Groq)

- **Switched from Anthropic to Groq** for all generation (`core/generator.py` and
  `core/auto_seed.py`). Uses Groq's OpenAI-compatible endpoint via the `openai`
  Python package, default model `openai/gpt-oss-120b` (overridable via `GROQ_MODEL`
  in `.env`). No other logic changed — retrieval, dedup, schemas, templates, and
  the dashboard are untouched.

## What's new in v3

- **Fixed repeat-question bug**: dedup is now semantic (embedding cosine similarity),
  not exact-hash, and checks across ALL content types per sport — catches "same fact,
  reworded as a different question type" which v1/v2 missed entirely.
- **Fixed retrieval always returning the same top fact**: ChromaDB now samples
  randomly from a pool of 12 matches instead of always the top 4; every query also
  gets a randomized angle ("lesser-known record", "recent milestone", etc.).
- **Generation temperature raised to 0.9** so repeated calls don't converge on
  the same wording/fact.
- **Rebuilt dashboard**: tabbed layout (Current Batch / Recent History / Stats),
  platform-surface guidance per item (Story vs Feed vs Reel — per the assignment's
  requirement to match format to surface), a history tab so you can see exactly
  what the dedup system is checking against, and a stats tab with batch breakdown.

## Setup


```bash
cd sports_agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY and TAVILY_API_KEY
python seed_chroma.py  # one-time: seeds the vector DB with starter facts
rm -f data/history.db  # if upgrading from v1/v2: old dedup schema is incompatible
streamlit run app.py
```

Get a free Groq key at https://console.groq.com/keys (Google/GitHub login, no card needed).

Get a free Tavily key at https://tavily.com — it's built for RAG/agent search
and returns clean JSON, faster to integrate than raw search APIs.

## Architecture

```
User request (sport, difficulty, type[s], batch size)
        │
        ▼
  generate_batch() ── cycles through content types for mixed batches
        │
        ▼
  generate_item()
        │
        ├─► retrieve_context()  [core/retrieval.py]
        │     - This-or-That -> skip retrieval (opinion-based)
        │     - Guess-the-Number / Hard difficulty -> web search (Tavily)
        │     - else -> ChromaDB first; fall back to web search if <2 hits
        │
        ├─► fill type-specific prompt template  [templates/prompt_templates.py]
        │     one template per content type, each with its own JSON contract
        │
        ├─► call Claude (claude-sonnet-4-5)
        │
        ├─► parse JSON -> validate against Pydantic schema  [schemas/content_schemas.py]
        │     on failure: retry (up to 3x) with the validation error appended to the prompt
        │
        ├─► check dedup store (SQLite)  [core/dedup.py]
        │     on exact repeat: retry with "avoid this" instruction
        │
        └─► record + return validated item
```

## Why these design choices

- **Type-specific templates + schemas instead of one generic prompt**: each
  content type has structurally different output (2 options vs 4, a boolean vs
  a number), so a single prompt either over-constrains simple types or
  under-constrains complex ones. Separating them also makes each template easy
  to tune independently.
- **Routing heuristic (web vs ChromaDB)**: recent/volatile facts (records that
  change, "Hard" difficulty questions which tend to be more niche/recent) go to
  web search; everything else tries the vector DB first since it's cheaper and
  faster, falling back to web search if the KB doesn't have enough on that sport
  yet (cold-start problem — see Known Limitations).
- **SQLite dedup store**: persists across app restarts, unlike in-memory state,
  so "freshness across sessions" (a stated requirement) actually holds up.
- **Retry-with-error-injection**: rather than hard-failing on a schema
  violation, the validation error is fed back into the next prompt attempt,
  which meaningfully improves the LLM's ability to self-correct.

## Known Limitations / Next Steps

- **ChromaDB is seeded with a small starter set** (`seed_chroma.py`) — retrieval
  quality depends entirely on how much you expand it. This is manual curation,
  not automatic; a good next step is scraping structured stats pages per sport.
- **Source citation is currently "which retrieval call fed this," not
  claim-level attribution** — the LLM isn't asked to cite per-sentence. A
  stronger version would ask Claude to tag each explanation with which
  retrieved chunk supports it.
- **Dedup is exact-match only** (hash of the question text). Near-duplicate
  detection (same fact, reworded) would need embedding similarity instead of a
  hash — worth adding if repetition still shows up during testing.
- **Guess-the-Number tolerance** is currently left to the LLM's judgment with
  guidance in the prompt; consider a programmatic post-processing rule if you
  see unreasonable ranges in practice.
- **No caching layer yet** — every generation call hits Claude + (web search or
  ChromaDB). Fine for a demo; add a cache keyed on (sport, type, difficulty) if
  cost/latency becomes an issue at scale.

## Project Structure

```
sports_agent/
├── app.py                      # Streamlit dashboard
├── seed_chroma.py               # one-time ChromaDB seeding script
├── schemas/content_schemas.py   # Pydantic models, one per content type
├── templates/prompt_templates.py# one prompt template per content type
├── core/
│   ├── retrieval.py              # web search / ChromaDB routing
│   ├── dedup.py                  # SQLite freshness/dedup store
│   └── generator.py              # orchestration: retrieve -> prompt -> validate -> retry
└── data/                         # chroma_store/ + history.db (created at runtime)
```

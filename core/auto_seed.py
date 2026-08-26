"""
Auto fact harvester + verifier.

Instead of hand-typing facts into ChromaDB, this module:
  1. Runs several web searches per (sport, topic) to gather source material
  2. Asks Claude to extract atomic, checkable facts from that material
  3. Cross-checks each fact against a SECOND independent search
  4. Only stores facts that are corroborated by 2+ independent sources
  5. Tags each stored fact with a verified_at date + source URLs

This gives you a "verified" knowledge base instead of a hardcoded one, and lets
you re-run it periodically to catch outdated facts (e.g. a record that got broken).
"""

import json
import os
import time
from datetime import datetime, timezone

import chromadb
from chromadb.utils import embedding_functions

from core.retrieval import get_tavily, CHROMA_PATH, COLLECTION_NAME
from core.generator import get_client, MODEL, _strip_json_fences

# How many days before a stored fact is considered "stale" and re-verified
STALENESS_DAYS = 90

TOPICS_PER_SPORT = {
    "Cricket": ["all-time batting records", "all-time bowling records", "World Cup winners history", "fastest deliveries"],
    "Football": ["all-time top scorers international", "Ballon d'Or winners", "World Cup winners history", "transfer records"],
    "Tennis": ["Grand Slam titles record", "world number 1 history", "longest match record"],
    "Badminton": ["Olympic medalists", "world championship winners", "rules and scoring"],
    "Basketball": ["NBA all-time scoring leaders", "NBA championship winners", "MVP award history"],
}

EXTRACTION_PROMPT = """Below are web search results about "{topic}" in {sport}.

Extract 5-8 DISCRETE, ATOMIC, CHECKABLE facts (one specific claim each — a record,
a name+number, a date, a rule). Do not combine multiple claims into one fact.
Only include facts that are explicitly stated in the text below, do not infer or guess.

Search results:
{context}

Return ONLY a JSON array, no markdown, no preamble:
[
  {{"fact": "...", "confidence_hint": "high|medium|low"}}
]
"""

VERIFY_PROMPT = """Claim to verify: "{fact}"

Independent search results (from a SEPARATE search than the one that produced this claim):
{context}

Does this second, independent set of search results corroborate the claim above?
Return ONLY valid JSON, no markdown:
{{"corroborated": true or false, "reason": "1 sentence"}}
"""


def _call_claude_json(prompt: str):
    client = get_client()
    resp = client.chat.completions.create(
        model=MODEL, max_tokens=1000, messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.choices[0].message.content.strip()
    return json.loads(_strip_json_fences(raw))


def _search_context(query: str, max_results: int = 5):
    tavily = get_tavily()
    results = tavily.search(query=query, max_results=max_results, search_depth="advanced")
    chunks, urls = [], []
    for r in results.get("results", []):
        chunks.append(f"- {r.get('title','')}: {r.get('content','')}")
        urls.append(r.get("url", ""))
    return "\n".join(chunks), urls


def harvest_and_verify_topic(sport: str, topic: str) -> list[dict]:
    """
    Returns a list of verified fact dicts:
      {"text": str, "sport": str, "source_urls": [...], "verified_at": iso_str}
    Only facts corroborated by a second, independent search are included.
    """
    primary_query = f"{sport} {topic}"
    primary_context, primary_urls = _search_context(primary_query)

    if not primary_context.strip():
        return []

    candidates = _call_claude_json(
        EXTRACTION_PROMPT.format(topic=topic, sport=sport, context=primary_context)
    )

    verified = []
    for c in candidates:
        fact_text = c.get("fact", "").strip()
        if not fact_text:
            continue

        # independent second search, phrased around the specific fact (not the broad topic)
        verify_query = fact_text
        secondary_context, secondary_urls = _search_context(verify_query, max_results=3)
        if not secondary_context.strip():
            continue  # can't verify independently -> skip rather than guess

        verdict = _call_claude_json(
            VERIFY_PROMPT.format(fact=fact_text, context=secondary_context)
        )

        if verdict.get("corroborated") is True:
            verified.append({
                "text": fact_text,
                "sport": sport,
                "source_urls": list(set(primary_urls + secondary_urls))[:5],
                "verified_at": datetime.now(timezone.utc).isoformat(),
            })

        time.sleep(0.3)  # be polite to the search API

    return verified


def store_facts(facts: list[dict]):
    if not facts:
        return
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)

    ids = [f"auto_{hash(f['text'])}" for f in facts]
    documents = [f["text"] for f in facts]
    metadatas = [
        {
            "sport": f["sport"],
            "verified_at": f["verified_at"],
            "source_urls": ",".join(f["source_urls"]),
        }
        for f in facts
    ]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def is_stale(verified_at_iso: str) -> bool:
    verified_at = datetime.fromisoformat(verified_at_iso)
    age_days = (datetime.now(timezone.utc) - verified_at).days
    return age_days > STALENESS_DAYS


def run_full_harvest(sports: list[str] = None):
    """
    Entry point: harvests + verifies facts for every topic of every sport,
    and stores only the corroborated ones. Prints a summary as it goes.
    """
    sports = sports or list(TOPICS_PER_SPORT.keys())
    total_stored = 0

    for sport in sports:
        for topic in TOPICS_PER_SPORT.get(sport, []):
            print(f"[harvest] {sport} — {topic}...")
            facts = harvest_and_verify_topic(sport, topic)
            store_facts(facts)
            print(f"  -> {len(facts)} verified fact(s) stored")
            total_stored += len(facts)

    print(f"\nDone. {total_stored} verified facts stored across {len(sports)} sport(s).")


if __name__ == "__main__":
    run_full_harvest()

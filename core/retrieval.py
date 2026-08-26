"""
Retrieval layer: decides whether a given (sport, content_type, difficulty) request
needs FRESH web data or STABLE historical data from ChromaDB, then fetches it.

Routing heuristic (simple, explainable — good enough for MVP, documented as a
design decision in the README):
  - Guess-the-Number and MCQ/Fill-blank at Hard difficulty -> lean web search
    (specific recent stats change often, and "hard" often means recent/niche facts)
  - Everything else defaults to ChromaDB first; if ChromaDB has too few
    matching docs (cold-start / thin knowledge base), fall back to web search.
  - This-or-That never retrieves anything (opinion-based).
"""

import os
import random
import chromadb
from chromadb.utils import embedding_functions
from tavily import TavilyClient

# Random angles appended to search/retrieval queries so repeated calls for the
# same (sport, difficulty) don't always surface the single most prominent fact.
QUERY_VARIANTS = [
    "well-known record", "lesser-known record", "historic milestone",
    "recent record", "career statistic", "notable achievement",
    "unusual fact", "all-time list", "single-match record", "career total",
]

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_store")
COLLECTION_NAME = "sports_knowledge"

_tavily_client = None
_chroma_client = None
_collection = None


def get_tavily():
    global _tavily_client
    if _tavily_client is None:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY not set in environment/.env")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


def get_chroma_collection():
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        # Local embedding model -> no extra API key needed for embeddings
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME, embedding_function=ef
        )
    return _collection


def web_search(query: str, max_results: int = 4) -> tuple[str, str]:
    """Returns (context_text, source_detail)."""
    client = get_tavily()
    results = client.search(query=query, max_results=max_results, search_depth="advanced")
    chunks = []
    for r in results.get("results", []):
        chunks.append(f"- {r.get('title', '')}: {r.get('content', '')}")
    context = "\n".join(chunks) if chunks else "No web results found."
    return context, f"web_search:{query}"


def chroma_search(query: str, sport: str, n_results: int = 4, pool_size: int = 12) -> tuple[str, str, int]:
    """
    Returns (context_text, source_detail, num_hits).

    Fetches a larger POOL of matches (pool_size) but randomly samples n_results
    from within that pool, instead of always returning the top-N. Otherwise the
    same query returns the same top chunk every single call, and the LLM
    gravitates to whatever fact is most prominent in it — which is exactly why
    every "Cricket / Easy" item kept being about Muralitharan's wicket record.
    """
    collection = get_chroma_collection()
    results = collection.query(
        query_texts=[query],
        n_results=pool_size,
        where={"sport": sport},
    )
    docs = results.get("documents", [[]])[0]
    ids = results.get("ids", [[]])[0]

    if not docs:
        return "", "vector_db:no_hits", 0

    paired = list(zip(docs, ids))
    sample_size = min(n_results, len(paired))
    sampled = random.sample(paired, sample_size)

    context = "\n".join(f"- {d}" for d, _ in sampled)
    source_detail = f"vector_db:{','.join(i for _, i in sampled)}"
    return context, source_detail, len(docs)


MIN_CHROMA_HITS = 2  # below this, treat the vector DB as "too thin" and fall back to web


def retrieve_context(sport: str, content_type: str, difficulty: str, query: str):
    """
    Main routing function. Returns dict:
      { "context": str, "source_type": "web_search"|"vector_db"|"not_applicable",
        "source_detail": str }
    """
    if content_type == "This-or-That":
        return {"context": "", "source_type": "not_applicable", "source_detail": "n/a (opinion-based)"}

    # vary the query so repeated calls don't always surface the same top result
    varied_query = f"{query} {random.choice(QUERY_VARIANTS)}"

    prefer_web = content_type == "Guess-the-Number" or difficulty == "Hard"

    if prefer_web:
        context, detail = web_search(varied_query)
        return {"context": context, "source_type": "web_search", "source_detail": detail}

    # try ChromaDB first (randomly sampled, see chroma_search)
    context, detail, hits = chroma_search(varied_query, sport)
    if hits >= MIN_CHROMA_HITS:
        return {"context": context, "source_type": "vector_db", "source_detail": detail}

    # cold start / thin KB -> fall back to web search
    context, detail = web_search(varied_query)
    return {"context": context, "source_type": "web_search", "source_detail": detail}

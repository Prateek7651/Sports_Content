"""
Core generation engine:
  1. Build the search/retrieval query for this item
  2. Retrieve context (web search or ChromaDB, via retrieval.retrieve_context)
  3. Fill the type-specific prompt template
  4. Call the LLM (Groq)
  5. Parse JSON, validate against the Pydantic schema
  6. Independently re-verify the generated claim against a FRESH web search
     (regardless of whether the original context was from ChromaDB or web) —
     rejects and retries if the web doesn't corroborate it
  7. Check dedup store; if it's a near-repeat, regenerate
  8. On success, record it and return (tagged with web_verified + verification_note)
"""

import json
import os
import time
import uuid

from openai import OpenAI
from pydantic import ValidationError

from schemas.content_schemas import SCHEMA_MAP
from templates.prompt_templates import TEMPLATE_MAP
from core.retrieval import retrieve_context, web_search
from core.dedup import is_duplicate, record_item, get_recent_summaries

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_RETRIES = 3
GENERATION_TEMPERATURE = 0.9  # was implicitly ~default/low; higher = less repetition
LLM_RETRY_ATTEMPTS = 3

VERIFY_PROMPT = """Claim to verify: "{claim}"

Independent web search results (fetched separately, just now):
{context}

Does this independent search corroborate the claim? Only say true if the search
results clearly support it. If the results are empty, unrelated, or contradict
the claim, say false.

Return ONLY valid JSON, no markdown:
{{"verified": true or false, "reason": "1 short sentence"}}
"""

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set in environment/.env")
        _client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    return _client


def _build_query(sport: str, content_type: str, difficulty: str) -> str:
    if content_type == "Guess-the-Number":
        return f"{sport} recent statistics records numbers {difficulty}"
    return f"{sport} facts records history {difficulty}"


def _summary_for_dedup(content_type: str, data: dict) -> str:
    if content_type == "MCQ":
        return data["question"]
    if content_type == "True/False":
        return data["statement"]
    if content_type == "This-or-That":
        return data["prompt"]
    if content_type == "Fill-in-the-Blank":
        return data["sentence_with_blank"]
    if content_type == "Guess-the-Number":
        return data["question"]
    return json.dumps(data)


def _claim_for_verification(content_type: str, data: dict) -> str:
    """
    Builds the single checkable factual claim to verify against the web.
    This-or-That is opinion-based and skips verification entirely (handled
    by the caller before this is ever invoked).
    """
    if content_type == "MCQ":
        return f"{data['question']} Answer: {data['correct_answer']}."
    if content_type == "True/False":
        truth = "True" if data["correct_answer"] else "False"
        return f'"{data["statement"]}" — this statement is {truth}.'
    if content_type == "Fill-in-the-Blank":
        filled = data["sentence_with_blank"].replace("____", data["correct_answer"])
        return filled
    if content_type == "Guess-the-Number":
        return f"{data['question']} Answer: approximately {data['target_number']}."
    return json.dumps(data)


def verify_with_web(content_type: str, data: dict) -> tuple[bool, str]:
    """
    Runs an independent web search on the specific generated claim (not the
    broad topic query used for retrieval) and asks the LLM to confirm the
    search results actually support it. Returns (verified, reason).
    """
    if content_type == "This-or-That":
        return True, "opinion-based, not fact-checked by design"

    claim = _claim_for_verification(content_type, data)
    context, _ = web_search(claim, max_results=4)

    if not context.strip() or context == "No web results found.":
        return False, "no independent web results found to confirm this claim"

    prompt = VERIFY_PROMPT.format(claim=claim, context=context)
    raw = _call_claude(prompt)
    try:
        verdict = json.loads(_strip_json_fences(raw))
        return bool(verdict.get("verified")), verdict.get("reason", "")
    except (json.JSONDecodeError, AttributeError):
        return False, "verification step returned an unparseable response"


def _call_claude(prompt: str) -> str:
    """
    Named _call_claude for backwards compatibility with the rest of this file —
    actually calls Groq's OpenAI-compatible chat completions endpoint.
    Retries on transient errors (e.g. rate limits) with a short backoff.
    """
    client = get_client()
    last_err = None
    for attempt in range(LLM_RETRY_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=800,
                temperature=GENERATION_TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {LLM_RETRY_ATTEMPTS} attempts: {last_err}")


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def generate_item(sport: str, content_type: str, difficulty: str = "Medium") -> dict:
    """
    Generates ONE validated content item. Returns the item as a dict
    (already matching its Pydantic schema, including item_id/source fields).
    Raises RuntimeError if it can't produce a valid, non-duplicate item after retries.
    """
    schema_cls = SCHEMA_MAP[content_type]
    template = TEMPLATE_MAP[content_type]

    query = _build_query(sport, content_type, difficulty)
    retrieved = retrieve_context(sport, content_type, difficulty, query)

    # pulls across ALL content types for this sport now, not just the current
    # one, since the same fact can resurface as a different content type
    avoid_list = get_recent_summaries(sport, limit=12)
    if avoid_list:
        avoid_text = (
            "The following facts/questions were ALREADY used recently for this sport "
            "(across all content types). You MUST pick a DIFFERENT underlying fact — "
            "not just a reworded version of one of these:\n"
            + "\n".join(f"- {a}" for a in avoid_list)
        )
    else:
        avoid_text = "(none yet)"

    last_error = None
    for attempt in range(MAX_RETRIES):
        prompt = template.format(
            sport=sport,
            difficulty=difficulty,
            context=retrieved["context"] or "(no external context needed)",
            avoid_list=avoid_text,
        )
        if last_error:
            prompt += f"\n\nYour previous attempt failed validation with this error, fix it:\n{last_error}"

        raw = _call_claude(prompt)
        try:
            data = json.loads(_strip_json_fences(raw))
        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON: {e}"
            continue

        # attach the fields the LLM doesn't generate itself
        data["item_id"] = str(uuid.uuid4())
        data["sport"] = sport
        data["source_type"] = retrieved["source_type"]
        data["source_detail"] = retrieved["source_detail"]
        if content_type != "This-or-That":
            data["difficulty"] = difficulty

        try:
            validated = schema_cls(**data)
        except ValidationError as e:
            last_error = str(e)
            continue

        # every generation is independently re-checked against a fresh web
        # search of the specific claim, regardless of whether the original
        # context came from ChromaDB or web search — catches stale/wrong
        # facts the retrieval step or the LLM itself introduced
        verified, reason = verify_with_web(content_type, data)
        if not verified:
            last_error = (
                f"Web verification failed for this claim ({reason}). "
                "Generate a different, verifiable fact."
            )
            continue

        summary = _summary_for_dedup(content_type, data)
        if is_duplicate(summary, sport):
            last_error = (
                "That fact (or a close rewording of it) was already used recently. "
                "Pick a genuinely different fact/stat/player, not a rephrasing."
            )
            continue

        record_item(sport, content_type, summary)
        result = validated.model_dump()
        result["web_verified"] = verified
        result["verification_note"] = reason
        return result

    raise RuntimeError(
        f"Failed to generate a valid {content_type} item after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def generate_batch(sport: str, content_types: list[str], difficulty: str = "Medium", batch_size: int = 5) -> list[dict]:
    """
    Generates a batch, cycling through content_types if mixed.
    e.g. content_types=["MCQ","True/False"], batch_size=5 -> MCQ,T/F,MCQ,T/F,MCQ
    """
    items = []
    errors = []
    for i in range(batch_size):
        ctype = content_types[i % len(content_types)]
        try:
            items.append(generate_item(sport, ctype, difficulty))
        except RuntimeError as e:
            errors.append({"content_type": ctype, "error": str(e)})
    return {"items": items, "errors": errors}


# A sensible default rotation so a week doesn't feel repetitive: MCQ mid-week,
# This-or-That to open/close the week (best organic engagement), a T/F and
# Fill-blank mixed in, Guess-the-Number as a periodic change-of-pace.
DEFAULT_WEEKLY_ROTATION = [
    ("Monday", "This-or-That"),
    ("Tuesday", "MCQ"),
    ("Wednesday", "True/False"),
    ("Thursday", "Fill-in-the-Blank"),
    ("Friday", "MCQ"),
    ("Saturday", "Guess-the-Number"),
    ("Sunday", "This-or-That"),
]


def generate_weekly_calendar(sport: str, difficulty: str = "Medium", items_per_day: int = 1,
                              rotation: list[tuple] = None) -> dict:
    """
    Generates a full week of content in one call, one distinct content type
    (or a few) per day so the batch reads like an actual posting calendar
    rather than a flat list — directly targets the assignment's stated goal
    of "vary content strategy so followers don't get bored."

    Returns: {"calendar": [{"day": "Monday", "items": [...]}, ...], "errors": [...]}
    """
    rotation = rotation or DEFAULT_WEEKLY_ROTATION
    calendar = []
    errors = []

    for day, ctype in rotation:
        day_items = []
        for _ in range(items_per_day):
            try:
                day_items.append(generate_item(sport, ctype, difficulty))
            except RuntimeError as e:
                errors.append({"day": day, "content_type": ctype, "error": str(e)})
        calendar.append({"day": day, "content_type": ctype, "items": day_items})

    return {"calendar": calendar, "errors": errors}

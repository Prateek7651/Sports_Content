"""
One prompt template per content type. Each template:
  - injects retrieved context (web search or ChromaDB results)
  - injects a "avoid these" list for freshness/diversity
  - forces strict JSON output matching the corresponding Pydantic schema
"""

MCQ_TEMPLATE = """You are a sports content generator creating a Multiple Choice Question.

Sport: {sport}
Difficulty: {difficulty}

Retrieved context (use ONLY this for facts, do not invent stats):
{context}

Avoid repeating any of these previously used questions/facts:
{avoid_list}

Generate ONE multiple choice question. Return ONLY valid JSON, no markdown, no preamble:
{{
  "question": "...",
  "options": ["...", "...", "...", "..."],
  "correct_answer": "must exactly match one of the options",
  "explanation": "1-2 sentences, grounded in the context above"
}}
"""

TRUE_FALSE_TEMPLATE = """You are a sports content generator creating a True/False statement.

Sport: {sport}
Difficulty: {difficulty}

Retrieved context (use ONLY this for facts, do not invent stats):
{context}

Avoid repeating any of these previously used statements:
{avoid_list}

Generate ONE true/false statement (mix it up — don't always make it True). Return ONLY valid JSON:
{{
  "statement": "...",
  "correct_answer": true,
  "explanation": "1-2 sentences, grounded in the context above"
}}
"""

THIS_OR_THAT_TEMPLATE = """You are a sports content generator creating a "This-or-That" opinion poll.
This is NOT fact-based — it's meant to spark debate/engagement (e.g. player comparisons, style preferences).

Sport: {sport}

Avoid repeating any of these previously used prompts:
{avoid_list}

Generate ONE this-or-that poll. Return ONLY valid JSON:
{{
  "prompt": "e.g. Messi or Ronaldo — who's the greater dribbler?",
  "options": ["Option A", "Option B"]
}}
"""

FILL_BLANK_TEMPLATE = """You are a sports content generator creating a Fill-in-the-Blank question.

Sport: {sport}
Difficulty: {difficulty}

Retrieved context (use ONLY this for facts, do not invent stats):
{context}

Avoid repeating any of these previously used sentences:
{avoid_list}

Generate ONE fill-in-the-blank item. The sentence MUST contain the literal placeholder "____".
Return ONLY valid JSON:
{{
  "sentence_with_blank": "e.g. Virat Kohli scored ____ centuries in ODIs before 2024.",
  "options": ["...", "...", "...", "..."],
  "correct_answer": "must exactly match one of the options",
  "explanation": "1-2 sentences, grounded in the context above"
}}
"""

GUESS_NUMBER_TEMPLATE = """You are a sports content generator creating a Guess-the-Number challenge.

Sport: {sport}
Difficulty: {difficulty}

Retrieved context (use ONLY this for facts, do not invent stats):
{context}

Avoid repeating any of these previously used questions:
{avoid_list}

Generate ONE guess-the-number question with a numeric answer.
Choose a sensible tolerance based on the magnitude of the number
(e.g. ±5 for a number around 100, ±2 for a number around 20, ±1 for a number under 10).
Return ONLY valid JSON:
{{
  "question": "...",
  "target_number": 123,
  "tolerance": 5,
  "explanation": "1-2 sentences, grounded in the context above"
}}
"""

TEMPLATE_MAP = {
    "MCQ": MCQ_TEMPLATE,
    "True/False": TRUE_FALSE_TEMPLATE,
    "This-or-That": THIS_OR_THAT_TEMPLATE,
    "Fill-in-the-Blank": FILL_BLANK_TEMPLATE,
    "Guess-the-Number": GUESS_NUMBER_TEMPLATE,
}

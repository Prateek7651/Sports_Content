"""
Pydantic schemas for all 5 sports content types.
Every generated item MUST validate against one of these before being returned to the user.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Sport(str, Enum):
    CRICKET = "Cricket"
    FOOTBALL = "Football"
    TENNIS = "Tennis"
    BADMINTON = "Badminton"
    BASKETBALL = "Basketball"


class Difficulty(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class ContentType(str, Enum):
    MCQ = "MCQ"
    TRUE_FALSE = "True/False"
    THIS_OR_THAT = "This-or-That"
    FILL_BLANK = "Fill-in-the-Blank"
    GUESS_NUMBER = "Guess-the-Number"


class SourceType(str, Enum):
    WEB_SEARCH = "web_search"
    VECTOR_DB = "vector_db"
    NOT_APPLICABLE = "not_applicable"  # for opinion-based polls


# ---------- Shared base ----------

class BaseContentItem(BaseModel):
    item_id: str  # uuid, used for per-item regeneration
    sport: Sport
    content_type: ContentType
    source_type: SourceType
    source_detail: str = Field(
        ..., description="e.g. search query used, or doc id retrieved from ChromaDB"
    )


# ---------- 1. MCQ ----------

class MCQItem(BaseContentItem):
    content_type: ContentType = ContentType.MCQ
    difficulty: Difficulty
    question: str
    options: List[str] = Field(..., min_length=4, max_length=4)
    correct_answer: str
    explanation: str

    @field_validator("correct_answer")
    @classmethod
    def correct_answer_must_be_in_options(cls, v, info):
        options = info.data.get("options")
        if options and v not in options:
            raise ValueError("correct_answer must exactly match one of the 4 options")
        return v


# ---------- 2. True / False ----------

class TrueFalseItem(BaseContentItem):
    content_type: ContentType = ContentType.TRUE_FALSE
    difficulty: Difficulty
    statement: str
    correct_answer: bool
    explanation: str


# ---------- 3. This-or-That Poll (opinion, no correct answer) ----------

class ThisOrThatItem(BaseContentItem):
    content_type: ContentType = ContentType.THIS_OR_THAT
    source_type: SourceType = SourceType.NOT_APPLICABLE
    prompt: str
    options: List[str] = Field(..., min_length=2, max_length=2)
    is_opinion_based: bool = True  # always flagged, never fact-checked


# ---------- 4. Fill in the Blank ----------

class FillBlankItem(BaseContentItem):
    content_type: ContentType = ContentType.FILL_BLANK
    difficulty: Difficulty
    sentence_with_blank: str  # must contain "____"
    options: List[str] = Field(..., min_length=4, max_length=4)
    correct_answer: str
    explanation: str

    @field_validator("sentence_with_blank")
    @classmethod
    def must_contain_blank(cls, v):
        if "____" not in v:
            raise ValueError("sentence_with_blank must contain a '____' placeholder")
        return v

    @field_validator("correct_answer")
    @classmethod
    def correct_answer_must_be_in_options(cls, v, info):
        options = info.data.get("options")
        if options and v not in options:
            raise ValueError("correct_answer must exactly match one of the 4 options")
        return v


# ---------- 5. Guess the Number ----------

class GuessNumberItem(BaseContentItem):
    content_type: ContentType = ContentType.GUESS_NUMBER
    difficulty: Difficulty
    question: str
    target_number: float
    tolerance: float = Field(..., description="± range considered a correct guess")
    explanation: str

    @field_validator("tolerance")
    @classmethod
    def tolerance_must_be_reasonable(cls, v, info):
        target = info.data.get("target_number")
        if target is not None and v > abs(target):
            raise ValueError("tolerance should not exceed the target number itself")
        if v < 0:
            raise ValueError("tolerance cannot be negative")
        return v


# ---------- Batch request/response ----------

class GenerationRequest(BaseModel):
    sport: Sport
    difficulty: Optional[Difficulty] = Difficulty.MEDIUM
    content_types: List[ContentType] = Field(
        ..., description="one or more types to mix in this batch"
    )
    batch_size: int = Field(default=5, ge=1, le=10)


SCHEMA_MAP = {
    ContentType.MCQ: MCQItem,
    ContentType.TRUE_FALSE: TrueFalseItem,
    ContentType.THIS_OR_THAT: ThisOrThatItem,
    ContentType.FILL_BLANK: FillBlankItem,
    ContentType.GUESS_NUMBER: GuessNumberItem,
}

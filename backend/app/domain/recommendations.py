from pydantic import BaseModel, Field


class RecommendationExplanation(BaseModel):
    summary: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

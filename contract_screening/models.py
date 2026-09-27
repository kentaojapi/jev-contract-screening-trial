from pydantic import BaseModel, Field


class ContractDocument(BaseModel):
    """A contract body to evaluate."""

    text: str = Field(min_length=1)


class RiskFlags(BaseModel):
    """Risk attributes that require human review when entrustment is present."""

    sensitive_personal_info: bool
    childrens_data: bool
    biometric_facial_data: bool
    subcontracting_possible: bool
    cross_border_transfer: bool


class RiskScores(BaseModel):
    """Jev's affirmative probability for each risk attribute."""

    sensitive_personal_info: float = Field(ge=0.0, le=1.0)
    childrens_data: float = Field(ge=0.0, le=1.0)
    biometric_facial_data: float = Field(ge=0.0, le=1.0)
    subcontracting_possible: float = Field(ge=0.0, le=1.0)
    cross_border_transfer: float = Field(ge=0.0, le=1.0)


class ScreeningResult(BaseModel):
    """The stable JSON output returned by the screener."""

    is_personal_data_entrustment: bool
    jev_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    risk_flags: RiskFlags
    risk_scores: RiskScores
    matched_keywords: list[str]
    requires_human_review: bool


class ScreeningMeasurement(BaseModel):
    """A screening result together with the API-reported input token count."""

    result: ScreeningResult
    input_tokens: int | None

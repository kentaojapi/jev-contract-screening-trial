import re
from collections.abc import Mapping
from typing import ClassVar, Protocol, TypedDict

from typesafe_sdk import Noul, TypeSafeClient

from contract_screening.models import (
    ContractDocument,
    RiskFlags,
    RiskScores,
    ScreeningMeasurement,
    ScreeningResult,
)
from contract_screening.questions import ScreeningQuestions


class NoulAnswer(Protocol):
    """The Noul portion of a TypeSafe SDK response."""

    noul: float


class SystemOneResponse(Protocol):
    """The response fields used by this application."""

    nouls: Mapping[str, NoulAnswer]
    usage: "TokenUsage"


class TokenUsage(Protocol):
    """The API-reported token count used by a System One request."""

    input_tokens: int | None


class SystemOneClient(Protocol):
    """The TypeSafe client interface used by the screener."""

    def system_one(
        self, state: dict[str, str], questions: dict[str, Noul]
    ) -> SystemOneResponse: ...


class RiskAnswerKeys(TypedDict):
    sensitive_personal_info: str
    childrens_data: str
    biometric_facial_data: str
    subcontracting_possible: str
    cross_border_transfer: str


class RiskFlagValues(TypedDict):
    sensitive_personal_info: bool
    childrens_data: bool
    biometric_facial_data: bool
    subcontracting_possible: bool
    cross_border_transfer: bool


class RiskScoreValues(TypedDict):
    sensitive_personal_info: float
    childrens_data: float
    biometric_facial_data: float
    subcontracting_possible: float
    cross_border_transfer: float


class ContractScreener:
    """Evaluates a contract with Jev and derives the application decision."""

    MODEL = "jev-latest"
    POSITIVE_THRESHOLD = 0.5
    AUTOMATION_CONFIDENCE_THRESHOLD = 0.9
    CONFIDENCE_DECIMAL_PLACES = 6
    MAX_MATCHED_KEYWORDS = 12
    RISK_ANSWER_KEYS: ClassVar[RiskAnswerKeys] = {
        "sensitive_personal_info": "sensitive_personal_info",
        "childrens_data": "childrens_data",
        "biometric_facial_data": "biometric_facial_data",
        "subcontracting_possible": "subcontracting_possible",
        "cross_border_transfer": "cross_border_transfer",
    }
    KEYWORD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("個人情報", re.compile(r"個人情報")),
        ("個人データ", re.compile(r"個人データ")),
        ("氏名", re.compile(r"氏名")),
        ("連絡先", re.compile(r"連絡先")),
        ("顧客情報", re.compile(r"顧客情報")),
        ("患者", re.compile(r"患者")),
        ("病歴", re.compile(r"病歴")),
        ("未成年", re.compile(r"未成年")),
        ("顔特徴情報", re.compile(r"顔特徴情報")),
        ("生体認証", re.compile(r"生体認証")),
        ("再委託", re.compile(r"再委託")),
        ("海外", re.compile(r"海外|国外")),
        ("匿名加工情報", re.compile(r"匿名加工情報")),
        ("統計情報", re.compile(r"統計情報|集計済み")),
    )

    def __init__(self, client: SystemOneClient | None = None) -> None:
        self.client = client or TypeSafeClient(model=self.MODEL)

    def screen(self, contract_text: str) -> ScreeningResult:
        return self.screen_with_usage(contract_text).result

    def screen_with_usage(self, contract_text: str) -> ScreeningMeasurement:
        """Evaluate a contract and retain the input usage reported by the API."""
        document = ContractDocument(text=contract_text)
        response = self.client.system_one(
            state={"contract_text": document.text},
            questions=ScreeningQuestions.build(),
        )
        entrustment_probability = response.nouls["entrustment"].noul
        is_entrustment = self._is_positive(entrustment_probability)
        confidence = round(
            (
                entrustment_probability
                if is_entrustment
                else 1.0 - entrustment_probability
            ),
            self.CONFIDENCE_DECIMAL_PLACES,
        )
        risk_flags = self._risk_flags(response, is_entrustment)
        return ScreeningMeasurement(
            result=ScreeningResult(
                is_personal_data_entrustment=is_entrustment,
                jev_score=entrustment_probability,
                confidence=confidence,
                risk_flags=risk_flags,
                risk_scores=self._risk_scores(response),
                matched_keywords=self._matched_keywords(document.text),
                requires_human_review=(
                    confidence < self.AUTOMATION_CONFIDENCE_THRESHOLD
                    or any(risk_flags.model_dump().values())
                ),
            ),
            input_tokens=response.usage.input_tokens,
        )

    def _is_positive(self, probability: float) -> bool:
        return probability >= self.POSITIVE_THRESHOLD

    def _risk_flags(
        self, response: SystemOneResponse, is_entrustment: bool
    ) -> RiskFlags:
        values: RiskFlagValues = {
            flag_name: (
                is_entrustment and self._is_positive(response.nouls[answer_key].noul)
            )
            for flag_name, answer_key in self.RISK_ANSWER_KEYS.items()
        }
        return RiskFlags(**values)

    def _risk_scores(self, response: SystemOneResponse) -> RiskScores:
        values: RiskScoreValues = {
            score_name: response.nouls[answer_key].noul
            for score_name, answer_key in self.RISK_ANSWER_KEYS.items()
        }
        return RiskScores(**values)

    def _matched_keywords(self, contract_text: str) -> list[str]:
        return [
            keyword
            for keyword, pattern in self.KEYWORD_PATTERNS
            if pattern.search(contract_text)
        ][: self.MAX_MATCHED_KEYWORDS]

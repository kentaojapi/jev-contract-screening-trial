from types import SimpleNamespace

import pytest
from typesafe_sdk import Noul

from contract_screening.questions import ScreeningQuestions
from contract_screening.service import ContractScreener


class FakeClient:
    """A deterministic System One client for unit tests."""

    def __init__(self, probabilities: dict[str, float]) -> None:
        self.probabilities = probabilities
        self.last_state: dict[str, str] | None = None
        self.last_questions: dict[str, Noul] | None = None

    def system_one(
        self, state: dict[str, str], questions: dict[str, Noul]
    ) -> SimpleNamespace:
        self.last_state = state
        self.last_questions = questions
        return SimpleNamespace(
            nouls={
                name: SimpleNamespace(noul=probability)
                for name, probability in self.probabilities.items()
            },
            usage=SimpleNamespace(input_tokens=321),
        )


class TestContractScreener:
    @pytest.mark.parametrize(
        [
            "probabilities",
            "expected_entrustment",
            "expected_confidence",
            "expected_review",
        ],
        [
            pytest.param(
                {
                    "entrustment": 0.97,
                    "sensitive_personal_info": 0.98,
                    "childrens_data": 0.02,
                    "biometric_facial_data": 0.01,
                    "subcontracting_possible": 0.96,
                    "cross_border_transfer": 0.95,
                },
                True,
                0.97,
                True,
                id="case1: clear entrustment with risk flags",
            ),
            pytest.param(
                {
                    "entrustment": 0.03,
                    "sensitive_personal_info": 0.99,
                    "childrens_data": 0.99,
                    "biometric_facial_data": 0.99,
                    "subcontracting_possible": 0.99,
                    "cross_border_transfer": 0.99,
                },
                False,
                0.97,
                False,
                id="case2: clear non-entrustment ignores risk flags",
            ),
            pytest.param(
                {
                    "entrustment": 0.42,
                    "sensitive_personal_info": 0.01,
                    "childrens_data": 0.01,
                    "biometric_facial_data": 0.01,
                    "subcontracting_possible": 0.01,
                    "cross_border_transfer": 0.01,
                },
                False,
                0.58,
                True,
                id="case3: ambiguous non-entrustment requires review",
            ),
        ],
    )
    def test_screen_derives_policy_result_from_noul_probabilities(
        self,
        probabilities: dict[str, float],
        expected_entrustment: bool,
        expected_confidence: float,
        expected_review: bool,
    ) -> None:
        client = FakeClient(probabilities)
        result = ContractScreener(client).screen(
            "患者の個人データを再委託先の海外拠点で取り扱う。"
        )

        assert result.is_personal_data_entrustment is expected_entrustment
        assert result.confidence == expected_confidence
        assert result.requires_human_review is expected_review
        assert result.jev_score == probabilities["entrustment"]
        assert result.risk_scores.model_dump() == {
            name: probability
            for name, probability in probabilities.items()
            if name != "entrustment"
        }
        if expected_entrustment:
            assert result.risk_flags.sensitive_personal_info is True
            assert result.risk_flags.subcontracting_possible is True
            assert result.risk_flags.cross_border_transfer is True
        else:
            assert result.risk_flags.model_dump() == {
                "sensitive_personal_info": False,
                "childrens_data": False,
                "biometric_facial_data": False,
                "subcontracting_possible": False,
                "cross_border_transfer": False,
            }

    def test_screen_passes_contract_text_and_all_questions_to_jev(self) -> None:
        probabilities = {
            "entrustment": 0.91,
            "sensitive_personal_info": 0.01,
            "childrens_data": 0.01,
            "biometric_facial_data": 0.01,
            "subcontracting_possible": 0.01,
            "cross_border_transfer": 0.01,
        }
        client = FakeClient(probabilities)
        ContractScreener(client).screen("氏名と連絡先を入力する。")

        assert client.last_state == {"contract_text": "氏名と連絡先を入力する。"}
        assert client.last_questions is not None
        assert set(client.last_questions) == {
            "entrustment",
            "sensitive_personal_info",
            "childrens_data",
            "biometric_facial_data",
            "subcontracting_possible",
            "cross_border_transfer",
        }
        assert client.last_questions == ScreeningQuestions.build()

    def test_screen_with_usage_returns_api_reported_input_tokens(self) -> None:
        probabilities = {
            "entrustment": 0.91,
            "sensitive_personal_info": 0.01,
            "childrens_data": 0.01,
            "biometric_facial_data": 0.01,
            "subcontracting_possible": 0.01,
            "cross_border_transfer": 0.01,
        }

        measurement = ContractScreener(FakeClient(probabilities)).screen_with_usage(
            "氏名と連絡先を入力する。"
        )

        assert measurement.input_tokens == 321
        assert measurement.result.is_personal_data_entrustment is True

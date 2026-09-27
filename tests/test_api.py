import pytest
from fastapi.testclient import TestClient

from contract_screening.api import BatchScreeningExecutor, create_app
from contract_screening.models import (
    RiskFlags,
    RiskScores,
    ScreeningMeasurement,
    ScreeningResult,
)


class FakeScreener:
    """A deterministic screener that lets the HTTP tests avoid external requests."""

    def screen_with_usage(self, contract_text: str) -> ScreeningMeasurement:
        return ScreeningMeasurement(
            result=ScreeningResult(
                is_personal_data_entrustment="個人データ" in contract_text,
                jev_score=0.95,
                confidence=0.95,
                risk_flags=RiskFlags(
                    sensitive_personal_info=False,
                    childrens_data=False,
                    biometric_facial_data=False,
                    subcontracting_possible=False,
                    cross_border_transfer=False,
                ),
                risk_scores=RiskScores(
                    sensitive_personal_info=0.1,
                    childrens_data=0.2,
                    biometric_facial_data=0.3,
                    subcontracting_possible=0.4,
                    cross_border_transfer=0.5,
                ),
                matched_keywords=[],
                requires_human_review=False,
            ),
            input_tokens=12,
        )


class TestScreeningApi:
    def test_lists_only_indexes_and_titles_before_screening(self) -> None:
        client = TestClient(create_app())

        response = client.get("/api/contracts")

        assert response.status_code == 200
        assert len(response.json()) == 100
        assert set(response.json()[0]) == {
            "id",
            "index",
            "title",
            "dataset_category",
        }
        assert response.json()[0]["dataset_category"] == "明確に該当"

    def test_returns_a_contract_body_for_the_right_drawer(self) -> None:
        client = TestClient(create_app())

        response = client.get("/api/contracts/clear-entrustment-01")

        assert response.status_code == 200
        assert response.json()["title"] == "架空通販会社の配送業務委託契約"
        assert "顧客の氏名" in response.json()["body"]

    def test_screens_a_selected_batch_and_reports_usage(self) -> None:
        executor = BatchScreeningExecutor(screener_factory=FakeScreener)
        client = TestClient(create_app(executor=executor))

        response = client.post(
            "/api/screenings",
            json={
                "contract_ids": [
                    "clear-entrustment-01",
                    "clear-non-entrustment-01",
                ]
            },
        )

        payload = response.json()
        assert response.status_code == 200
        assert [result["contract_id"] for result in payload["results"]] == [
            "clear-entrustment-01",
            "clear-non-entrustment-01",
        ]
        assert payload["results"][0]["jev_score"] == 0.95
        assert payload["results"][0]["risk_scores"]["childrens_data"] == 0.2
        assert payload["metrics"]["input_tokens"] == 24
        assert payload["metrics"]["input_cost_usd"] == pytest.approx(0.000001008)
        assert payload["metrics"]["input_cost_jpy"] == pytest.approx(0.00016128)

    def test_rejects_an_unknown_contract_identifier(self) -> None:
        client = TestClient(create_app())

        response = client.post("/api/screenings", json={"contract_ids": ["missing"]})

        assert response.status_code == 404

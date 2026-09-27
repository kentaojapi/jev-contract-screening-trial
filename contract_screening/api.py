import asyncio
from collections.abc import Callable
from time import perf_counter
from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from contract_screening.dataset import ContractDataset, ContractSummary, DatasetContract
from contract_screening.models import RiskFlags, RiskScores, ScreeningMeasurement
from contract_screening.service import ContractScreener


class ContractDetail(BaseModel):
    """The full synthetic contract opened from the list drawer."""

    id: str
    title: str
    body: str


class ScreeningBatchRequest(BaseModel):
    """A client-selected set of contracts to evaluate."""

    contract_ids: list[str] = Field(min_length=1, max_length=100)


class ContractScreening(BaseModel):
    """One contract's policy outcome formatted for the table."""

    contract_id: str
    is_personal_data_entrustment: bool
    jev_score: float
    confidence: float
    risk_flags: RiskFlags
    risk_scores: RiskScores
    requires_human_review: bool
    input_tokens: int | None


class ExecutionMetrics(BaseModel):
    """Aggregate timing, actual input usage, and cost for a batch."""

    elapsed_ms: int
    input_tokens: int | None
    input_cost_usd: float | None
    input_cost_jpy: float | None
    input_price_per_million_usd: float
    yen_per_usd: int


class ScreeningBatchResponse(BaseModel):
    """The completed evaluations and the aggregate execution metrics."""

    results: list[ContractScreening]
    metrics: ExecutionMetrics


class ContractScreeningService(Protocol):
    """The portion of the existing screener used by the concurrent executor."""

    def screen_with_usage(self, contract_text: str) -> ScreeningMeasurement: ...


class BatchScreeningExecutor:
    """Runs independent System One requests concurrently with a bounded fan-out."""

    MAX_CONCURRENT_REQUESTS = 12
    INPUT_TOKEN_PRICE_PER_MILLION_USD = 0.042
    YEN_PER_USD = 160

    def __init__(
        self,
        screener_factory: Callable[[], ContractScreeningService] = ContractScreener,
    ) -> None:
        self.screener_factory = screener_factory

    async def execute(self, contracts: list[DatasetContract]) -> ScreeningBatchResponse:
        """Screen the requested contracts in parallel and sum their API usage."""
        started_at = perf_counter()
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)
        results = await asyncio.gather(
            *(self._screen_one(contract, semaphore) for contract in contracts)
        )
        elapsed_ms = round((perf_counter() - started_at) * 1000)
        return ScreeningBatchResponse(
            results=results,
            metrics=self._metrics(elapsed_ms, results),
        )

    async def _screen_one(
        self, contract: DatasetContract, semaphore: asyncio.Semaphore
    ) -> ContractScreening:
        async with semaphore:
            measurement = await asyncio.to_thread(
                self._screen_synchronously, contract.body
            )
        return ContractScreening(
            contract_id=contract.id,
            **measurement.result.model_dump(),
            input_tokens=measurement.input_tokens,
        )

    def _screen_synchronously(self, contract_text: str) -> ScreeningMeasurement:
        return self.screener_factory().screen_with_usage(contract_text)

    def _metrics(
        self, elapsed_ms: int, results: list[ContractScreening]
    ) -> ExecutionMetrics:
        input_token_counts = [result.input_tokens for result in results]
        if any(input_tokens is None for input_tokens in input_token_counts):
            return ExecutionMetrics(
                elapsed_ms=elapsed_ms,
                input_tokens=None,
                input_cost_usd=None,
                input_cost_jpy=None,
                input_price_per_million_usd=self.INPUT_TOKEN_PRICE_PER_MILLION_USD,
                yen_per_usd=self.YEN_PER_USD,
            )
        input_tokens = sum(
            input_tokens
            for input_tokens in input_token_counts
            if input_tokens is not None
        )
        input_cost_usd = (
            input_tokens / 1_000_000 * self.INPUT_TOKEN_PRICE_PER_MILLION_USD
        )
        return ExecutionMetrics(
            elapsed_ms=elapsed_ms,
            input_tokens=input_tokens,
            input_cost_usd=input_cost_usd,
            input_cost_jpy=input_cost_usd * self.YEN_PER_USD,
            input_price_per_million_usd=self.INPUT_TOKEN_PRICE_PER_MILLION_USD,
            yen_per_usd=self.YEN_PER_USD,
        )


def create_app(
    dataset: ContractDataset | None = None,
    executor: BatchScreeningExecutor | None = None,
) -> FastAPI:
    """Create the CORS-enabled HTTP interface consumed by the static frontend."""
    application = FastAPI(
        title="契約書個人データ取扱い委託スクリーナー API",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.state.dataset = dataset or ContractDataset()
    application.state.executor = executor or BatchScreeningExecutor()

    @application.get("/api/contracts", response_model=list[ContractSummary])
    async def list_contracts() -> list[ContractSummary]:
        return application.state.dataset.summaries()

    @application.get("/api/contracts/{contract_id}", response_model=ContractDetail)
    async def get_contract(contract_id: str) -> ContractDetail:
        try:
            contract = application.state.dataset.get(contract_id)
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="契約書が見つかりません。"
            ) from error
        return ContractDetail(
            id=contract.id,
            title=contract.title,
            body=contract.body,
        )

    @application.post("/api/screenings", response_model=ScreeningBatchResponse)
    async def screen_contracts(
        request: ScreeningBatchRequest,
    ) -> ScreeningBatchResponse:
        try:
            contracts = application.state.dataset.get_many(request.contract_ids)
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="指定された契約書が見つかりません。"
            ) from error
        return await application.state.executor.execute(contracts)

    return application


app = create_app()

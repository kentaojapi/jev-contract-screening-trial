import json
from collections import Counter
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel


class GroundTruth(BaseModel):
    """Expected classification metadata kept out of the browser API."""

    entrustment: bool
    difficulty: str

    def dataset_category(self) -> str:
        """Return the human-readable benchmark category shown in the UI."""
        match (self.entrustment, self.difficulty):
            case (True, "clear"):
                return "明確に該当"
            case (False, "clear"):
                return "明確に該当しない"
            case (True, "ambiguous"):
                return "グレーだが該当"
            case (False, "ambiguous"):
                return "グレーだが該当しない"
            case _:
                raise ValueError("The dataset has an unsupported category.")


class DatasetContract(BaseModel):
    """A synthetic contract used in the screening benchmark."""

    id: str
    title: str
    body: str
    ground_truth: GroundTruth


class ContractSummary(BaseModel):
    """The data needed to render the initial contract list."""

    id: str
    index: int
    title: str
    dataset_category: str


class ContractDataset:
    """Loads and validates the four balanced synthetic contract subsets."""

    DATA_DIRECTORY: ClassVar[Path] = Path(__file__).resolve().parents[1] / "data"
    FILE_NAMES: ClassVar[tuple[str, ...]] = (
        "clear_entrustment.json",
        "clear_non_entrustment.json",
        "ambiguous_entrustment.json",
        "ambiguous_non_entrustment.json",
    )
    EXPECTED_DISTRIBUTION: ClassVar[Counter[tuple[bool, str]]] = Counter(
        {
            (True, "clear"): 25,
            (False, "clear"): 25,
            (True, "ambiguous"): 25,
            (False, "ambiguous"): 25,
        }
    )

    def __init__(self) -> None:
        self.contracts = self._load_contracts()
        self.contracts_by_id = {contract.id: contract for contract in self.contracts}
        self._validate_contracts()

    def summaries(self) -> list[ContractSummary]:
        """Return the lightweight records displayed before screening begins."""
        return [
            ContractSummary(
                id=contract.id,
                index=index,
                title=contract.title,
                dataset_category=contract.ground_truth.dataset_category(),
            )
            for index, contract in enumerate(self.contracts, start=1)
        ]

    def get(self, contract_id: str) -> DatasetContract:
        """Return one contract body or raise KeyError for an unknown identifier."""
        return self.contracts_by_id[contract_id]

    def get_many(self, contract_ids: list[str]) -> list[DatasetContract]:
        """Resolve a requested batch while rejecting every unknown identifier."""
        unknown_ids = [
            contract_id
            for contract_id in contract_ids
            if contract_id not in self.contracts_by_id
        ]
        if unknown_ids:
            raise KeyError(", ".join(unknown_ids))
        return [self.get(contract_id) for contract_id in contract_ids]

    def _load_contracts(self) -> list[DatasetContract]:
        contracts: list[DatasetContract] = []
        for filename in self.FILE_NAMES:
            path = self.DATA_DIRECTORY / filename
            raw_contracts = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw_contracts, list):
                raise TypeError(f"{path} must contain a JSON array.")
            contracts.extend(
                DatasetContract.model_validate(raw_contract)
                for raw_contract in raw_contracts
            )
        return contracts

    def _validate_contracts(self) -> None:
        if len(self.contracts) != 100:
            raise ValueError("The dataset must contain exactly 100 contracts.")
        if len(self.contracts_by_id) != len(self.contracts):
            raise ValueError("Every contract identifier must be unique.")
        distribution = Counter(
            (contract.ground_truth.entrustment, contract.ground_truth.difficulty)
            for contract in self.contracts
        )
        if distribution != self.EXPECTED_DISTRIBUTION:
            raise ValueError(
                "The dataset must contain 25 contracts in each expected category."
            )

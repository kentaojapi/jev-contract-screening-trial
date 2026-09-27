from collections import Counter

from contract_screening.dataset import ContractDataset


class TestContractDataset:
    def test_loads_the_balanced_hundred_contract_dataset(self) -> None:
        dataset = ContractDataset()
        distribution = Counter(
            (contract.ground_truth.entrustment, contract.ground_truth.difficulty)
            for contract in dataset.contracts
        )

        assert len(dataset.contracts) == 100
        assert distribution == {
            (True, "clear"): 25,
            (False, "clear"): 25,
            (True, "ambiguous"): 25,
            (False, "ambiguous"): 25,
        }

    def test_summaries_exclude_the_contract_body(self) -> None:
        summaries = ContractDataset().summaries()

        assert summaries[0].index == 1
        assert len(summaries) == 100
        assert "body" not in summaries[0].model_dump()
        assert summaries[0].dataset_category == "明確に該当"

    def test_contract_bodies_follow_a_short_contract_format(self) -> None:
        for contract in ContractDataset().contracts:
            assert contract.body.startswith(contract.title)
            assert "甲" in contract.body
            assert "乙" in contract.body
            assert all(
                article in contract.body
                for article in ("第1条", "第2条", "第3条", "第4条")
            )

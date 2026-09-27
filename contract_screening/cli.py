import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from contract_screening.service import ContractScreener

load_dotenv()


class ApiKeyConfiguration:
    """Validates the API key loaded from the local environment."""

    API_KEY = os.environ.get("TYPESAFE_API_KEY")

    def ensure_configured(self) -> None:
        if not self.API_KEY:
            raise RuntimeError(
                "TYPESAFE_API_KEY must be set in the environment or .env file."
            )


class CommandLineApplication:
    """Reads contract files and writes screening results as JSON."""

    EXAMPLES_DIRECTORY = Path(__file__).resolve().parents[1] / "examples"

    def __init__(self, screener: ContractScreener) -> None:
        self.screener = screener

    def run(self, arguments: Sequence[str] | None = None) -> int:
        parser = self._create_parser()
        parsed = parser.parse_args(arguments)
        if bool(parsed.contract) == parsed.examples:
            parser.error("provide a contract path or --examples, but not both")
        if parsed.contract is not None:
            output = self.screener.screen(
                self._read_contract(parsed.contract)
            ).model_dump()
        else:
            output = {
                path.stem: self.screener.screen(self._read_contract(path)).model_dump()
                for path in sorted(self.EXAMPLES_DIRECTORY.glob("*.md"))
            }
        json.dump(output, fp=sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    def _create_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="Screen contracts for personal-data handling entrustment."
        )
        parser.add_argument(
            "contract",
            nargs="?",
            type=Path,
            help="UTF-8 contract file to screen",
        )
        parser.add_argument(
            "--examples",
            action="store_true",
            help="screen every bundled example",
        )
        return parser

    def _read_contract(self, path: Path) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"Contract file was not found: {path}")
        return path.read_text(encoding="utf-8")


def main() -> int:
    ApiKeyConfiguration().ensure_configured()
    return CommandLineApplication(ContractScreener()).run()

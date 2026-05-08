import json
from pathlib import Path

RESULT_PATH = Path("/app/result.json")


def test_result_file_exists() -> None:
    assert RESULT_PATH.exists(), "result.json artifact does not exist"


def test_result_contents() -> None:
    data = json.loads(RESULT_PATH.read_text())

    assert data["count"] == 50, f"Expected 50 primes, got {data['count']}"
    assert data["sum"] == 5117, f"Expected sum 5117, got {data['sum']}"
    assert data["max"] == 229, f"Expected max 229, got {data['max']}"
    assert data["primes"][0] == 2
    assert data["primes"][-1] == 229
    assert len(data["primes"]) == 50

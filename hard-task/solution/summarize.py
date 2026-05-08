import json
from pathlib import Path

primes = [int(line) for line in Path("/tmp/primes.txt").read_text().splitlines() if line.strip()]

result = {
    "count": len(primes),
    "sum": sum(primes),
    "max": max(primes),
    "primes": primes,
}

Path("/app/result.json").write_text(json.dumps(result, indent=2))

"""Run the public demo dataset against the live API and print a compact quality report."""

import json
import math
import os
import statistics
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.getenv("API_URL", "http://localhost:8000")
DATASET = Path(__file__).resolve().parents[1] / "demo" / "questions.json"


def post(path, data, token=None, form=False):
    body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(BASE + path, data=body, headers=headers), timeout=15) as response:
        return json.load(response)


def main():
    env_file = DATASET.parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    cases = json.loads(DATASET.read_text())
    correct_citations = 0
    answerable = 0
    correct_abstentions = 0
    unanswerable = 0
    latencies = []
    cost = 0.0
    failures = []
    for case in cases:
        password = os.environ[f"{case['role'].upper()}_PASSWORD"]
        token = post("/api/login", {"username": case["role"], "password": password}, form=True)["access_token"]
        result = post("/api/ask", {"question": case["question"]}, token)
        latencies.append(result["latency_ms"])
        cost += result["estimated_cost_usd"]
        if case["abstain"]:
            unanswerable += 1
            passed = result["abstained"] and not result["citations"]
            correct_abstentions += passed
        else:
            answerable += 1
            passed = (not result["abstained"] and case["expected_answer"] in result["answer"]
                      and any(c["title"] == case["expected_document"] and c["section"] == case["expected_section"]
                              and c["quote"] == result["answer"] for c in result["citations"]))
            correct_citations += passed
        print(f"{'PASS' if passed else 'FAIL'}  {case['role']:8} {case['question']}")
        if not passed:
            failures.append(case["question"])
    ordered = sorted(latencies)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    print(f"\nCitation correctness: {correct_citations}/{answerable}")
    print(f"Correct abstentions: {correct_abstentions}/{unanswerable}")
    print(f"Latency: mean {statistics.mean(latencies):.1f} ms, p95 {p95:.1f} ms")
    print(f"Estimated total cost: ${cost:.6f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

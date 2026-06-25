"""Smoke test for the demo Scene 2 questions.

Hits the running RAG API over HTTP (default http://localhost:9000) and:
  1. Asks the star question, asserts the top-5 chunks include PRICELIST-2026-Q2
     and SOP-SHIP-004 (the two sources required by Part C Scene 2).
  2. Asks the honesty question, prints the top scores for review.
  3. Asks a price question in CLIENT mode, expects 0 chunks (visibility filter
     works — no CLIENT docs mention prices).

Run inside the container:
    docker compose exec rag-api python -m app.scripts.smoke_query
"""

from __future__ import annotations

import json
import os
import sys
from urllib import request

BASE_URL = os.environ.get("RAG_API_URL", "http://localhost:9000")
STAR_QUESTION = (
    "A client wants to ship a 20ft container from Lae to Port Moresby "
    "— what do I quote and what documents do I need?"
)
HONESTY_QUESTION = "What was the Q1 2026 revenue for Steamships Hospitality division?"
CLIENT_PRICE_QUESTION = "What discount can a contract customer get on FCL 40ft shipments?"

REQUIRED_STAR_SOURCES = {"PRICELIST-2026-Q2", "SOP-SHIP-004"}


def _post(payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{BASE_URL}/api/retrieve",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:  # noqa: S310 — controlled URL
        return json.loads(resp.read().decode("utf-8"))


def _print_top(label: str, resp: dict, n: int = 5) -> None:
    print(f"\n=== {label} ===")
    print(f"Question: {resp['question']}")
    print(f"Mode:     {resp['mode']}")
    print(f"Top {n} chunks:")
    for i, chunk in enumerate(resp["chunks"][:n], start=1):
        print(
            f"  {i}. [{chunk['score']:.4f}] {chunk['doc_id']} — {chunk['doc_name']}"
            f"  ({chunk['section']})"
        )


def main() -> int:
    print(f"RAG API base URL: {BASE_URL}")

    # 1) Star question.
    star_resp = _post({"question": STAR_QUESTION, "mode": "STAFF", "top_k": 5})
    _print_top("Star question (Demo Scene 2)", star_resp)
    star_doc_ids = {c["doc_id"] for c in star_resp["chunks"]}
    missing = REQUIRED_STAR_SOURCES - star_doc_ids
    if missing:
        print(f"FAIL: star question top-5 missing required sources: {sorted(missing)}")
        return 1
    print("PASS: star question returns both required sources in top-5.")

    # 2) Honesty question — print scores, reviewer eyeballs.
    honesty_resp = _post({"question": HONESTY_QUESTION, "mode": "STAFF", "top_k": 5})
    _print_top("Honesty question (out of corpus)", honesty_resp)
    honesty_top = honesty_resp["chunks"][:1]
    honesty_top_score = honesty_top[0]["score"] if honesty_top else 0.0
    star_top_score = star_resp["chunks"][0]["score"] if star_resp["chunks"] else 0.0
    print(f"Star top score:    {star_top_score:.4f}")
    print(f"Honesty top score: {honesty_top_score:.4f}")
    if honesty_top_score >= star_top_score:
        print("WARN: honesty question scored >= star question — review embeddings.")
    else:
        print("PASS: honesty question scores lower than star question (no relevant corpus).")

    # 3) Visibility filter — CLIENT mode must only see CLIENT-visibility chunks
    #    (never SOPs / PRICELIST / POLICIES / DIRECTORY / VESSEL SCHEDULE).
    client_resp = _post({"question": CLIENT_PRICE_QUESTION, "mode": "CLIENT", "top_k": 5})
    _print_top("Client mode — contract discount question (visibility filter check)", client_resp)
    staff_only_doc_ids = {
        "SOP-SHIP-001", "SOP-SHIP-004", "SOP-SHIP-007",
        "SOP-PROP-002", "SOP-HOSP-003", "SOP-FIN-005", "SOP-HR-001",
        "SOP-CRM-001", "SOP-OPS-006",
        "PRICELIST-2026-Q2",
        "POLICY-DATA-001", "POLICY-CONDUCT-001",
        "DIRECTORY-2026", "VESSEL-SCHED-Q2-2026",
    }
    leaked = {c["doc_id"] for c in client_resp["chunks"]} & staff_only_doc_ids
    if leaked:
        print(f"FAIL: CLIENT mode leaked STAFF-only documents: {sorted(leaked)}")
        return 1
    if not client_resp["chunks"]:
        print("PASS: CLIENT mode returns zero chunks for that question.")
    else:
        returned = {c["doc_id"] for c in client_resp["chunks"]}
        print(f"PASS: CLIENT mode returned only CLIENT-visibility chunks: {sorted(returned)}")

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

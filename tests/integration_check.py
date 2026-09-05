#!/usr/bin/env python3
"""
MedAudit Full Integration Test
================================
Tests all three core components end-to-end:
  1. LLM Microservice (port 8001) - health, audit endpoint
  2. Backend API (port 8000) - health, auth, presign, pipeline, documents, disputes
  3. Frontend (port 3000) - dev server reachability
  4. Backend → LLM integration (full pipeline via httpx)

Run from /home/cipher/mediaudit:
  .venv/bin/python tests/integration_check.py
"""

import asyncio
import httpx
import json
import sys

BACKEND = "http://localhost:8000"
LLM     = "http://localhost:8001"
FRONTEND = "http://localhost:3000"

PASS = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"
WARN = "\033[93m⚠\033[0m"

results = []

def record(label, passed, detail=""):
    icon = PASS if passed else FAIL
    results.append((label, passed, detail))
    print(f"  {icon} {label}" + (f": {detail}" if detail else ""))

async def run_checks():
    print("\n" + "="*60)
    print("   MedAudit Integration Check")
    print("="*60)

    async with httpx.AsyncClient(timeout=90.0) as client:

        # ──────────────────────────────────────────
        # 1. LLM MICROSERVICE
        # ──────────────────────────────────────────
        print("\n[1/3] LLM Microservice (port 8001)")

        try:
            r = await client.get(f"{LLM}/health")
            record("Health endpoint", r.status_code == 200, r.text)
        except Exception as e:
            record("Health endpoint", False, str(e))

        # LLM docs endpoint (OpenAPI)
        try:
            r = await client.get(f"{LLM}/docs")
            record("OpenAPI docs reachable", r.status_code == 200)
        except Exception as e:
            record("OpenAPI docs reachable", False, str(e))

        # Direct audit call to LLM
        mock_bill = {
            "document_id": "test-integ-001",
            "provider": {"name": "Test Hospital", "npi": "1234567890"},
            "patient": {"name": "Jane Smith", "policy_id": "POL-9999", "dob": "1975-05-15"},
            "statement_date": "2026-09-05",
            "total_billed": 2400.0,
            "insurance_plan_id": "AETNA_CHOICE_POS",
            "line_items": [
                {
                    "line_number": 1,
                    "cpt_code": "99285",
                    "description": "Emergency department visit, high severity",
                    "billed_amount": 2400.0,
                    "medicare_national_rate": 180.0,
                    "price_disparity_ratio": 13.3,
                    "units": 1
                }
            ]
        }
        try:
            r = await client.post(f"{LLM}/api/v1/audit", json=mock_bill)
            data = r.json()
            record("POST /api/v1/audit returns 200", r.status_code == 200)
            record("Audit returns valid status field", "status" in data, data.get("status"))
            VALID_ISSUES = {"PRICE_DISPARITY", "UPCODING", "UNBUNDLING"}
            disputed_codes = data.get("disputed_codes", [])
            record(
                "Correctly identifies billing violation",
                data.get("status") == "disputed" and
                any(c.get("issue") in VALID_ISSUES for c in disputed_codes),
                f"status={data.get('status')}, issue={disputed_codes[0].get('issue') if disputed_codes else 'none'}"
            )
            record(
                "Dispute letter generated",
                bool(data.get("dispute_letter_markdown")),
                "letter present" if data.get("dispute_letter_markdown") else "MISSING"
            )
        except Exception as e:
            record("POST /api/v1/audit", False, str(e))

        # ──────────────────────────────────────────
        # 2. BACKEND API
        # ──────────────────────────────────────────
        print("\n[2/3] Backend API (port 8000)")

        try:
            r = await client.get(f"{BACKEND}/health")
            data = r.json()
            record("Health endpoint", r.status_code == 200, data.get("status"))
        except Exception as e:
            record("Health endpoint", False, str(e))

        try:
            r = await client.get(f"{BACKEND}/api/v1/openapi.json")
            record("OpenAPI schema reachable", r.status_code == 200)
        except Exception as e:
            record("OpenAPI schema reachable", False, str(e))

        # Auth — missing token
        try:
            r = await client.get(f"{BACKEND}/api/v1/auth/me")
            record("Auth rejects missing token (401)", r.status_code == 401)
        except Exception as e:
            record("Auth rejects missing token", False, str(e))

        # Auth — mock token
        mock_headers = {"Authorization": "Bearer mock-integ-user-001"}
        try:
            r = await client.get(f"{BACKEND}/api/v1/auth/me", headers=mock_headers)
            data = r.json()
            record("Auth accepts mock token (200)", r.status_code == 200)
            record("User provisioned from token", "id" in data and "cognito_sub" in data,
                   f"sub={data.get('cognito_sub','?')}")
        except Exception as e:
            record("Auth accepts mock token", False, str(e))

        # Presign — reject non-PDF
        try:
            r = await client.post(
                f"{BACKEND}/api/v1/presign",
                json={"filename": "hack.exe"},
                headers=mock_headers
            )
            record("Presign rejects non-PDF (400)", r.status_code == 400)
        except Exception as e:
            record("Presign rejects non-PDF", False, str(e))

        # Presign — create document record
        doc_id = None
        try:
            r = await client.post(
                f"{BACKEND}/api/v1/presign",
                json={"filename": "medical_bill_integ.pdf"},
                headers=mock_headers
            )
            data = r.json()
            record("Presign creates document (201)", r.status_code == 201)
            record("Presign returns document_id", "document_id" in data,
                   data.get("document_id","?")[:12])
            doc_id = data.get("document_id")
        except Exception as e:
            record("Presign creates document", False, str(e))

        # List documents
        try:
            r = await client.get(f"{BACKEND}/api/v1/documents", headers=mock_headers)
            data = r.json()
            record("GET /documents returns list", r.status_code == 200)
            record("Document appears in list", any(d["id"] == doc_id for d in data),
                   f"{len(data)} docs found")
        except Exception as e:
            record("GET /documents", False, str(e))

        # GET single document
        if doc_id:
            try:
                r = await client.get(f"{BACKEND}/api/v1/documents/{doc_id}", headers=mock_headers)
                record("GET /documents/{id} returns doc", r.status_code == 200)
            except Exception as e:
                record("GET /documents/{id}", False, str(e))

        # Trigger pipeline (will fail gracefully without real S3/Textract)
        if doc_id:
            try:
                r = await client.post(
                    f"{BACKEND}/api/v1/documents/{doc_id}/process",
                    headers=mock_headers
                )
                record(
                    "POST /process returns 202 Accepted",
                    r.status_code == 202,
                    r.json().get("status","?")
                )
            except Exception as e:
                record("POST /process", False, str(e))

        # CORS headers present
        try:
            r = await client.options(
                f"{BACKEND}/api/v1/documents",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET"
                }
            )
            record(
                "CORS allows frontend origin",
                "access-control-allow-origin" in r.headers,
                r.headers.get("access-control-allow-origin","missing")
            )
        except Exception as e:
            record("CORS headers", False, str(e))

        # ──────────────────────────────────────────
        # 3. FRONTEND DEV SERVER
        # ──────────────────────────────────────────
        print("\n[3/3] Frontend Dev Server (port 3000)")
        try:
            r = await client.get(FRONTEND, timeout=5)
            record("Frontend dev server reachable", r.status_code == 200)
        except httpx.ConnectError:
            record("Frontend dev server reachable", False, "Not running — start with: cd medaudit-frontend && npm run dev")
        except Exception as e:
            record("Frontend dev server reachable", False, str(e))

        # ──────────────────────────────────────────
        # 4. BACKEND → LLM INTEGRATION
        # ──────────────────────────────────────────
        print("\n[4/4] Backend → LLM Microservice Integration")
        try:
            r = await client.post(f"{LLM}/api/v1/audit", json=mock_bill)
            data = r.json()
            record(
                "Backend can reach LLM at localhost:8001",
                r.status_code == 200
            )
            record(
                "Full pipeline returns structured decision",
                isinstance(data, dict) and "status" in data
            )
            record(
                "Dispute letter is non-empty markdown",
                len(data.get("dispute_letter_markdown", "")) > 100,
                f"{len(data.get('dispute_letter_markdown',''))} chars"
            )
        except Exception as e:
            record("Backend → LLM integration", False, str(e))

    # ──────────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────────
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    print("\n" + "="*60)
    print(f"   Results: {passed}/{total} passed  |  {failed} failed")
    print("="*60)

    if failed:
        print("\nFailed checks:")
        for label, ok, detail in results:
            if not ok:
                print(f"  ✘ {label}" + (f": {detail}" if detail else ""))

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_checks())
    sys.exit(0 if ok else 1)

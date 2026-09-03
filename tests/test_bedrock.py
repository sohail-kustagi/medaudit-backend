import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.services.bedrock_service import run_bedrock_audit

mock_bill = {
  "provider": {"name": "Test Hospital", "npi": "1234567890", "tax_id": "XX-XXXXXXX"},
  "patient": {"name": "John Doe", "policy_id": "999-00-1111", "dob": "1980-01-01"},
  "statement_date": "2026-09-04",
  "line_items": [
    {
      "cpt_code": "99285",
      "description": "Emergency department visit, high severity",
      "billed_amount": 3500.00,
      "medicare_national_rate": 180.00,
      "price_disparity_ratio": 19.4
    }
  ]
}

async def test():
    print("Testing OpenAI-compatible Proxy integration...")
    try:
        result = await run_bedrock_audit(mock_bill)
        print("Success! Agent output:")
        print(result)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())

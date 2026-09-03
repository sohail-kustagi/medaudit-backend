import re
from typing import Any, Dict, List, Optional, Tuple
from backend.app.schemas.bill import (
    BillingLineItem,
    PatientInfo,
    ProviderInfo,
    StructuredBill,
)

# Regex patterns
CPT_REGEX = re.compile(r"\b([0-9]{4}[0-9A-Za-z])\b")
CURRENCY_REGEX = re.compile(r"[\$]?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)")
NPI_REGEX = re.compile(r"\b([0-9]{10})\b")


def parse_money_value(text: str) -> Optional[float]:
    """Extracts floating point monetary value from raw text (e.g. '$1,450.50' -> 1450.50)."""
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
    match = re.search(r"[-+]?\d*\.\d+|\d+", cleaned)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def get_block_text(block: Dict[str, Any], block_map: Dict[str, Any]) -> str:
    """Recursively retrieves concatenated text for a given block's children."""
    text_pieces = []
    if "Relationships" in block:
        for rel in block["Relationships"]:
            if rel["Type"] == "CHILD":
                for child_id in rel["Ids"]:
                    child_block = block_map.get(child_id)
                    if child_block:
                        if child_block["BlockType"] == "WORD":
                            text_pieces.append(child_block.get("Text", ""))
                        elif child_block["BlockType"] == "SELECTION_ELEMENT":
                            if child_block.get("SelectionStatus") == "SELECTED":
                                text_pieces.append("X")
    return " ".join(text_pieces).strip()


def extract_key_value_pairs(blocks: List[Dict[str, Any]]) -> Dict[str, str]:
    """Extracts form key-value pairs from Textract KEY_VALUE_SET blocks."""
    block_map = {b["Id"]: b for b in blocks}
    key_blocks = {}
    value_blocks = {}

    for b in blocks:
        if b["BlockType"] == "KEY_VALUE_SET":
            entity_types = b.get("EntityTypes", [])
            if "KEY" in entity_types:
                key_blocks[b["Id"]] = b
            elif "VALUE" in entity_types:
                value_blocks[b["Id"]] = b

    kv_pairs = {}
    for key_id, key_block in key_blocks.items():
        key_text = get_block_text(key_block, block_map).lower().replace(":", "").strip()
        value_text = ""

        # Follow VALUE relationship
        if "Relationships" in key_block:
            for rel in key_block["Relationships"]:
                if rel["Type"] == "VALUE":
                    for val_id in rel["Ids"]:
                        val_block = value_blocks.get(val_id)
                        if val_block:
                            value_text = get_block_text(val_block, block_map).strip()

        if key_text:
            kv_pairs[key_text] = value_text

    return kv_pairs


def extract_tables(blocks: List[Dict[str, Any]]) -> List[List[List[str]]]:
    """Reconstructs 2D cell grids for each TABLE block found in Textract output."""
    block_map = {b["Id"]: b for b in blocks}
    tables = []

    table_blocks = [b for b in blocks if b["BlockType"] == "TABLE"]
    for t_block in table_blocks:
        cell_grid: Dict[int, Dict[int, str]] = {}
        max_row = 0
        max_col = 0

        if "Relationships" in t_block:
            for rel in t_block["Relationships"]:
                if rel["Type"] == "CHILD":
                    for child_id in rel["Ids"]:
                        cell_block = block_map.get(child_id)
                        if cell_block and cell_block["BlockType"] == "CELL":
                            r = cell_block.get("RowIndex", 1) - 1
                            c = cell_block.get("ColumnIndex", 1) - 1
                            max_row = max(max_row, r)
                            max_col = max(max_col, c)
                            text = get_block_text(cell_block, block_map)

                            if r not in cell_grid:
                                cell_grid[r] = {}
                            cell_grid[r][c] = text

        table_data = []
        for r in range(max_row + 1):
            row_data = []
            for c in range(max_col + 1):
                row_data.append(cell_grid.get(r, {}).get(c, ""))
            table_data.append(row_data)

        if table_data:
            tables.append(table_data)

    return tables


def structure_bill(textract_response: Dict[str, Any]) -> StructuredBill:
    """
    Parses raw Amazon Textract Blocks into a normalized StructuredBill object.
    Combines KEY_VALUE_SET extraction for headers and TABLE extraction for line items.
    """
    blocks = textract_response.get("Blocks", [])
    kv = extract_key_value_pairs(blocks)
    tables = extract_tables(blocks)

    # 1. Parse Patient Information
    patient_name = (
        kv.get("patient name")
        or kv.get("patient")
        or kv.get("name")
        or kv.get("member name")
    )
    dob = (
        kv.get("dob")
        or kv.get("date of birth")
        or kv.get("birth date")
    )
    policy_id = (
        kv.get("policy id")
        or kv.get("policy #")
        or kv.get("member id")
        or kv.get("insurance id")
        or kv.get("group #")
    )
    account_number = (
        kv.get("account #")
        or kv.get("account number")
        or kv.get("invoice #")
        or kv.get("bill #")
    )

    patient_info = PatientInfo(
        name=patient_name,
        dob=dob,
        policy_id=policy_id,
        account_number=account_number,
    )

    # 2. Parse Provider Information
    provider_name = (
        kv.get("provider")
        or kv.get("hospital")
        or kv.get("facility")
        or kv.get("facility name")
        or kv.get("billing provider")
    )
    npi = kv.get("npi") or kv.get("provider npi")
    if not npi and provider_name:
        npi_match = NPI_REGEX.search(provider_name)
        if npi_match:
            npi = npi_match.group(1)

    provider_info = ProviderInfo(
        name=provider_name,
        npi=npi,
        tax_id=kv.get("tax id") or kv.get("ein"),
        phone=kv.get("phone") or kv.get("telephone"),
    )

    # 3. Statement / Due Dates
    statement_date = kv.get("statement date") or kv.get("bill date") or kv.get("date")
    due_date = kv.get("due date") or kv.get("payment due")

    # 4. Parse Line Items from Tables
    line_items: List[BillingLineItem] = []
    line_number = 1

    for table in tables:
        if len(table) < 2:
            continue

        # Detect Header Row
        header_row_idx = 0
        header_text = " ".join(table[0]).lower()
        if not ("code" in header_text or "cpt" in header_text or "charge" in header_text or "desc" in header_text):
            if len(table) > 2 and ("code" in " ".join(table[1]).lower() or "charge" in " ".join(table[1]).lower()):
                header_row_idx = 1

        headers = [h.lower().strip() for h in table[header_row_idx]]

        # Map column indices
        col_code = next((i for i, h in enumerate(headers) if "code" in h or "cpt" in h or "hcpcs" in h), None)
        col_desc = next((i for i, h in enumerate(headers) if "desc" in h or "service" in h or "procedure" in h), None)
        col_charge = next((i for i, h in enumerate(headers) if "charge" in h or "amount" in h or "fee" in h or "total" in h), None)
        col_units = next((i for i, h in enumerate(headers) if "unit" in h or "qty" in h), None)
        col_dos = next((i for i, h in enumerate(headers) if "date" in h or "dos" in h), None)

        for row_idx in range(header_row_idx + 1, len(table)):
            row = table[row_idx]
            row_str = " ".join(row).strip()
            if not row_str or "total" in row_str.lower() and col_charge is not None:
                continue

            # Extract fields
            cpt_code = None
            if col_code is not None and col_code < len(row):
                code_text = row[col_code].strip()
                cpt_match = CPT_REGEX.search(code_text)
                if cpt_match:
                    cpt_code = cpt_match.group(1)

            # If CPT wasn't in explicit code column, search entire row
            if not cpt_code:
                cpt_match = CPT_REGEX.search(row_str)
                if cpt_match:
                    cpt_code = cpt_match.group(1)

            desc = ""
            if col_desc is not None and col_desc < len(row):
                desc = row[col_desc].strip()
            if not desc:
                desc = row_str

            billed_amount = 0.0
            if col_charge is not None and col_charge < len(row):
                val = parse_money_value(row[col_charge])
                if val is not None:
                    billed_amount = val

            units = 1
            if col_units is not None and col_units < len(row):
                try:
                    units = int(row[col_units].strip())
                except (ValueError, TypeError):
                    units = 1

            dos = None
            if col_dos is not None and col_dos < len(row):
                dos = row[col_dos].strip()

            # Only add if has meaningful charge or CPT code
            if billed_amount > 0 or cpt_code:
                line_items.append(
                    BillingLineItem(
                        line_number=line_number,
                        cpt_code=cpt_code,
                        description=desc,
                        units=units,
                        billed_amount=billed_amount,
                        date_of_service=dos,
                        raw_text=row_str,
                    )
                )
                line_number += 1

    # Total Billed Calculation
    total_billed = 0.0
    total_from_kv = (
        parse_money_value(kv.get("total amount due"))
        or parse_money_value(kv.get("total charges"))
        or parse_money_value(kv.get("total due"))
        or parse_money_value(kv.get("balance due"))
    )
    if total_from_kv is not None and total_from_kv > 0:
        total_billed = total_from_kv
    else:
        total_billed = sum(item.billed_amount for item in line_items)

    return StructuredBill(
        patient=patient_info,
        provider=provider_info,
        statement_date=statement_date,
        due_date=due_date,
        total_billed=round(total_billed, 2),
        line_items=line_items,
    )

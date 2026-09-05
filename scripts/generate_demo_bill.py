#!/usr/bin/env python3
"""
Generate a realistic demo medical bill PDF for MedAudit testing.
Intentionally includes billing issues the LLM agent should detect:
  - CPT 99285: Billed $3,850 vs $180 Medicare baseline (PRICE_DISPARITY/UPCODING)
  - CPT 80053 + 80048 + 84443: Unbundled panel (UNBUNDLING)
  - CPT 71046: Chest X-ray $940 vs $52 (PRICE_DISPARITY)
  - CPT 93000: ECG $445 vs $18.05 (PRICE_DISPARITY)

Usage:
  .venv/bin/python scripts/generate_demo_bill.py
  Output: tests/fixtures/demo_medical_bill.pdf
"""

from fpdf import FPDF, XPos, YPos
import os

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "tests", "fixtures", "demo_medical_bill.pdf"
)


class MedicalBillPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(160, 160, 160)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def info_box(pdf, x, y, w, h, label, lines):
    pdf.set_fill_color(245, 248, 252)
    pdf.set_draw_color(200, 210, 220)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, w, h, "FD")
    pdf.set_xy(x + 3, y + 3)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(w - 6, 5, label)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    for i, line in enumerate(lines):
        pdf.set_xy(x + 3, y + 10 + i * 5)
        pdf.cell(w - 6, 5, line)


def generate():
    pdf = MedicalBillPDF(orientation="P", unit="mm", format="Letter")
    pdf.add_page()
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)

    # Header bar
    pdf.set_fill_color(30, 58, 95)
    pdf.rect(0, 0, 216, 32, "F")

    pdf.set_xy(20, 6)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "VALLEY GENERAL HOSPITAL", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(20, 18)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(180, 200, 230)
    pdf.cell(
        0, 6,
        "1200 Medical Center Drive, Austin, TX 78701  |  NPI: 1234567890  |  TAX ID: 74-1234567  |  (512) 555-0100"
    )

    # Title
    pdf.ln(16)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 8, "PATIENT BILLING STATEMENT", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(
        0, 5,
        "Please retain this statement for your records. This is NOT a check.",
        align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.ln(4)

    # Info boxes
    info_box(pdf, 20, 68, 82, 45, "PATIENT INFORMATION", [
        "Name:          John Michael Doe",
        "Date of Birth: January 01, 1980",
        "Account #:     VGH-20260901-00421",
        "Policy ID:     999-00-1111",
        "Member ID:     AET-80053812",
    ])

    info_box(pdf, 108, 68, 82, 45, "INSURANCE INFORMATION", [
        "Insurer:       Aetna Choice POS II",
        "Plan ID:       AETNA_CHOICE_POS",
        "Group #:       TX-CORP-88821",
        "Claim #:       AET-2026-09-881923",
        "Auth #:        Not Required",
    ])

    info_box(pdf, 20, 118, 82, 30, "PROVIDER INFORMATION", [
        "Attending:     Dr. Sarah K. Patel, MD",
        "Department:    Emergency Medicine",
        "Facility NPI:  1234567890",
    ])

    info_box(pdf, 108, 118, 82, 30, "STATEMENT DETAILS", [
        "Statement Date: September 05, 2026",
        "Date of Service: September 01, 2026",
        "Due Date:       October 05, 2026",
    ])

    pdf.set_y(155)
    pdf.ln(4)

    # Line items table header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(255, 255, 255)
    pdf.set_fill_color(30, 58, 95)

    col_widths = [22, 72, 14, 28, 28]
    headers = ["CPT Code", "Description", "Units", "Billed Amount", "Expected Rate"]
    for i, h in enumerate(headers):
        align = "R" if i >= 3 else "L"
        last = i == len(headers) - 1
        pdf.cell(
            col_widths[i], 8, h, border=0, align=align, fill=True,
            new_x=XPos.LMARGIN if last else XPos.RIGHT,
            new_y=YPos.NEXT if last else YPos.TOP,
        )

    line_items = [
        ("99285", "Emergency Dept Visit - High Medical Decision Complexity", "1", "$3,850.00", "$180.00"),
        ("71046", "Chest X-Ray, 2 Views (PA and Lateral)", "1", "$940.00", "$52.00"),
        ("80053", "Comprehensive Metabolic Panel (CMP)", "1", "$310.00", "$14.53"),
        ("80048", "Basic Metabolic Panel (BMP)", "1", "$260.00", "$11.37"),
        ("84443", "Thyroid Stimulating Hormone (TSH) Assay", "1", "$195.00", "$24.44"),
        ("93000", "ECG - Routine, with Interpretation", "1", "$445.00", "$18.05"),
    ]

    pdf.set_font("Helvetica", "", 8.5)
    for idx, (code, desc, units, billed, expected) in enumerate(line_items):
        fill = idx % 2 == 0
        pdf.set_fill_color(247, 250, 254) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(col_widths[0], 7, code,  border=0, align="L", fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(col_widths[1], 7, desc,  border=0, align="L", fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(col_widths[2], 7, units, border=0, align="L", fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(180, 30, 30)
        pdf.cell(col_widths[3], 7, billed, border=0, align="R", fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(40, 120, 40)
        pdf.cell(col_widths[4], 7, expected, border=0, align="R", fill=fill, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 8.5)

    # Separator
    pdf.set_draw_color(30, 58, 95)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(2)

    # Totals
    totals = [
        ("Total Billed Charges:",         "$6,000.00",  False),
        ("Insurance Adjustment (Est.):",  "-$4,685.32", False),
        ("Coinsurance (20%):",            "$262.93",    False),
        ("Previous Balance:",             "$0.00",      False),
        ("AMOUNT DUE:",                   "$262.93",    True),
    ]

    x_label = 110
    x_value = 165
    for label, value, bold in totals:
        pdf.set_x(x_label)
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        pdf.set_text_color(30, 58, 95 if bold else 60)
        pdf.cell(50, 6, label, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_x(x_value)
        pdf.cell(25, 6, value, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(6)

    # Notice box
    pdf.set_fill_color(255, 248, 230)
    pdf.set_draw_color(220, 160, 30)
    pdf.set_line_width(0.4)
    pdf.set_x(20)
    notice_y = pdf.get_y()
    pdf.rect(20, notice_y, 170, 22, "FD")
    pdf.set_xy(24, notice_y + 3)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(150, 90, 0)
    pdf.cell(0, 5, "BILLING NOTICE - PLEASE REVIEW CAREFULLY")
    pdf.set_xy(24, notice_y + 9)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(100, 70, 0)
    pdf.multi_cell(
        162, 4,
        "Charges for CPT 99285, 71046, 80053, 80048, and 84443 may contain discrepancies relative to "
        "CMS Medicare national rates. Patients have the right to request an itemized review under the "
        "No Surprises Act (42 CFR 300gg-111). Contact billing at (512) 555-0199."
    )

    pdf.ln(8)

    # Payment
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 6, "PAYMENT OPTIONS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(
        0, 5,
        "Online: pay.valleygeneralhospital.org   |   Phone: (512) 555-0100   |   Mail: PO Box 1200, Austin TX 78701",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )

    # Footer bar
    pdf.set_fill_color(30, 58, 95)
    pdf.rect(0, 265, 216, 12, "F")
    pdf.set_xy(20, 267)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(160, 185, 220)
    pdf.cell(
        0, 5,
        "Valley General Hospital | HIPAA Privacy Notice available at valleygeneralhospital.org/privacy | Questions? (512) 555-0100"
    )

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    pdf.output(OUTPUT_PATH)
    print(f"Demo bill generated: {OUTPUT_PATH}")
    print("")
    print("  Intentional billing issues for the LLM to detect:")
    print("  CPT 99285 - PRICE_DISPARITY/UPCODING : $3,850 billed vs $180 Medicare (21.4x)")
    print("  CPT 71046 - PRICE_DISPARITY           : $940   billed vs $52  Medicare (18.1x)")
    print("  CPT 93000 - PRICE_DISPARITY           : $445   billed vs $18  Medicare (24.7x)")
    print("  CPT 80053 - UNBUNDLING                : $310   billed (should be bundled panel)")
    print("  CPT 80048 - UNBUNDLING                : $260   billed (included in CMP)")
    print("  CPT 84443 - UNBUNDLING                : $195   billed (included in CMP)")


if __name__ == "__main__":
    generate()

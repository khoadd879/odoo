"""Regression checks for the Day 5 Bill of Lading parser."""

from __future__ import annotations

import importlib.util
import sys
import types

if importlib.util.find_spec("pytesseract") is None:
    sys.modules["pytesseract"] = types.SimpleNamespace(image_to_string=lambda _page: "")

if importlib.util.find_spec("fastapi") is None:
    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        def post(self, *args, **kwargs):
            return lambda fn: fn

    class HTTPException(Exception):
        pass

    fastapi.FastAPI = FastAPI
    fastapi.File = lambda *args, **kwargs: None
    fastapi.HTTPException = HTTPException
    fastapi.UploadFile = object
    sys.modules["fastapi"] = fastapi

if importlib.util.find_spec("PIL") is None:
    pil = types.ModuleType("PIL")
    pil.Image = object
    sys.modules["PIL"] = pil

from main import extract_bill_of_lading, summarise


SAMPLE_RAW_OCR_TEXT = """
OCEAN BILL OF LADING
B/LNO
ABC1201TYO-001

SHIPPER
General Goods Export Co, Ltd.

CONSIGNEE
Global Business Ltd

NOTIFY PARTY
Same as Consignee

Vessel
AAATHAILAND V.1000N

Port of Loading
BANGKOK, THAILAND

Place of Acceptance
BANGKOK, THAILAND

Port of Discharge (8) _ Final Distination Place of Delivery (Q) Freight and charges payable at
TOKYO, JAPAN TOKYO, JAPAN TOKYO, JAPAN BANGKOK

B/L signed at Bangkok Mar 10, 2018

Marks and Number and we Weight Measurement
Numbers. Type of Packages | Description of goods KGS Me

Case Mark 3,000 CARTONS
TOKYO/JAPAN

3,000 CARTONS.

1 x 40'HO SAID TO CONTAIN
SHAMPOO F 600m!
SHAMPOO U 600ml

12,335kg | 21.80CBM

437kg

HS CODE : 3307.30.00

Invoice No : GGE10001

Date
Ist March, 2018

“SHIPPER LOAD & COUNT”

Container Nos.
BB883000000 / MOL 200001N

Freight Prepaid

Delivery Agent
EXEL JAPAN INC.
"""


EXPECTED_FIELDS = {
    "bl_number": "ABC1201TYO-001",
    "shipper": "General Goods Export Co, Ltd.",
    "consignee": "Global Business Ltd",
    "notify_party": "Same as Consignee",
    "vessel_name": "AAA THAILAND",
    "voyage_number": "V.1000N",
    "port_of_loading": "Bangkok, Thailand",
    "port_of_discharge": "Tokyo, Japan",
    "place_of_acceptance": "Bangkok, Thailand",
    "place_of_delivery": "Tokyo, Japan",
    "container_numbers": "BB883000000, MOL 200001N",
    "document_date": "Mar 10, 2018",
    "weight": "12,335 kg",
    "measurement": "21.80 CBM",
    "freight_terms": "Freight Prepaid",
    "delivery_agent": "EXEL JAPAN INC.",
    "cargo_description": "3,000 CARTONS. 1 x 40' HQ SAID TO CONTAIN SHAMPOO F 600ml SHAMPOO U 600ml. HS CODE: 3307.30.00.",
    "reference_invoice_number": "GGE10001",
}


def test_bill_of_lading_sample_fields() -> None:
    fields, confidences = extract_bill_of_lading(SAMPLE_RAW_OCR_TEXT)
    for key, expected in EXPECTED_FIELDS.items():
        assert fields.get(key) == expected, f"{key}: expected {expected!r}, got {fields.get(key)!r}"
    assert "GGE10001" not in fields["cargo_description"]

    _overall, notes = summarise(fields, confidences)
    assert notes in ("", "Please review extracted fields before approval.")
    assert "place of delivery" not in notes.lower()
    assert "cargo description" not in notes.lower()


if __name__ == "__main__":
    test_bill_of_lading_sample_fields()
    print("B/L parser regression test passed")

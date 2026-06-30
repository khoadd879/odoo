"""Smoke checks for vision_ai merge logic — run with: python test_vision_ai.py

No frameworks. Exits 0 on success, non-zero on the first failed assertion.
"""

from __future__ import annotations

import os
import sys

# Force-disable Vision AI so import-time config doesn't pollute the run.
os.environ.setdefault("VISION_AI_ENABLED", "false")
os.environ.setdefault("GEMINI_API_KEY", "")

# Allow running from inside the service dir without packaging.
sys.path.insert(0, os.path.dirname(__file__))

from vision_ai import (  # noqa: E402
    fields_needing_ai,
    merge_ai_corrections,
)


def t_needs():
    fields = {
        "bl_number": "ZZ-123",
        "shipper": "",  # empty -> need
        "consignee": "Consignee Co.",  # high -> no
        "vessel_name": "unreadable",  # placeholder -> need
        "voyage_number": "v.999",  # medium -> need (priority field)
        "port_of_loading": "TOKYO",  # high
        "port_of_discharge": "n/a",  # placeholder -> need
        "container_numbers": "AAAU1234567",  # high
        "weight": "@@@",  # placeholder -> need
        "document_date": "01/02/2026",  # high
    }
    confs = {
        "bl_number": "high",
        "shipper": "low",
        "consignee": "high",
        "vessel_name": "low",
        "voyage_number": "medium",
        "port_of_loading": "high",
        "port_of_discharge": "low",
        "container_numbers": "high",
        "weight": "low",
        "document_date": "high",
    }
    needed = set(fields_needing_ai(fields, confs, fields.keys()))
    expected = {"shipper", "vessel_name", "voyage_number", "port_of_discharge", "weight"}
    assert needed == expected, f"needed={needed}, expected={expected}"
    print("ok: fields_needing_ai")


def t_merge_overwrites_only_weak():
    fields = {
        "bl_number": "ZZ-123",          # high - never overwritten
        "shipper": "",                  # empty - overwritten
        "vessel_name": "unreadable",    # placeholder - overwritten
        "voyage_number": "v.999",       # medium - overwritten for priority keys
        "port_of_discharge": "",        # empty - overwritten
        "container_numbers": "AAAU1234567",  # high - kept
    }
    confs = {k: "low" for k in fields}
    confs["bl_number"] = "high"
    confs["container_numbers"] = "high"
    ai = {
        "bl_number": "DIFFERENT-999",          # should NOT be applied
        "shipper": "Real Shipper Co.",
        "vessel_name": "AAA THAILAND",
        "voyage_number": "V.1000N",
        "port_of_discharge": "TOKYO, JAPAN",
        "container_numbers": "OVERRIDE-XYZ",   # should NOT be applied (high)
        "unknown_key": "ignored",
    }
    new_fields, new_confs, merged = merge_ai_corrections(
        dict(fields), dict(confs), ai, fields.keys()
    )
    assert new_fields["bl_number"] == "ZZ-123", "high-confidence field got clobbered"
    assert new_fields["shipper"] == "Real Shipper Co."
    assert new_fields["vessel_name"] == "AAA THAILAND"
    assert new_fields["voyage_number"] == "V.1000N"
    assert new_fields["port_of_discharge"] == "TOKYO, JAPAN"
    assert new_fields["container_numbers"] == "AAAU1234567", "high confidence container number got clobbered"
    assert new_confs["shipper"] == "high"
    assert new_confs["vessel_name"] == "high"
    assert sorted(merged) == ["port_of_discharge", "shipper", "vessel_name", "voyage_number"], merged
    print("ok: merge_ai_corrections")


def t_merge_skips_empty_ai():
    fields = {"shipper": "", "vessel_name": ""}
    confs = {"shipper": "low", "vessel_name": "low"}
    ai = {"shipper": "", "vessel_name": "   "}
    new_fields, new_confs, merged = merge_ai_corrections(fields, confs, ai, fields.keys())
    assert merged == [], f"empty AI values should not merge; got {merged}"
    assert new_fields == {"shipper": "", "vessel_name": ""}
    print("ok: merge_ai_corrections skips empty corrections")


def t_invalid_value_replaced():
    fields = {"vendor_name": "$$$$$"}  # mostly punctuation -> invalid
    confs = {"vendor_name": "low"}
    ai = {"vendor_name": "Real Vendor Co."}
    new_fields, _, merged = merge_ai_corrections(fields, confs, ai, fields.keys())
    assert merged == ["vendor_name"]
    assert new_fields["vendor_name"] == "Real Vendor Co."
    print("ok: merge_ai_corrections replaces invalid value")


if __name__ == "__main__":
    t_needs()
    t_merge_overwrites_only_weak()
    t_merge_skips_empty_ai()
    t_invalid_value_replaced()
    print("all vision_ai tests passed")

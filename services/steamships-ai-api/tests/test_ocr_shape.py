"""Verify the OCR endpoints return the strict JSON shapes from the spec."""

from __future__ import annotations

from fastapi.testclient import TestClient


BL_REQUIRED_KEYS = {
    "bl_number",
    "shipper",
    "consignee",
    "notify_party",
    "vessel_name",
    "voyage_number",
    "container_numbers",
    "port_of_loading",
    "port_of_discharge",
    "cargo_description",
    "weight",
    "date",
    "confidence",
}


def _upload(client: TestClient, path: str) -> "requests.Response":  # type: ignore[name-defined]
    with open(path, "rb") as fh:
        return client.post(
            "/api/ocr/bill-of-lading",
            files={"file": ("sample.bin", fh, "application/octet-stream")},
        )


def test_bill_of_lading_returns_required_keys(
    client: TestClient, tmp_path
) -> None:
    fake = tmp_path / "bl.pdf"
    fake.write_bytes(b"%PDF-1.4\n%fake\n%%EOF")
    r = _upload(client, str(fake))
    assert r.status_code == 200, r.text
    body = r.json()
    assert BL_REQUIRED_KEYS.issubset(body.keys()), body
    # All fields are nullable in the stub.
    assert body["bl_number"] is None
    assert body["container_numbers"] == []
    assert body["confidence"] == {}


def test_invoice_returns_not_implemented_status(client: TestClient, tmp_path) -> None:
    fake = tmp_path / "inv.pdf"
    fake.write_bytes(b"%PDF-1.4\n%fake\n%%EOF")
    with open(fake, "rb") as fh:
        r = client.post(
            "/api/ocr/invoice",
            files={"file": ("inv.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "not_implemented"

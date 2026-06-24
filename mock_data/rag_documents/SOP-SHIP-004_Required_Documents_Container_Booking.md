# SOP-SHIP-004 — Required Documents for Container Booking

**Document ID:** SOP-SHIP-004
**Version:** 4.0
**Effective Date:** 2026-05-15
**Owner:** Shipping Compliance Lead — John Kaupa
**Approved by:** Head of Shipping — Margaret Vele
**Visibility:** STAFF ONLY

---

## 1. Purpose

List every document the shipping operations team must collect from a client before a container booking can be confirmed and the vessel loaded. Prevents customs holds, demurrage charges, and rejected Bills of Lading.

## 2. Mandatory documents — FCL booking (any route)

The following documents MUST be in the client's CRM record and attached to the booking before the documentation cut-off:

1. **Commercial Invoice** — original, signed by shipper, showing goods description, unit price, total value, currency, and INCOTERMS 2020 term.
2. **Packing List** — detailed item-by-item breakdown: quantity per package, package type, weight, dimensions, total packages.
3. **Export Permit** (where commodity is regulated: logs, fish, minerals, coffee) — issued by relevant PNG government authority.
4. **KYC Pack** — already approved in CRM (one-time per client; verify expiry).
5. **Letter of Authority** — if a freight forwarder is booking on the client's behalf.
6. **Dangerous Goods Declaration** (SOP-SHIP-007) — if cargo is IMO classified.

## 3. Mandatory documents — LCL booking

Same as FCL plus:

- **Cargo manifest** with each consignment marked separately (must reconcile with the master packing list).
- **Weight certificate** from a certified weighbridge (within 30 days of vessel sailing).

## 4. Reefer containers (perishable cargo)

Additional documents required:

- **Phytosanitary certificate** (for agricultural products)
- **Temperature log agreement** signed by shipper (set point, tolerance, ventilation)
- **Pre-cooling confirmation** from the depot

## 5. How to verify documents

Before confirming a booking, the Sales Coordinator must:

1. Open the client's CRM record (steamships_demo_crm.partner).
2. Check the "Onboarding" tab — KYC status must be "Approved" (not "In Progress" or "Pending").
3. Open the "Documents" tab — verify each mandatory document is attached with a clear file name and a valid date.
4. For export permits: cross-check the permit number against the issuing authority's online register (links in the SOP library).
5. Flag any missing item to the Sales Manager BEFORE confirming space with the vessel.

## 6. Common errors to avoid

- Accepting a "draft" invoice — only signed originals are valid.
- Skipping KYC check because the client is "well known" — every booking, every time.
- Treating the Letter of Authority as optional when a forwarder is involved — never optional.
- Missing the export permit for logs, coffee, or fish — these are the most-cited reasons for customs holds in 2025.

## 7. What to do if documents are incomplete

- DO NOT confirm space with the vessel.
- Email the client the missing-items checklist (auto-generated from Odoo).
- Log a 24-hour follow-up activity in Odoo with the client contact.
- If documents remain incomplete at cut-off time, cancel the booking per SOP-SHIP-001 Section 5.

## 8. References

- SOP-SHIP-001 — Container booking procedure
- SOP-SHIP-007 — Dangerous goods declaration
- CRM Onboarding Checklist (8 KYC items)

---

*End of SOP-SHIP-004*

# SOP-CRM-001 — Client Onboarding Procedure

**Document ID:** SOP-CRM-001
**Version:** 2.5
**Effective Date:** 2026-04-01
**Owner:** Head of Sales Operations — Peter Laga
**Visibility:** STAFF ONLY

---

## 1. Purpose

Define the single, end-to-end onboarding flow for every new client of Steamships Trading Company. Replaces the previous 3 different forms (one per legacy company) with one standardised process.

## 2. Why this matters

In 2025, the Head of Strategy reported a real incident: a client registration document was lost and the client had to redo it. That must not happen again. This SOP ensures:

- ONE form instead of THREE
- All documents attached to the CRM record forever
- Full audit trail in the Odoo chatter (who did what, when)

## 3. Onboarding workflow

| Step | Action | Owner | SLA |
|------|--------|-------|-----|
| 1 | Client submits the public onboarding web form | Client | — |
| 2 | System auto-creates CRM lead + partner record | Odoo automation | < 30 seconds |
| 3 | System auto-creates 24-hour follow-up activity | Odoo automation | Instant |
| 4 | Salesperson reviews lead, attaches any missing documents | Sales | 24 hours |
| 5 | Salesperson starts "KYC" wizard in CRM | Sales | 24 hours |
| 6 | Client submits KYC pack (8 items) | Client | 7 days |
| 7 | Compliance team reviews KYC | Compliance | 3 working days |
| 8 | State transitions: Draft → KYC In Progress → KYC Approved | Sales | After step 7 |
| 9 | CRM lead stage advances to "Qualified" | Odoo | Automatic |
| 10 | Salesperson schedules onboarding meeting | Sales | Within 7 days |

## 4. Onboarding web form fields

The client-facing form collects:

| Field | Type | Required |
|-------|------|----------|
| Company name | text | Yes |
| Contact person | text | Yes |
| Email | email | Yes |
| Phone | text | Yes |
| Country | selection (default PNG) | Yes |
| Industry | selection (Logistics / Property / Hospitality / Joint Venture) | Yes |
| Service needed | multi-select | Yes |
| File uploads | multiple attachments | Optional but recommended |

## 5. KYC checklist (8 items)

Once the client record is created, the Salesperson opens the KYC wizard and the client provides:

1. IPA Certificate of Incorporation
2. IRC Tax Identification Number (TIN)
3. Bank reference letter
4. Director ID copies (front + back)
5. PEP (Politically Exposed Person) screening consent
6. Credit check consent
7. Insurance certificate (where applicable)
8. Signed standard terms

Each item is YES/NO in Odoo; the wizard computes a `completion_pct` percentage.

## 6. Lead stage transitions

```
New → Lead → Qualified → Onboarding Docs → Quoted → Won / Lost
```

The stage transitions automatically when:

- "Qualified" → all 8 KYC items = YES
- "Onboarding Docs" → KYC state = approved
- "Quoted" → first quotation sent to client
- "Won" → quotation confirmed by client
- "Lost" → quotation rejected OR no response in 30 days

## 7. References

- SOP-HR-001 — New hire onboarding (for staff who assist clients)
- SOP-FIN-005 — Tenant credit check (Property clients)
- SOP-SHIP-001 — Container booking (Shipping clients)

---

*End of SOP-CRM-001*

# POLICY-DATA-001 — Data Handling and Classification Policy

**Document ID:** POLICY-DATA-001
**Version:** 2.0
**Effective Date:** 2026-01-01
**Owner:** Group CIO — Henry Moke
**Visibility:** STAFF ONLY

---

## 1. Purpose

Define how Steamships Trading Company classifies, stores, shares, and disposes of information assets. Ensures compliance with the PNG Data Protection Act 2024 and AS/NZS ISO 27001 controls.

## 2. Data classification

All company information is classified into one of FOUR levels:

| Level | Label | Examples | Who can access |
|-------|-------|----------|----------------|
| 1 | PUBLIC | Marketing brochures, published price lists (where applicable), website content | Anyone |
| 2 | INTERNAL | Most policies, general company information, training material | All staff |
| 3 | CONFIDENTIAL | Client data, pricing details, KYC documents, sales forecasts, contracts | Authorised staff only (need-to-know basis) |
| 4 | RESTRICTED | Board papers, M&A documents, employee medical records, security incidents | Named individuals only |

## 3. Marking

- Level 1: no marking required.
- Level 2: footer "Internal — Steamships Trading Company".
- Level 3: footer "Confidential" + watermark.
- Level 4: footer "Restricted" + serial number, stored in encrypted location.

## 4. Storage

- Level 1: public website, public file shares.
- Level 2-3: Odoo document management system; one drive per division.
- Level 4: encrypted vault; access logged and reviewed quarterly.

## 5. Sharing with external parties

- Level 1: share freely (with marketing approval).
- Level 2: share with confidentiality wording if appropriate.
- Level 3: only with signed NDA; recipient listed in Odoo.
- Level 4: requires CIO sign-off in writing.

## 6. AI chatbot data rules

When using the Steamships AI Chatbot (RAG-based):

- DO NOT paste Level 4 (Restricted) content into the chatbot.
- Level 3 content may be summarised by the chatbot if the user has CONFIDENTIAL clearance.
- Client data may be referenced (the chatbot searches the document library) but never pasted into a query.
- All chatbot interactions are logged in Odoo chatter for audit purposes.

## 7. Retention

| Data class | Retention |
|------------|-----------|
| Client records (Level 3) | 7 years after last transaction |
| Employee records (Level 3) | 7 years after end of employment |
| Financial records (Level 3) | 10 years (regulatory requirement) |
| Board papers (Level 4) | Permanent (archive) |
| Marketing material (Level 1) | Until superseded |

## 8. Disposal

- Paper: cross-cut shredder, then secure bin collection.
- Electronic: secure erase (DoD 5220.22-M or equivalent); for tapes, degauss and physically destroy.
- Cloud: follow provider's certified data destruction process.

## 9. Incident reporting

Any suspected data breach must be reported within 4 hours to the CIO (cio@steamships.com.pg) and the Group Risk Officer. External regulator (PNG Information Commissioner) must be notified within 72 hours if personal data is involved.

## 10. References

- PNG Data Protection Act 2024
- AS/NZS ISO 27001
- Code of Conduct policy

---

*End of POLICY-DATA-001*

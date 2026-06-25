# Steamships Day 3 — RAG Mock Data

> Source plan: `docs/Steamships Odoo Prototype Plan.md` Part B4 (Day 3 — RAG pipeline)
> Scope: 17 mock documents for the AI chatbot vector store
> Demo scene: Part C Scene 2 ("Ask the AI, quote in 90 seconds — THE STAR")
> Created: 2026-06-24

## What's in here

This directory holds the **fake company documents** that the Day 3 RAG chatbot will ingest, embed, and search when staff (or clients) ask questions.

Documents are split by **visibility** for the two chatbot modes (per ai-architecture-gap.md §3.4):

- **STAFF mode** (default, the demo star): SOPs, internal price list, policies, vessel schedule, key contacts directory.
- **CLIENT mode** (cut-able per plan B7): FAQ, services catalog, glossary. NO prices, NO SOPs.

## File list

| # | File | Visibility | Used for demo question |
|---|------|------------|------------------------|
| 1 | SOP-SHIP-001 — Container Booking Procedure | STAFF | "How do I book a container?" |
| 2 | **SOP-SHIP-004 — Required Documents** | **STAFF** | **"What documents for 20ft Lae -> POM?"** |
| 3 | SOP-SHIP-007 — Dangerous Goods Declaration | STAFF | DG cargo questions |
| 4 | SOP-PROP-002 — Commercial Lease | STAFF | Property questions |
| 5 | SOP-HOSP-003 — Hotel Group Booking | STAFF | Hospitality questions |
| 6 | SOP-FIN-005 — Tenant Credit Check | STAFF | Property/finance questions |
| 7 | SOP-HR-001 — New Hire Onboarding | STAFF | HR questions |
| 8 | SOP-CRM-001 — Client Onboarding | STAFF | Onboarding questions |
| 9 | SOP-OPS-006 — LCL Consolidation Warehouse | STAFF | Warehouse/LCL questions |
| 10 | **PRICELIST 2026 Q2** | **STAFF** | **"What price for 20ft Lae -> POM?"** |
| 11 | FAQ — Client Onboarding | CLIENT | Client-mode FAQ |
| 12 | POLICY-DATA-001 — Data Classification | STAFF | Data policy questions |
| 13 | POLICY-CONDUCT-001 — Code of Conduct | STAFF | Ethics questions |
| 14 | CATALOG — Services Summary | CLIENT | "What services do you offer?" |
| 15 | DIRECTORY — Key Contacts | STAFF | "Who do I contact for...?" |
| 16 | VESSEL SCHEDULE Q2 2026 | STAFF | "When is the next vessel?" |
| 17 | GLOSSARY — Steamships Terms | CLIENT | Acronym / term questions |
| - | MANIFEST_ingestion_metadata.json | — | Ingestion metadata for the pipeline |

## Demo question → expected answer

The Plan Part C Scene 2 says the demo will type this question live:

> *"A client wants to ship a 20ft container from Lae to Port Moresby — what do I quote and what documents do I need?"*

The chatbot should return:

1. **Price**: PGK 4,500 (from PRICELIST 2026 Q2 §1.1 — FCL 20ft Lae → POM)
2. **Documents**: Commercial Invoice, Packing List, Export Permit (if regulated), KYC pack, Letter of Authority (if forwarder), DGD (if DG) — from SOP-SHIP-004 §2
3. **Source citations**: "PRICELIST-2026-Q2" and "SOP-SHIP-004"
4. **Honesty test** (Scene 2 honesty moment): ask something not in the docs (e.g. "Q1 2026 Hospitality revenue?") — bot must say "I do not know, please ask the CFO" rather than guess.

## How to ingest (Day 3 — separate task)

The ingestion pipeline (separate from this mock data work) will:

1. Load each `.md` file from `rag_documents/`.
2. Split into 500-1000 character chunks with 100-char overlap.
3. Create embeddings (Anthropic `voyage-3` if API key set, else deterministic hash for mock).
4. Store in Chroma or pgvector with metadata from `MANIFEST_ingestion_metadata.json`.

## Notes for the developer building the pipeline

- Visibility filter: when building the retriever, filter `metadata['visibility']` against the user's mode. STAFF mode can see everything; CLIENT mode only sees files where `visibility == "CLIENT"`.
- The DOCX system prompt (B4): *"Answer ONLY from the provided documents. If the answer is not in the documents, say you do not know and name a person/team to ask. Always cite your sources."*
- For the honesty test, include in the prompt: "If the answer is not in the provided documents, respond with: 'I do not know, please ask the [appropriate team] team.'"
- Always include at least the top 3 source chunks in the LLM context; cap at 5 to avoid blowing the token budget.
- Return `{answer, sources: [{name, section, score}]}` so the UI can render source chips.

---

*End of README*

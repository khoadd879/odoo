**ODOO PROTOTYPE PROJECT**

Steamships Trading Company — Digital Transformation Demo

*1-Week Build Plan for the Development Team*

This document has 3 parts:

**Part A — The Problems We Are Fixing (the story and context)**

**Part B — Technical Instructions (what to build, step by step)**

**Part C — The Presentation (what the demo must show)**

June 2026  •  Confidential — Internal Use Only

# **PART A — The Problems We Are Fixing**

Read this part first. It explains WHO the client is, WHAT is going wrong, and WHY we are building this demo. If you understand the problems, you will build the right thing.

## **A1. Who is the client?**

Steamships Trading Company is one of the biggest companies in Papua New Guinea (PNG). It started in 1918 and has about 3,000 staff. It is listed on two stock exchanges (Australia and Port Moresby), so it must follow strict rules.

It runs many businesses across 4 main areas:

* **1\.** Shipping and Logistics — about 20 ships (the Consort fleet), visiting 17 ports, with over 8,000 containers. Also tug boats (Pacific Towing) and port services.

* **2\.** Property — buildings they rent out: offices, shops, warehouses, and homes.

* **3\.** Hotels and Hospitality — hotels, restaurants, and bars.

* **4\.** Joint Ventures (JVs) — over 20 part-owned businesses with partners, like Colgate Palmolive PNG (50% owned).

Important: Steamships recently BOUGHT OUT its shipping vendors and partners. This means several companies that used to be separate are now one big group. They all have different prices, different forms, different computer systems, and different ways of working. Gluing them together is the heart of this project.

## **A2. The problems (told to us by the Head of Strategy & Transformation)**

### **Problem 1 — New staff make basic mistakes**

The company is hiring a lot of people very fast. The Head of Strategy said roughly: out of every 10 new hires, only 2 are great. The other 8 make basic errors, mostly in accounting and documents (typing wrong numbers, missing steps, wrong paperwork).

**What this means for us:** We are not trying to replace people. We are building AI helpers that catch mistakes, fill in forms automatically, and answer staff questions correctly — so even a new hire can do the job right.

### **Problem 2 — There is NO CRM (no customer system at all)**

Today, the sales team manages clients using only email and messaging apps. There is no single place that shows: who the client is, what they asked for, what documents they sent, and what stage the deal is at.

**Real story they told us:** A client filled in a registration document. It got LOST. The company had to ask the client to fill it in again. This was embarrassing and made the company look unprofessional.

### **Problem 3 — The merged companies do not fit together**

Because Steamships bought several companies, things are messy:

* A new client can be asked to fill 3 different onboarding forms on different platforms that track different things.

* Some steps are still on paper or in someone's inbox, so things get lost.

* Each old company has its own prices, formats, and ways of communicating.

* Sales and Business Development (BD) teams cannot work together smoothly.

### **Problem 4 — Nobody is sure what price to quote**

Salespeople do not have one trusted price list they can check any time, day or night. Different teams quote different prices for the same service. This loses money and confuses clients.

### **Problem 5 — Booking meetings across time zones is painful**

Clients are in different countries. Finding a meeting time means lots of back-and-forth emails. They want a smart booking system connected to Google Calendar that finds free slots automatically and shows times in the client's own time zone.

### **Problem 6 — Too much paperwork (shipping is document-heavy)**

Shipping runs on documents: invoices and Bills of Lading (a B/L is the official paper that travels with cargo — it says what is being shipped, by whom, to whom, and on which ship). Staff type these into computers by hand. It is slow and full of errors.

**Their wish:** Use AI vision (AI that can read photos and scans) to read these documents automatically, fill in the system, and let a human just check and approve. This is called 'human in the loop'.

### **Nice-to-have ideas (NOT in this 1-week build)**

* AI note-taker that joins meetings, writes summaries, finds follow-ups, and checks if staff follow company rules (SOPs).

* AI proposal and pitch-deck maker.

* AI layer that moves all the OLD data from the old systems into the new one with no manual work. (Be honest with the client: this is a big future project, not a 1-week job.)

## **A3. What we are building and what we are NOT building**

**We ARE building:** a working DEMO (prototype) in 7 days, on one Odoo system, using sample/fake data. It must look real, work live on screen, and prove the idea.

**We are NOT building:** the final production system. No real company data, no full security setup, no data migration, no PNG tax setup. Those come later, in Phase 2, if the demo wins approval.

## **A4. The 5 things we will build (and why these 5\)**

We picked these 5 because they fix the loudest problems AND look impressive in a live demo:

| \# | What we build | Problem it fixes | Wow factor |
| :---- | :---- | :---- | :---- |
| 1 | One CRM \+ one client onboarding form | Lost documents, 3 different forms, no client system | Medium (but it is the foundation) |
| 2 | One trusted price list \+ instant quote maker | Sales don't know what to quote | High |
| 3 | AI chatbot that knows the company (RAG) | New staff making basic errors; client onboarding questions | Highest — the star of the demo |
| 4 | AI document reader (invoices \+ B/L) with human check | Manual typing errors, document-heavy work | Very high — feels like magic |
| 5 | Smart meeting booking with time zones \+ Google Calendar | Painful meeting scheduling | High, and easiest to build |

**Glossary (simple meanings):**

* CRM \= Customer Relationship Management. One system that remembers everything about every client.

* ERP \= Enterprise Resource Planning. One system that runs the whole business (money, stock, staff, sales). Odoo is both a CRM and an ERP.

* RAG \= Retrieval-Augmented Generation. A way to make an AI chatbot answer using the COMPANY'S OWN documents, not just general knowledge — and show where the answer came from.

* B/L \= Bill of Lading. The official shipping paper for cargo.

* OCR / AI Vision \= software that reads text from photos and scanned papers.

* Human in the loop \= the AI does the work, but a person checks and approves before anything is final.

* SOP \= Standard Operating Procedure. The company's official 'how to do this task' instructions.

# **PART B — Technical Instructions for the Developer**

This part tells you exactly what to set up and build, day by day. Where possible, use Odoo's built-in features (configuration) instead of writing code. Write custom code only where Odoo cannot do it alone (the AI parts).

## **B1. Tools and setup**

| Item | Choice | Why |
| :---- | :---- | :---- |
| Odoo version | Odoo 18 Enterprise (free trial on Odoo.sh or odoo.com) | Enterprise includes invoice OCR, Appointments, and Studio. Community edition would add 2-3 days of extra work. |
| AI model API | Anthropic Claude API (or OpenAI as backup) | For the chatbot (text) and document reading (vision). Budget USD 20-50 for the whole demo. |
| Middleware / glue | Python (FastAPI) or n8n | Small service that connects Odoo to the AI APIs. |
| Vector database | Chroma or pgvector (both free) | Stores the company documents so the chatbot can search them (the RAG part). |
| Calendar | Google Calendar API (OAuth) | Odoo has a native Google Calendar connector — mostly configuration. |
| Demo data | Fake/sample data only | Sample clients, sample price list, 3-5 sample scanned B/L documents, 10-20 sample SOP documents. |

**Rule for the whole week:** build the demo path first, polish later. Every feature only needs to work for the demo script in Part C. Do not gold-plate.

## **B2. Feature 1 — One CRM \+ one client onboarding form (Day 1\)**

Goal: a client fills ONE web form. A client record appears in the CRM with all their documents attached. Nothing can get lost.

### **Build steps**

1. Install Odoo apps: CRM, Sales, Website, Documents.

2. Create the sales pipeline stages: Lead → Qualified → Onboarding Docs → Quoted → Won / Lost.

3. Build one public onboarding form (Odoo Website form builder) with fields: company name, contact person, email, phone, country, industry (dropdown: Logistics / Property / Hospitality / Joint Venture), service needed (dropdown), file upload (multiple files allowed).

4. Make key fields REQUIRED so an incomplete form cannot be submitted.

5. When the form is submitted: auto-create a CRM lead, attach all uploaded files to that lead, auto-assign a salesperson, and auto-create an activity reminder: 'Check documents within 24 hours'.

6. Add a document checklist on the client record (can be a simple custom field set via Studio): Registration form (yes/no), KYC documents (yes/no), Signed terms (yes/no).

### **Done when**

* Submitting the form creates a lead with files attached, visible in the pipeline, in under 5 seconds.

* The record shows the full history (who did what, when) in the Odoo chatter/log.

## **B3. Feature 2 — One price list \+ instant quote maker (Day 2\)**

Goal: a salesperson builds a correct, branded quote in under 2 minutes, using one trusted price list.

### **Build steps**

1. Create a product catalog with sample services grouped by division. Examples: 'Container FCL 20ft, Lae → Port Moresby', 'Container FCL 40ft, Lae → Port Moresby', 'LCL per cubic metre', 'Stevedoring per move', 'Warehouse storage per day', 'Office lease per square metre per month'.

2. Set up price lists: Standard price, Contract-customer price (e.g. 10% lower), JV-partner price. Currencies: PGK (PNG Kina) and USD.

3. Make a clean branded quotation PDF template (company name, logo placeholder, payment terms).

4. Show profit margin on quote lines for INTERNAL view only (never on the client PDF).

5. Add an approval rule: any discount above 10% needs manager approval before the quote can be sent (Odoo Sales settings).

### **Done when**

* A salesperson can pick a client, add 3 services from dropdowns, and email a branded PDF quote — all in under 2 minutes, live on screen.

* A 15% discount gets blocked and asks for manager approval (show this in the demo — bosses love control features).

## **B4. Feature 3 — AI company chatbot with RAG (Days 3-4) — THE SHOWPIECE**

Goal: a chat window where staff ask questions in normal language and get correct answers based on the COMPANY'S OWN documents, with the source shown.

### **Build steps — Day 3 (the brain)**

1. Collect 10-20 sample documents: SOPs (make realistic fakes, e.g. 'SOP-SHIP-004: Required documents for container booking'), the price list exported from Odoo, an onboarding checklist, an FAQ, a company policy or two.

2. Build the ingestion pipeline: split documents into chunks (about 500-1,000 characters each), create embeddings, store them in Chroma/pgvector with the document name and section as metadata.

3. Build the answer endpoint (FastAPI): take the user's question → find the 5 most relevant chunks → send question \+ chunks to the AI model → return the answer PLUS the source names (e.g. 'Source: SOP-SHIP-004').

4. Write the system prompt carefully: 'Answer ONLY from the provided documents. If the answer is not in the documents, say you do not know and name a person/team to ask. Always cite your sources.' This honesty rule is what makes it trustworthy.

### **Build steps — Day 4 (the face)**

1. Build a simple chat user interface. Easiest path: a standalone web page (simple HTML/JS) styled with company colours, or embed it in Odoo via an iframe / Odoo's website builder.

2. Add two modes with a toggle: STAFF mode (can see SOPs and internal prices) and CLIENT mode (onboarding help only — must NOT reveal internal prices or SOPs). For the demo, the toggle just switches which document set the bot searches.

3. Test with the exact demo questions (see Part C) and tune the prompt until the answers are correct and short.

### **Done when**

* Asking 'A client wants to ship a 20ft container from Lae to Port Moresby — what do I quote and what documents do I need?' returns the correct price, the correct document list, AND the source names.

* Asking something NOT in the documents makes the bot honestly say it does not know.

### **Honest limits to write on the slide**

* Demo only: no user login security yet, small document set, no access control per division. Production needs all of that (Phase 2).

## **B5. Feature 4 — AI document reader: invoices and Bills of Lading (Days 5-6)**

Goal: upload a scanned document → AI reads it and fills in the fields → a human checks and approves. Two parts: (a) supplier invoices using Odoo's BUILT-IN tool, (b) Bills of Lading using a small custom build.

### **Part (a) — Supplier invoice OCR (Day 5 morning — configuration only)**

1. Turn on Odoo's built-in invoice digitisation (Accounting app → settings → Document Digitisation).

2. Upload 2-3 sample supplier invoices (PDF/photo). Odoo creates DRAFT bills with vendor, date, amounts pre-filled. A human reviews and posts. No code needed.

### **Part (b) — Custom Bill of Lading reader (Day 5 afternoon \+ Day 6\)**

1. Create a custom Odoo model using Studio: 'Bill of Lading'. Fields: B/L number, shipper, consignee, notify party, vessel name, voyage number, container number(s), port of loading, port of discharge, cargo description, weight, date, status (Draft / Pending Review / Approved), and the original file attachment.

2. Build the extraction endpoint: user uploads an image/PDF → middleware sends it to the AI vision API with a prompt asking for a strict JSON answer matching the fields above, plus a confidence score (high/medium/low) per field.

3. Write the extracted JSON into a new Bill of Lading record in Odoo (via Odoo's XML-RPC or JSON-RPC API), status \= 'Pending Review'.

4. Build the review screen: Odoo form view showing the extracted fields next to the original document image. Low-confidence fields should stand out (e.g. a warning tag or a 'check these fields' note). Reviewer fixes anything wrong and clicks Approve.

5. Prepare 3-5 sample B/L scans of mixed quality for the demo — include one slightly crumpled/skewed photo. When the AI still reads it correctly, that moment sells the whole feature.

### **Done when**

* Uploading a B/L photo produces a filled-in record in under 30 seconds, ready for one-click human approval.

* The demo can show the comparison: manual typing ≈ 12 minutes with errors vs AI ≈ 20 seconds plus a quick human check.

## **B6. Feature 5 — Smart meeting booking (Day 7 morning)**

Goal: a client clicks a link, sees free times in THEIR time zone, books a meeting, and it lands in Google Calendar and on the client's CRM record automatically.

### **Build steps**

1. Install the Odoo Appointments app.

2. Connect Google Calendar (Odoo's native connector, OAuth setup) for 2 demo users.

3. Create appointment types: 'Sales Call' (30 min) and 'Client Onboarding' (60 min), with working hours set to PNG time (GMT+10).

4. Confirm the booking page auto-detects the visitor's time zone (Odoo does this natively — test it by switching your browser/computer time zone to Singapore or Sydney).

5. Confirmation emails on, and each booking auto-logged as a meeting on the client's CRM record.

### **Done when**

* Booking from a 'Singapore' browser shows Singapore times, creates the event in the salesperson's Google Calendar, and appears on the CRM record.

## **B7. The 7-day timetable (one developer)**

| Day | Deliverable | Type of work |
| :---- | :---- | :---- |
| 1 | Odoo setup, branding, CRM pipeline, single onboarding form (Feature 1\) | Configuration |
| 2 | Product catalog, price lists, quote template, discount approval (Feature 2\) | Configuration \+ data entry |
| 3 | RAG pipeline: document ingestion, vector store, answer endpoint (Feature 3a) | Custom code |
| 4 | Chat UI, staff/client modes, prompt tuning (Feature 3b) | Custom code |
| 5 | Invoice OCR config \+ custom B/L model (Feature 4a \+ 4b start) | Config \+ Studio \+ code |
| 6 | Vision extraction \+ review screen \+ sample documents (Feature 4b finish) | Custom code |
| 7 | Appointments \+ Google Calendar (Feature 5), seed demo data, FULL demo rehearsal, fix what breaks | Config \+ testing |

**If you fall behind:** cut in this order — first drop the client-mode chatbot toggle, then drop the invoice OCR part (keep the B/L reader, it is flashier), then simplify the review screen. NEVER cut Features 1, 2, or the staff chatbot — they carry the demo story.

## **B8. Risks and honest warnings**

| Risk | What to do |
| :---- | :---- |
| Odoo Enterprise trial expires (15 days) | Start the trial only when the build starts. Keep a database backup. |
| AI gives a wrong answer live in the demo | Rehearse with the exact demo questions. The prompt must force 'I don't know' instead of guessing. |
| Google OAuth setup is fiddly | Do it early on Day 7 morning, not 1 hour before the demo. Test with both demo users. |
| Vision misreads a bad scan | Pre-test all 5 sample B/Ls. Use the worst one ONLY if it works reliably. |
| Confidential data questions from the client | Be ready to answer: demo uses fake data; production design will cover data residency, access rights, and security review in Phase 2\. |
| Internet drops during the demo (PNG connectivity) | Have a recorded screen video of the full demo as backup. Always. |

# **PART C — The Presentation: What the Demo Must Show**

The demo is a STORY, not a feature tour. Every step must match a problem the Head of Strategy personally told us. Total time: 20-25 minutes of demo plus questions.

## **C1. The golden rule**

For each step: first say the PROBLEM in their own words, then show the FIX live, then say the RESULT in numbers. Problem → Fix → Result. Never show a feature without first naming the pain it kills.

## **C2. The demo script (step by step)**

### **Opening (2 minutes)**

Say something like: 'You told us about lost client documents, three different onboarding forms, sales teams unsure what to quote, and new hires making basic errors. In the next 20 minutes we will show you one system, built in one week, that fixes every one of those — live, not slides.'

### **Scene 1 — The onboarding that cannot lose documents (4 min)**

* PROBLEM (say it): 'A client registration document went missing and the client had to redo it.'

* SHOW: open the single onboarding form on screen (ideally on a phone too). Fill it as a fake client, attach 2 files, submit.

* SHOW: switch to Odoo — the client instantly appears in the pipeline with both files attached and a 24-hour follow-up task already created.

* RESULT (say it): 'One form instead of three. Every document attached to the client forever. Full history of who did what. Nothing can go missing again.'

### **Scene 2 — Ask the AI, quote in 90 seconds (6 min) — THE STAR**

* PROBLEM: 'Sales are not sure what to quote. There is no single source of truth available 24/7. And 8 out of 10 new hires make basic errors.'

* SHOW: open the AI chatbot in STAFF mode. Type: 'A client wants to ship a 20ft container from Lae to Port Moresby. What price do I quote and what documents do I need?'

* The bot answers with the correct price, the document list, AND the sources (e.g. 'per SOP-SHIP-004'). Pause here. Let the room read it.

* SHOW honesty: ask the bot something it cannot know. It says 'I don't know, please ask X team.' Say: 'It never guesses. That is how it protects your new hires from errors.'

* SHOW: now build the actual quote in Odoo — pick the client from Scene 1, add the service from the price list, generate the branded PDF, email it. Time it openly: under 2 minutes.

* SHOW control: try a 15% discount — the system blocks it and asks for manager approval.

* RESULT: 'Any of your 3,000 staff can now get the right answer and the right price, day or night, with proof of where it came from.'

### **Scene 3 — The meeting books itself (3 min)**

* PROBLEM: 'Scheduling across time zones wastes days of back-and-forth.'

* SHOW: open the booking link in a browser set to Singapore time. The slots show in Singapore time automatically. Book one.

* SHOW: the meeting appears in the salesperson's Google Calendar AND on the client's CRM record.

* RESULT: 'Zero emails to schedule a call. Every meeting automatically remembered on the client's file.'

### **Scene 4 — The AI reads the paperwork (6 min) — THE MAGIC TRICK**

* PROBLEM: 'Shipping is document-heavy, and manual typing causes the accounting and documentation errors you mentioned.'

* SHOW: upload a photo of a scanned Bill of Lading — use the slightly crumpled one. Within \~20 seconds the fields fill themselves: shipper, consignee, vessel, container number, ports.

* SHOW human-in-the-loop: one field is flagged 'please check'. The reviewer fixes it and clicks Approve. Say: 'The AI does the typing; your people do the judging.'

* SHOW (quick): the built-in invoice OCR doing the same for a supplier invoice.

* RESULT: 'Twelve minutes of error-prone typing becomes twenty seconds plus a human check. Multiply that by every B/L and invoice you handle in a year.'

### **Closing — the road ahead (3 min)**

* Show ONE slide with Phase 2: AI meeting note-taker (connect an existing tool, with a consent policy), AI proposal/pitch-deck generator, AI-assisted migration of old data into the new system, and group-wide accounting consolidation across the JVs.

* Be honest: 'What you saw today is a prototype built in 7 days on sample data. Production needs security, access rights per division, real data migration, and PNG tax setup — that is the Phase 2 program.'

* Ask for the decision: 'If this direction is right, the next step is a scoping workshop with each division to plan Phase 1 of the real rollout.'

## **C3. What the audience should feel at each moment**

| Scene | Feeling we want | Their words we are answering |
| :---- | :---- | :---- |
| 1\. Onboarding | Relief | 'The registration doc went missing… embarrassing.' |
| 2\. AI bot \+ quote | Excitement / 'wow' | 'Sales not sure what to quote… 8 of 10 hires make errors AI can fix.' |
| 3\. Booking | 'Finally.' | 'Need time-zone synced AI calendar meetings.' |
| 4\. Document AI | Amazement | 'Very document heavy… AI vision… human in the loop.' |
| Closing | Trust (because we were honest) | 'No manual work to bring previous data over' — we tell them the truth about that. |

## **C4. Practical checklist for demo day**

* Rehearse the FULL demo at least twice the day before, with the exact questions and files.

* Record a screen video of the whole demo as a backup in case the internet fails.

* Seed the system with realistic-looking PNG sample data (real route names, PGK prices) — it makes the demo feel like THEIR company.

* Have the Phase 2 slide ready, and the honest-limits answers ready (fake data, no security hardening yet).

* Keep every scene under its time. If something breaks, switch to the backup video without apologising twice.

* End by asking for the next meeting (scoping workshop). A demo without an ask is just a show.

## **C5. Success \= these 4 outcomes**

1. The Head of Strategy says some version of 'I need this' or 'When can we start?'

2. At least one scene gets an audible reaction (usually Scene 2 or Scene 4).

3. Nobody in the room is confused about what is demo and what is Phase 2 — our honesty becomes a trust point.

4. We leave with a date for the scoping workshop.
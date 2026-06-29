# AGENTS.md — Rules for AI Coding Agents

This repository is an Odoo 19.0 Community development environment for the Steamships prototype.

The agent must follow these rules strictly.

## 1. Project boundaries

Only edit these areas unless explicitly told otherwise:

* `custom_addons/`
* `rag/`
* `mock_data/`
* `docs/`
* `scripts/`

Do not edit Odoo core files.

Do not edit cloned OCA repositories.

Do not edit files inside:

* `addons/oca/`
* `custom_addons/oca/`
* `odoo-data/`
* `postgres-data/`
* `chroma_data/`

If a task requires Odoo core behavior, create or update a custom addon that inherits the Odoo model/view/controller instead of modifying core code.

## 2. Odoo version and edition

Target:

* Odoo 19.0 Community
* PostgreSQL in Docker
* Custom addons mounted from the host
* RAG API as a separate FastAPI service

Do not use Odoo Enterprise-only features.

Do not use Odoo Studio.

Do not assume EE modules are available.

## 3. Addon rules

Every custom addon must be self-contained.

A normal addon structure should look like:

```text
custom_addons/<module_name>/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── *.py
├── controllers/
│   ├── __init__.py
│   └── *.py
├── security/
│   └── ir.model.access.csv
├── views/
│   └── *.xml
└── data/
    └── *.xml
```

Only create folders that are actually needed.

If a new model is created, always add:

* model Python file
* import in `models/__init__.py`
* import in addon `__init__.py`
* `security/ir.model.access.csv`
* manifest entry for the security file
* views/actions/menus only if needed

## 4. Manifest rules

Every `__manifest__.py` must be valid Python and must include:

* `name`
* `version`
* `summary`
* `license`
* `depends`
* `data`
* `installable`

Use `19.0.x.x.x` style versions.

Do not add dependencies unless the code really uses them.

Examples:

* Use `mail` only if inheriting `mail.thread` or posting chatter messages.
* Use `website` only if adding website pages/controllers/templates.
* Use `crm` only if extending `crm.lead`.
* Use `sale_management` only if extending sales quotations.

## 5. XML rules

For Odoo XML:

* Always wrap records in `<odoo>`.
* Use unique XML IDs.
* Do not reference fields that do not exist.
* Do not reference actions or menus before they are defined.
* Prefer simple tree/list/form views before adding complex UI.
* Do not add QWeb or JS unless required.

Before changing XML, check the model fields first.

## 6. Docker rules

Do not run:

```bash
docker compose down
docker compose down -v
docker compose up --build
docker system prune
```

unless the user explicitly asks.

For Odoo addon changes, use:

```bash
./scripts/update-module.sh <module_name>
```

For logs, use:

```bash
docker compose logs --tail=120 odoo
```

For RAG API changes, use:

```bash
docker compose restart rag-api
curl -fsS http://localhost:9000/api/healthz
```

Only rebuild Docker when Dockerfile, requirements, or system packages change.

## 7. Task size rules

One task must be small.

Good tasks:

* Add one field to one model.
* Add one button to one form.
* Add one controller route.
* Fix one XML error.
* Add one script.

Bad tasks:

* Build the whole Odoo AI CRM system.
* Rewrite the whole module.
* Refactor all Docker files and Odoo modules at once.
* Add CRM, OCR, RAG, pricing, and UI in one change.

## 8. Change rules

Before editing, state:

1. Files that will be changed.
2. Why those files need to change.
3. The test command.

After editing, state:

1. Files changed.
2. Summary of changes.
3. How to test.
4. Any risk or assumption.

Do not rewrite unrelated files.

Do not reformat large files unless the task is specifically to format them.

## 9. Debugging rules

When fixing an error:

* Read the exact error.
* Identify the root cause.
* Fix the minimum necessary lines.
* Do not rewrite the full module.
* Do not rename models, fields, or XML IDs unless required.

Common Odoo errors:

* Missing `ir.model.access.csv`
* Missing import in `__init__.py`
* XML references a field that does not exist
* Manifest does not include XML or CSV file
* Wrong dependency in `depends`
* Controller route auth/type mismatch
* External ID not found because XML record order is wrong

## 10. AI / RAG / OCR architecture

Do not put heavy AI logic inside Odoo modules.

Use this split:

* Odoo addon: UI, buttons, records, permissions, chatter, workflow
* FastAPI service in `rag/`: RAG, embeddings, LLM calls, OCR/vision, document extraction

Odoo can call FastAPI over HTTP.

Do not install LangChain, Chroma, or large ML dependencies into the Odoo container unless explicitly approved.

## 11. Steamships module plan

Use separate addons:

* `steamships_ai`: chat page and bridge to RAG API
* `steamships_bl`: Bill of Lading records, review workflow, OCR button
* `steamships_crm`: CRM lead extensions and onboarding checklist
* `steamships_pricing`: pricing/quote helpers and discount rules

Do not put all features into `steamships_ai`.

## 12. Final answer format

When completing a task, respond with:

```text
Changed files:
- path/to/file

What changed:
- ...

Test:
- command

Notes:
- ...
```

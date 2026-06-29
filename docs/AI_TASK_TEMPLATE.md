# AI Task Template

Use this template for every AI coding task.

## Task title

`<short task name>`

## Goal

Explain the goal in one or two sentences.

Example:

Create a basic Bill of Lading model in Odoo 18 Community that can be installed without errors.

## Scope

Allowed files:

```text
custom_addons/<module_name>/
```

Forbidden files:

```text
odoo core
addons/oca/
custom_addons/oca/
odoo-data/
postgres-data/
chroma_data/
```

## Rules

* Do not modify Odoo core.
* Do not modify OCA clones.
* Do not rebuild Docker.
* Do not run `docker compose down`.
* Make the smallest possible change.
* Do not rewrite unrelated files.
* Do not use Odoo Enterprise-only features.
* Do not use Studio.
* Keep AI/RAG/OCR heavy logic outside Odoo unless explicitly requested.

## Required checks before coding

Before editing, check:

* Which module is being changed?
* Does the module already have `__manifest__.py`?
* Does the module already import its Python files?
* Does a new model need `ir.model.access.csv`?
* Does XML reference only existing fields?
* Are dependencies declared correctly?

## Implementation request

Implement:

```text
<paste exact feature here>
```

## Expected result

After the change:

```text
<describe expected behavior>
```

## Test command

Use only this command for Odoo addon changes:

```bash
./scripts/update-module.sh <module_name>
```

Then inspect logs only if it fails:

```bash
docker compose logs --tail=120 odoo
```

## Response format

Return:

```text
Changed files:
- ...

What changed:
- ...

Test:
- ...

Risks / assumptions:
- ...
```

## Debug prompt

If the test fails, use this format:

```text
The module failed to upgrade.

Command:
./scripts/update-module.sh <module_name>

Error log:
<paste last 120 lines>

Fix only the root cause.
Do not rewrite the whole module.
Only edit the minimum necessary files.
```

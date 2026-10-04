# Research OS verification report

Verified locally on 2026-10-04 with Python 3.12:

```text
python -m unittest discover -s tests -v
Ran 11 tests ... OK

python scripts/verify_demo.py
status: PASS
entities: 51
relations: 55
```

The end-to-end verifier checks:

- SQLite migrations and foreign-key/integrity checks
- entity CRUD, revisions and idempotent demo seeding
- FTS/LIKE fallback search across title, notes and structured JSON
- graph traversal, backlinks and typed contradiction relations
- Markdown, HTML, Graph JSON and CSV exports
- SQLite online backup and restore with cardinality and integrity checks
- structured Paper, Claim, Experiment, Artifact and Question workflows

The fictional demo data is not an empirical scientific result.

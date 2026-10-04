# Research OS（个人科研操作系统）

Research OS is a local-first Windows desktop application for turning long-term research into a durable, inspectable knowledge graph. It is deliberately more structured than a notes editor: Papers, Claims, Evidence, Questions, Hypotheses, Experiments, Datasets, Artifacts, Results, Decisions, Ideas, Tasks and Daily Logs are first-class records connected by typed relations.

## What is included

- SQLite storage with numbered migrations, foreign-key checks, revision history and FTS5 search when available.
- A graph view with zoom, pan, type filters, relation filters, neighbor expansion and node inspection.
- Dedicated paper notes, claim ledger, experiment notebook, daily log and research timeline workflows.
- Local artifact links (folders, images, CSVs, model outputs, reports, PDFs and logs).
- Autosave, timestamped backup, restore, integrity check and recovery report.
- Export to Markdown archive, HTML report, graph JSON and CSV.
- A fictional **Agent Memory Research Demo** workspace with 5 papers, 10 claims, 3 hypotheses, 4 experiments, results and relations.
- Tests covering persistence, migrations, graph queries, search, export, integrity and backup/restore.

The repository includes a display-server-independent UI preview at
`screenshots/researchos_ui_preview.png`; the Windows build renders the same
layout as a native Tkinter window.

The demo is synthetic and is not a claim about the real world.

Verification notes are kept in `reports/TEST_REPORT.md` and
`reports/backup_recovery_report.json`.

## Run from source

```powershell
cd ResearchOS
py -3.11 -m researchos.app --demo
```

Or on any Python 3.11+ installation:

```bash
python -m researchos.app --demo
```

The first run creates a local workspace database under the platform's application-data directory (or the path supplied with `--workspace`). No network or paid model API is required.

## Build Windows executable

On Windows, install Python 3.11+ and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build_windows.ps1
```

The script runs the test suite, seeds a demo workspace, and creates `dist\ResearchOS\ResearchOS.exe` with PyInstaller. The build is intentionally reproducible on Windows rather than pretending that a Linux build is a Windows binary.

## Verification

```bash
python -m unittest discover -s tests -v
python scripts/verify_demo.py
```

## Data model

Each node is stored as a typed entity with a stable ID, structured JSON fields, content, timestamps and revisions. Edges are stored separately as unique directed typed relations. This means the provenance chain can be queried directly:

`Paper --SUPPORTS--> Claim --TESTED_BY--> Experiment --PRODUCES--> Result`

The database layer is intentionally UI-independent so the same workspace can later be used by command-line tools, importers or additional front ends.

## Safety and scope

Research OS is a personal research organization and experiment-tracking tool. It does not claim to predict society or validate scientific conclusions automatically. Contradictions are explicit, user-reviewable relations (`CONTRADICTS`, `NEEDS_VERIFICATION`), not hidden AI judgments.

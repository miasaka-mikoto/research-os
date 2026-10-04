# Research OS（个人科研操作系统）

Research OS is a local-first cross-platform research workspace for turning long-term research into a durable, inspectable knowledge graph. It is deliberately more structured than a notes editor: Papers, Claims, Evidence, Questions, Hypotheses, Experiments, Datasets, Artifacts, Results, Decisions, Ideas, Tasks and Daily Logs are first-class records connected by typed relations.

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
layout as a native Tkinter window. Linux has both a native GUI build and a
display-free JSON CLI for servers, containers and cloud-computer agents.

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

## Linux and cloud-agent mode

The storage layer and agent CLI do not import Tkinter. They run on Linux with
no X server, desktop session or GUI libraries. Every command emits one JSON
document and returns a non-zero exit code on failure, so an automation agent
can call it safely and pass the result to the next step.

```bash
# Python 3.11+; the workspace is created if it does not exist
python3 -m researchos.agent_cli init --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli demo --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli stats --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli search episodic --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli graph --entity paper-001 --depth 2 \
  --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli neighbors paper-001 --depth 2 \
  --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli export --output-dir /tmp/researchos-export \
  --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli integrity --workspace /tmp/researchos.sqlite3
python3 -m researchos.agent_cli backup --workspace /tmp/researchos.sqlite3
```

`verify` seeds the idempotent fictional demo and checks search, graph,
integrity and entity cardinalities in one call. `restore SOURCE DESTINATION`
validates the SQLite backup before copying it. Set
`RESEARCHOS_WORKSPACE=/path/to/researchos.sqlite3` to avoid repeating the
workspace flag. The installed console command is `researchos-agent`; from a
source checkout use `scripts/researchos-agent`.

To build a portable Linux package (GUI binary when PyInstaller is available,
plus the headless source CLI), run:

```bash
bash scripts/build_linux.sh
# dist/ResearchOS-linux-x86_64-v0.2.0.tar.gz
```

The package's `scripts/researchos-agent` works in minimal cloud images and its
`bin/ResearchOS` executable opens the GUI when a display is available. A
`build-linux.yml` workflow repeats these checks on Ubuntu for every version
tag or manual dispatch.

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

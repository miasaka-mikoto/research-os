# Agent Memory Research Demo

This is a fictional, fully local Research OS workspace used for smoke tests
and first launch. It contains:

- 5 Papers
- 10 Claims
- 4 Evidence records
- 3 Hypotheses
- 4 Experiments
- 4 Results
- Questions, Concepts, Datasets, Artifacts, Ideas, Decisions, Tasks and Daily Logs
- 55 typed graph relations, including SUPPORTS, REFUTES, CONTRADICTS and NEEDS_VERIFICATION

Open it with:

```powershell
python -m researchos.app --workspace demo_workspace/agent_memory_research_demo.sqlite3
```

All claims and results are synthetic examples for testing graph provenance;
they are not empirical findings.

## Note

`agent_memory_research_demo.sqlite3` is intentionally not committed to the repository.
Generate it locally with:

```bash
python scripts/seed_demo.py
```

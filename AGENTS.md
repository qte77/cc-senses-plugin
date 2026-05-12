# Agents

Role archetypes for subagent dispatch via `cc-meta:orchestrating-parallel-workers`.

## Roles

| Role | Skills | Scope |
|------|--------|-------|
| **Implementer** | `python-dev:implementing-python`, `tdd-core:testing-tdd` | Write code + tests (red-green-refactor) |
| **Tester** | `tdd-core:testing-tdd`, `python-dev:testing-python` | Backfill tests, property tests, coverage gaps |
| **Reviewer** | `python-dev:reviewing-code`, `security-audit:auditing-code-security` | Code review, OWASP audit, type safety |
| **Docs** | `docs-governance:maintaining-agents-md`, `docs-governance:enforcing-doc-hierarchy` | ADRs, SKILL.md, README, doc hierarchy |

## Parallel patterns

| Pattern | Workers | When to use |
|---------|---------|-------------|
| TDD + Review | 2 | New feature: one writes tests+impl, other reviews |
| Multi-engine | 2-3 | Feature touches TTS+STT+VLM engines independently |
| Docs + Code | 2 | Implementation + ADR/README update in parallel |
| Hardening | 3 | Security audit + test coverage + doc hierarchy in parallel |

## Dispatch example

```text
/orchestrating-parallel-workers

Worker 1 (Implementer): Add --format flag to cc-tts-stream. TDD: test first, then impl. Files: src/cc_tts/stream_json.py, tests/test_stream_json.py
Worker 2 (Docs): Update SKILL.md and README with --format flag docs. Files: skills/speak/SKILL.md, README.md
```

## Key references

- **Skills**: `skills/speak/SKILL.md`, `skills/listen/SKILL.md`, `skills/see/SKILL.md`
- **ADRs**: `docs/adr/0001-tts-delivery-modes.md`, `docs/adr/0002-stt-engine-selection.md`, `docs/adr/0003-vlm-screen-sharing.md`
- **Roadmap**: `docs/roadmap/v0.5.x.md`
- **Config**: `.cc-senses.toml` (TOML + env overrides)
- **Learnings**: `AGENT_LEARNINGS.md`

## Conventions

- Always TDD: red-green-refactor, `make validate` before commit
- `uv` only (never pip)
- Protected main: feature branches + squash-merge PRs
- Bump plugin version when modifying `plugins/<name>/` files

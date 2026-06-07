# End-to-End Test Plan — confluence-sync

**Status:** Draft (2026-06-07)  
**Audience:** Maintainers preparing a release  
**Problem this solves:** Unit tests passed while `make release` failed repeatedly. The project lacked a defined E2E strategy that exercises the *actual* maintainer path before version bump.

---

## 1. What went wrong (honest postmortem)

| Claim | Reality |
|-------|---------|
| "Tests pass" | 99 pytest tests pass; they mock Confluence and never run `sync.py` against a real API |
| "Release ready" | `scripts/release.sh` (11 steps) was never executed end-to-end before the first attempt |
| "Smoke works" | Live smoke was documented but not run; config path, venv CLI, and sync porting bugs blocked it |
| "Preflight" | Added reactively; still doesn't prove the *current commit* is smoke-clean |

**Root cause:** No **test pyramid entry** between mocked unit tests and a destructive 11-step release script. Failures surfaced one step at a time on the maintainer's machine.

---

## 2. Testing layers (target architecture)

```
                    ┌─────────────────────────────┐
                    │  L5  Release rehearsal      │  maintainer, pre-tag
                    │  (full script, no tag/push) │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  L4  Live smoke (Confluence) │  maintainer / nightly
                    │  ephemeral space lifecycle   │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  L3  Pipeline integration    │  pytest + tmp git repos
                    │  sync.py full path (mocked)  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  L2  Shell / script tests    │  bats or shunit2
                    │  lib.sh, preflight, trap     │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  L1  Unit + CLI subprocess   │  pytest (current)
                    └─────────────────────────────┘
```

Each layer has a **single Make target**, clear **pass criteria**, and a **when to run** rule.

---

## 3. Layer definitions

### L1 — Unit + CLI (exists today)

| Item | Detail |
|------|--------|
| **Command** | `make test` |
| **Scope** | `tests/unit`, `tests/integration`, `tests/cli` |
| **Covers** | Config, paths, git_utils, orphan handler, CLI help/subprocess |
| **Does not cover** | `sync.py` orchestration, Confluence HTTP, shell scripts, release |
| **Gate** | Every commit; coverage ≥72% on core modules |
| **Gap** | `sync.py` bugs (`data_dir`, `find_or_create_folder`, `force_update`) lived here undetected |

**L1 improvements (P1):**

- [ ] `tests/unit/test_sync_orchestration.py` — mock `ConfluenceSync`, run `sync_destination()` through prepare → folders → pages → orphans with a `tmp_path` git repo
- [ ] `tests/unit/test_confluence_page_body.py` — assert `_get_page(include_body=True)` uses `body-format=storage` and `_page_storage_body()` parsing
- [ ] Expand CLI tests: `smoke --help`, `doctor --config tests/live_smoke/...`

---

### L2 — Shell / script integration (missing)

| Item | Detail |
|------|--------|
| **Command** | `make test-scripts` (to add) |
| **Scope** | `scripts/lib.sh`, `scripts/release-preflight.sh`, trap behavior |
| **Tool** | [bats-core](https://github.com/bats-core/bats-core) or pure bash with `docker`/`mock` stubs |
| **Gate** | Every PR touching `scripts/` |

**Cases to automate:**

| # | Scenario | Expected |
|---|----------|----------|
| S1 | `ensure_venv` when `.venv` missing | bootstraps or fails clearly |
| S2 | `load_confluence_env` | loads token from `~/.local/confluence-sync/.env` |
| S3 | `run_live_smoke` invokes `.venv/bin/confluence-sync` with `--config tests/live_smoke/...` | not bare `confluence-sync` |
| S4 | `run_smoke_reset` in EXIT trap | uses venv path; does not error 127 |
| S5 | `release-preflight` without `smoke-last-pass` | exit 1 with "Run: make smoke" |
| S6 | `release-preflight` with stale `smoke-session.json` | calls reset before pass |
| S7 | `release-preflight` with expired `smoke-last-pass` | exit 1 |

**L2 improvements (P1):**

- [ ] Add `tests/scripts/` with bats tests
- [ ] Add `make test-scripts` to Makefile; run in `make test-all`

---

### L3 — Pipeline integration with mocked Confluence (missing)

| Item | Detail |
|------|--------|
| **Command** | `make test-pipeline` (to add) |
| **Scope** | Full `sync_destination()` + `smoke run` logic without network |
| **Tool** | `pytest` + `responses`/`httpx` mock or `unittest.mock` on `ConfluenceSync._make_request` |
| **Gate** | Every PR touching `sync.py`, `confluence_sync.py`, `smoke*.py` |

**Cases:**

| # | Scenario | Expected |
|---|----------|----------|
| P1 | Clean sync of mini fixture (2 md files, 1 folder) | 0 errors; state file has `content_hash` per page |
| P2 | Second sync, no file changes | all `skipped`; 0 `updated` |
| P3 | One file changed | exactly 1 `updated` |
| P4 | `SmokeProvisioner.create` mocked 200 | patched dest gets ephemeral `space_key` |
| P5 | `SmokeProvisioner.destroy` mocked 202 + longtask | session file cleared |
| P6 | Page GET returns `body.storage.value` | incremental compare does not treat as empty |

**L3 improvements (P1–P2):**

- [ ] `tests/integration/test_sync_pipeline.py`
- [ ] `tests/integration/test_smoke_run_mocked.py` — smoke run with provisioner + sync mocked; assert step order

---

### L4 — Live smoke (partially exists)

| Item | Detail |
|------|--------|
| **Command** | `make smoke` |
| **Scope** | Real Confluence: ephemeral space create → sync → verify → incremental → patch → destroy space |
| **Prereqs** | `CONFLUENCE_TOKEN` in `~/.local/confluence-sync/.env`; `mmdc` or npx |
| **Gate** | **Required before every release**; nightly optional |

**Current pass criteria (implemented):**

1. Ephemeral space created (`CS{run_id}`)
2. Clean sync: 8 pages, 0 errors
3. Verify: page count, mermaid PNG, image attachments
4. Incremental: 0 created; second pass 0 updated (after link normalization)
5. Patch sync: exactly 1 updated (`sibling.md`)
6. Teardown: space deleted; `smoke-session.json` cleared

**Gaps in L4 (P1–P2):**

| # | Gap | Fix |
|---|-----|-----|
| L4-1 | `smoke-last-pass` is timestamp only, not commit SHA | Record `git rev-parse HEAD` + timestamp; preflight verifies SHA matches (or allow `SMOKE_GATE_ALLOW_STALE_SHA=1` after doc-only changes) |
| L4-2 | ADR 0023 still references `CONFLUENCE_SMOKE_ROOT_PAGE_ID` | Update ADR to ephemeral space model |
| L4-3 | `smoke_verify` does not check links/anchors (ADR claims it does) | Add link assertions or narrow ADR |
| L4-4 | Fixture `assets/` missing for `images.md` | Add `tests/live_smoke/fixture/assets/` or smoke fails on attachment verify intermittently |
| L4-5 | Fallback path (`CONFLUENCE_SPACE`) not tested | Separate `make smoke-fallback` or pytest marker `@pytest.mark.live` |
| L4-6 | Interrupt testing (SIGINT during smoke) | Manual checklist item until automated trap test in L2 |

**L4 manual checklist (until automated):**

```bash
# Run once per release candidate on maintainer machine
make install
make test
make smoke                    # must exit 0
make release-preflight        # must exit 0
# Inspect Confluence: no stray CS* spaces left
ls ~/.local/confluence-sync/  # no smoke-session.json
```

---

### L5 — Release rehearsal (missing — highest priority)

| Item | Detail |
|------|--------|
| **Command** | `make release-rehearsal` (to add) |
| **Scope** | Entire `release.sh` **except** version bump commit, tag, push |
| **Purpose** | Catch release failures *before* mutating version files |

**Proposed `scripts/release-rehearsal.sh`:**

```
Steps (no git mutations):
  1. Assert clean tree on main (or allow REHEARSAL_DIR=tmp worktree)
  2. release-preflight
  3. make test
  4. mmdc check
  5. trap + make smoke
  6. hatch build → dist/
  7. publish-brew.sh with REHEARSAL_VERSION=99.0.0-rehearsal (local tarball sha)
  8. brew test --formula (against local dist)
  9. Print "rehearsal passed" — do NOT commit/tag
```

**Pass criteria:** Exit 0; `dist/*.whl` and `dist/*.tar.gz` exist; formula sha matches local tarball.

**L5 improvements (P0):**

- [ ] Implement `scripts/release-rehearsal.sh` + `make release-rehearsal`
- [ ] Document in RELEASE.md as **mandatory once per release candidate**
- [ ] Wire into DEVELOPER-GUIDE gates table

---

### L6 — Consumer validation (missing)

After package release, verify real consumer repos still work.

| Repo | Command | Pass |
|------|---------|------|
| `zeta-ai-product-strategy` | `confluence-sync doctor` + `sync -d foundry-cto --dry-run` | exit 0 |
| `writing-work` | `confluence-sync sync -d term-deposits-tda --dry-run` | exit 0 |

**Gate:** Manual after first `0.1.0` install; add to release checklist post-push.

---

## 4. Executable maintainer workflow (target)

```bash
# ── On every change touching sync/smoke/scripts ──
make test              # L1
make test-scripts      # L2 (when added)
make test-pipeline     # L3 (when added)

# ── Once per release candidate (same machine that will release) ──
make smoke             # L4 — records smoke-last-pass + commit SHA
make release-rehearsal # L5 — full dry release

# ── The actual release (only after L4 + L5 green) ──
make release VERSION=x.y.z
git push && git push --tags
gh release create vX.Y.Z dist/*

# ── After push ──
# L6 consumer dry-runs in strategy + writing-work
```

---

## 5. What runs when

| Trigger | L1 | L2 | L3 | L4 | L5 | L6 |
|---------|----|----|----|----|----|-----|
| Every commit (local) | ✓ | scripts changes | pipeline changes | — | — | — |
| PR (future CI) | ✓ | ✓ | ✓ | skip (no token) | skip | skip |
| Nightly (optional) | ✓ | ✓ | ✓ | ✓ | — | — |
| Pre-release | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Post-release | — | — | — | — | — | ✓ |

**Note:** ADR 0015 says no external CI is required. L4/L5 remain maintainer-local unless you add a self-hosted nightly with `CONFLUENCE_TOKEN`.

---

## 6. Implementation roadmap

### P0 — Stop repeating release-debug loops (1–2 days)

| ID | Task | Deliverable |
|----|------|-------------|
| P0-1 | `make release-rehearsal` | `scripts/release-rehearsal.sh` |
| P0-2 | Bind `smoke-last-pass` to git SHA | `lib.sh` + `release-preflight.sh` |
| P0-3 | Add fixture `assets/` if missing | `tests/live_smoke/fixture/assets/test.png`, `hero.jpeg` |
| P0-4 | Update RELEASE.md checklist | Rehearsal before release |
| P0-5 | Update ADR 0023 + 0024 | Match ephemeral space + current cleanup API |

### P1 — Catch porting regressions in pytest (2–3 days)

| ID | Task | Deliverable |
|----|------|-------------|
| P1-1 | Mocked full `sync_destination` test | `test_sync_pipeline.py` |
| P1-2 | Shell tests for lib/preflight | `tests/scripts/*.bats` |
| P1-3 | `make test-all` = test + test-scripts + test-pipeline | Makefile |
| P1-4 | Smoke error messages print `error_message` on failure | `smoke.py` / `sync.py` |

### P2 — Hardening (1 week)

| ID | Task | Deliverable |
|----|------|-------------|
| P2-1 | Link/anchor verification in `smoke_verify` | or ADR scope trim |
| P2-2 | `make smoke-fallback` for personal-space path | separate test entry |
| P2-3 | Consumer dry-run script | `scripts/verify-consumers.sh` |
| P2-4 | HTTP record/replay fixtures for Confluence v2 | optional VCR dir |

---

## 7. Definition of Done — "ready to tag vX.Y.Z"

All must be true:

- [ ] `make test-all` green on `main`
- [ ] `make smoke` green; `smoke-last-pass` SHA == `git rev-parse HEAD`
- [ ] `make release-rehearsal` green
- [ ] No `smoke-session.json` left in `~/.local/confluence-sync/`
- [ ] No orphan `CS*` spaces in Confluence admin
- [ ] CHANGELOG `[Unreleased]` section complete
- [ ] `make release VERSION=x.y.z` completes step 11
- [ ] Post-push L6 consumer dry-runs pass

---

## 8. Failure injection matrix (rehearsal / manual)

| Inject | Step that should fail | Detect |
|--------|----------------------|--------|
| Unset `CONFLUENCE_TOKEN` | preflight / smoke | clear error |
| Remove `mmdc` from PATH | preflight step 5 | clear error |
| Corrupt `smoke-last-pass` | preflight | "Re-run: make smoke" |
| Kill smoke mid-run (`Ctrl-C`) | trap | space destroyed via session file |
| Wrong `space_key` in yaml (auto_provision false) | smoke provision | fallback or fail loud |
| Publish without prior `git push --tags` | publish-brew github fetch | documented workaround |

---

## 9. Documentation sync debt

| Doc | Stale content | Action |
|-----|---------------|--------|
| ADR 0023 | `CONFLUENCE_SMOKE_ROOT_PAGE_ID`, manual CSYNC | Rewrite for ephemeral space |
| ADR 0024 | `delete_smoke_pages()` | Align with `SmokeProvisioner.destroy_workspace` |
| DEVELOPER-GUIDE | Gate table | Add L2–L5 targets |
| noxfile docstring | still primary path | Note Makefile is canonical for maintainers |

---

## 10. Summary

**The fix is not "run more pytest."** It is:

1. **Rehearse the release script** without tagging (`make release-rehearsal`)
2. **Test shell wiring** (venv paths, traps, preflight gates)
3. **Test sync orchestration** with mocks before live Confluence
4. **Bind smoke pass to commit SHA**, not a hand-waved timestamp
5. **Run L4 + L5 on the same machine, same commit**, then `make release`

Until P0 is implemented, treat every release as experimental and assume unit-test green is necessary but insufficient.

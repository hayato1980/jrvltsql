# PR #248 SE MakeDate repair worklog — 2026-08-26

## Start state and minimum scope

- Objective: repair the two exact release-blocking findings on
  `miyamamoto/jrvltsql` PR #248 without widening the SE contract beyond the
  captured provider sentinel.
- Repository: `miyamamoto/jrvltsql`.
- Dedicated worktree:
  `/home/keiba/scratch/20260826_jrvltsql_pr248_repair`.
- Local branch: `codex/pr248-se-makedate-repair-20260826`.
- PR head branch in contributor fork:
  `hayato1980:claude/pr35-rebase-upstream-oyqo45`; maintainers are allowed to
  modify it.
- Fetched base `origin/master`:
  `195a12f8f344d3cb9eb35ad6b22b7f58a40ef872` (`2.0.0.dev6`).
- Starting PR head:
  `510e7e654bb226e7b3467f2ef1c75109bc0b6f75`.
- Release scope: repair PR #248 only. Do not bump or publish a release in this
  iteration. A successful repair may be followed by a separate
  `2.0.0.dev7` release iteration after development-runtime provider storage
  evidence.

## Confirmed findings to close in one batch

1. Parser validation accepts every eight-digit value, including impossible
   non-zero dates such as `20040231`. Official evidence supports an exact
   `00000000` initial value, not arbitrary impossible provenance dates. The
   contract must be a real `YYYYMMDD` date or exact `00000000`.
2. Standard storage still declares `UMA_RACE.MakeDate DATE`. A fresh
   PostgreSQL 16 standard-mode import of the captured sentinel therefore fails
   with an out-of-range date even though native `NL_SE` succeeds. Standard
   storage must preserve the eight provider characters losslessly, and an
   existing DATE schema must be rejected by preflight before DML.
3. The captured fixture digest assertion currently checks only the first 16
   SHA-256 characters. Pin the complete digest.

## Required red/green evidence

- Before implementation, prove that current PR head accepts an impossible
  non-zero date and fails the captured `00000000` record in PostgreSQL
  standard mode.
- Add the smallest paired regression coverage: exact zero and real dates stay
  green; impossible/non-format values are red; native and standard storage
  preserve the sentinel; existing standard DATE storage fails closed before
  mutation.
- Run focused SE/schema/importer tests on SQLite and fresh PostgreSQL 16, then
  the repository workflow-equivalent suite and fresh artifact/install smoke
  on the exact final SHA.

## STOP conditions

- Stop on base/head drift, a fixture digest mismatch, behavior outside SE,
  any automatic in-place DATE-to-text migration, a PostgreSQL mutation before
  schema rejection, unresolved data loss, or unrelated dirty files.
- Do not alter the registered JRA runtime, Wine identity, provider cache, raw
  PostgreSQL, or production state in this PR repair.
- Do not merge until exact-head tests pass, the requested-changes review is
  superseded/resolved, unresolved threads are zero, and the worktree is clean.

## Red-first evidence at starting PR head

- Locked CPython 3.12 environment:
  `pytest -q tests/test_se_makedate_gate.py` produced
  `3 failed, 11 passed, 2 skipped`. Each failure was
  `Failed: DID NOT RAISE` for `20040231`, `20040001`, and `20041332`.
- Fresh disposable PostgreSQL 16:
  the two standard-storage regressions both failed. Importing the captured
  `00000000` row reached DML and PostgreSQL returned
  `date/time field value out of range: "00000000"`; the paired unsafe-schema
  test also proved that the expected `VARCHAR(8)` contract did not yet exist.
- No production file had been changed when these red results were recorded.

## Batched repair in progress

- Restrict SE `MakeDate` to an actual calendar date or exact `00000000`.
- Store standard `UMA_RACE.MakeDate` as `VARCHAR(8)`. Reuse the existing strict
  schema verifier so a legacy `DATE` column is rejected before DML; do not
  perform an in-place conversion.
- Pin the captured provider fixture with its complete SHA-256 digest and align
  the public migration contract.

## Candidate verification before SHA freeze

- Locked CPython 3.12.11, SQLite/default focused regression:
  `14 passed, 2 skipped`.
- Fresh PostgreSQL 16 plus SQLite across the SE MakeDate, official-contract,
  schema-migration, and canonical suites: `129 passed`. This includes
  lossless standard storage of `00000000` and pre-DML rejection of a legacy
  `DATE` column.
- Workflow-equivalent default test selection:
  `4794 passed, 505 skipped, 14 deselected, 21 subtests passed`.
- `scripts/validate_test_gate.py`: `TEST GATE PASS`.
- `uv lock --check`: passed with 50 locked packages.
- Fatal flake8 (`E9,F63,F7,F82`): zero findings.
- Strict MkDocs build: passed. The existing informational note that
  `record_contracts.md` is outside the configured nav remains unchanged.
- Focused `ruff check` of the hand-written parser and regression module passed.
  The repository's pre-existing `typing.Dict` advisory in generated
  `schema_jravan.py` was not widened into this repair.
- The Windows launcher contract was collected on Linux and produced the
  expected five environment skips; the Windows workflow remains the platform
  execution gate.
- `git diff --check`: passed.

No JRA runtime, provider cache, raw database, release metadata, or machine
identity was mutated. The PostgreSQL service used here is a disposable local
16 container created solely for this candidate.

Next safe action: freeze a commit, build wheel/sdist from its git archive, run
the distribution/installed-wheel smokes and Windows launcher contract, then
obtain one independent critical review of that immutable SHA.

## Immutable candidate review and artifact evidence

- Production/test candidate commit:
  `dd2ee0b98355113458a031decd5e7162d5246a49`.
- Fresh wheel and sdist built from `git archive` of that exact commit. The
  distribution-content gate and installed-wheel init smoke both passed;
  generated names and metadata remained `2.0.0.dev6`, as intended for this
  non-release repair.
- Independent read-only critical review used Claude Code `--model fable`
  (chosen because this validator/schema/fail-before-mutation boundary is a
  high-cost data-integrity change), session
  `c6fb141c-9dfd-4edc-ae32-8ea9b2f6fc1a`. Verdict: **GREEN**, P0=0, P1=0.
- The reviewer independently confirmed exact sentinel matching, rejection of
  impossible non-zero dates, lossless text storage, SQLite/PostgreSQL schema
  preflight, full fixture digest, and the absence of a downstream date-coercion
  path.

### P2 disposition

1. A future `.gitattributes` binary rule could make fixture handling more
   obvious, but the full SHA-256 plus exact length/CRLF tests already make any
   normalization a visible failure rather than a false green. Record as a
   non-blocking repository-hygiene follow-up; do not widen this repair.
2. PostgreSQL integration remains opt-in in the existing CI architecture. The
   exact candidate was therefore tested against a fresh local PostgreSQL 16
   instance, including both success and rejection paths. Changing CI service
   topology is a separate iteration.
3. The migration wording was clarified after review: old `DATE` storage could
   not save sentinel rows, so an in-place type conversion cannot restore the
   missing rows. The fail-closed rebuild/reimport policy remains unchanged.
4. A new SQLite-only duplicate of the legacy-DATE test was not added. The same
   generic declared-type verifier already has SQLite mismatch coverage, while
   this iteration adds the exact PostgreSQL regression where the production
   failure occurred. This avoids reviewer-hypothesis test proliferation.
5. CHANGELOG/RELEASE_NOTES and the operational migration notice are mandatory
   in the separate `2.0.0.dev7` release iteration. They are deliberately not
   mixed into PR #248 repair.

The post-review change is documentation/worklog-only; production code, schema,
tests, and built artifact inputs are byte-identical to the reviewed commit.
Next safe action: commit this review disposition, push both commits to the
existing PR head, verify exact remote SHA/CI/review state, and merge only when
all required gates are green.

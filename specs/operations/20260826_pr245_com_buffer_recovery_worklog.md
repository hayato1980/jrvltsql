# PR #245 COM buffer recovery worklog

## Scope and identity

- Purpose: repair and independently validate `miyamamoto/jrvltsql#245` without broadening into unrelated parser/importer changes.
- Repository: `miyamamoto/jrvltsql`.
- Worktree: `/home/keiba/scratch/20260826_jrvltsql_pr245_repair`.
- Branch: `codex/pr245-buffer-recovery-20260826`.
- Base `master`: `34a3297a376b56646ff166f9d1de903d92b010c9`.
- Contributor candidate at start: `7bb78c846260ccfa46e0954c4fea8291c4523409`.
- PR: <https://github.com/miyamamoto/jrvltsql/pull/245>.
- Production/release line: `2.0.0.dev5`; no version change belongs to this repair iteration.

## Contract and plan

- Preserve exact JV-Data bytes for latin-1-like, CP1252, and CP932 pywin32 marshal shapes.
- A trailing COM NUL must not alter encoding-candidate selection.
- Reject ambiguous recovery rather than returning a same-length corrupted record.
- Add the paired failing regression first, run it against the contributor candidate, then make the smallest production repair.
- Run focused transport tests and the repository-required relevant suite at the final full SHA.

## Initial state

- The main `/home/keiba/jrvltsql` checkout was already dirty on an unrelated old branch and is intentionally untouched.
- The dedicated worktree started clean at the contributor full SHA above.
- GitHub reported the PR mergeable/clean and its existing test/lint checks successful.

## Red-first evidence

- Added one paired regression for CP1252 and CP932 marshal strings with trailing COM NUL padding.
- On unchanged production code at `7bb78c846260ccfa46e0954c4fea8291c4523409`, both parameters failed: the recovered bytes differed from the original bytes at index 10.
- Added the fail-closed oversized-prefix contract. With the ambiguity branch temporarily absent, the focused test failed with `DID NOT RAISE JVLinkError`.
- These failures establish that the tests can say no; they are not success-only coverage.

## Repair

- Strip only trailing COM NUL padding before building encoding candidates. JV-Data fixed records end in CRLF, so this does not discard a valid record suffix.
- Require all exact-length candidates to agree.
- If only oversized candidates exist, compare their truncated prefixes and reject differing bytes as ambiguous instead of selecting by candidate order.

## Validation

- Python 3.13 focused transport module: `84 passed`.
- Fresh isolated Python 3.12.11 focused transport module: `84 passed`.
- Fresh isolated Python 3.12.11 repository suite (integration/e2e/slow excluded in the same shape as CI): `4735 passed, 503 skipped, 14 deselected, 21 subtests passed`.
- The first full-suite collection attempt was unable to import the optional PostgreSQL drivers. After installing the locked `postgres` extra into the isolated environment, the same command passed as recorded above; this was an environment setup issue, not a product failure.
- Workflow-equivalent fatal flake8 selection (`E9,F63,F7,F82`): pass with zero findings.
- `python scripts/validate_test_gate.py`: `TEST GATE PASS`.
- `uv lock --check`: pass.
- `git diff --check`: pass.
- A direct Ruff run reports pre-existing style debt in `wrapper.py`; none was introduced by this bounded repair and Ruff is not the workflow's fatal lint gate.

## Remaining before merge

- Commit and push this exact repair to the contributor PR branch, recording the resulting full SHA on the PR.
- Confirm required GitHub checks, actionable review findings, and unresolved-thread count on that pushed SHA.
- Merge only from a clean worktree after those gates are green.

## STOP conditions

- Stop if the dedicated worktree drifts outside the files listed in this worklog.
- Stop rather than guessing if actual COM padding cannot be represented without corrupting one of the paired marshal paths.
- Do not bump or tag a release from this branch.

# PR #246 yearly JVOpen repair worklog

## Scope and identity

- Purpose: independently repair and validate `miyamamoto/jrvltsql#246` before merge.
- Repository: `miyamamoto/jrvltsql`.
- Worktree: `/home/keiba/scratch/20260826_jrvltsql_pr246_repair`.
- Branch: `codex/pr246-chunk-close-20260826`.
- Base `master`: `34a3297a376b56646ff166f9d1de903d92b010c9`.
- Contributor candidate at start: `cfd0c0b0fbcbca9497a31194a0d2d941be841441`.
- PR: <https://github.com/miyamamoto/jrvltsql/pull/246>.
- Production/release line: `2.0.0.dev5`; version publication is a separate post-merge iteration.
- After PR #245 merged, this branch was cleanly rebased onto new `master` full SHA `2ed75a8e4873dbde786f3b0f773249ac639f2730`. The old base above remains the contributor start identity, not the merge target.

## Minimum repair contract

- A failed `JVClose` after an otherwise successful chunk must fail the fetch, prevent the next `JVOpen`, and prevent an NL-cache complete marker. A close failure must not replace an already-active primary exception.
- CLI/docs must state that option 2 is start-only even for a range-capable dataspec, and distinguish option 1/2 midnight cursors from option 3/4 previous-second cursors.
- Cross-chunk `-402` self-repair must replay only the successfully emitted prefix of the active chunk, excluding all records emitted by earlier chunks.
- The range-fromtime allowlist must contain only provider combinations with recorded live evidence. PR #246 records live range evidence for `RACE`; it records no equivalent SLOP/WOOD run, so those specs remain start-only until separately verified.
- Preserve boundary tiling, option-specific transaction ownership, cache rollback, and existing start-only behavior for non-allowlisted specs.

## Initial review findings

- `HistoricalFetcher._fetch_one_open()` catches `jv_close()` exceptions and logs a warning, then the outer fetch can open the next chunk and mark the cache range complete. This is a correctness and completeness failure, not advisory cleanup.
- The CLI single-open note attributes start-only behavior only to dataspec capability, omitting option 2's separate start-only contract. This matches the unresolved GitHub review thread.
- The new cross-chunk baseline is production-critical but lacks a regression that exercises recovery in chunk 2 after chunk 1 emitted rows.
- `RANGE_FROMTIME_DATA_SPECS` says only live-verified specs may be included, while the PR body provides live measurements only for `RACE` but enables `SLOP` and `WOOD` too.

## Red-first plan

Add the smallest paired regression around the existing yearly-chunk test module, run it against the unchanged contributor production code, and record the exact failure before changing production. Do not create one test per reviewer hypothesis where one parameterized or adjacent contract can pin the behavior.

## Red-first evidence

- On unchanged contributor production `cfd0c0b0fbcbca9497a31194a0d2d941be841441`, the focused yearly-chunk module reported **2 failed, 43 passed**:
  - the provider allowlist contained unverified `SLOP` and `WOOD` in addition to `RACE`;
  - a first-chunk `JVClose` exception produced `DID NOT RAISE FetcherError`, opened the second chunk, and logged `Fetch completed`.
- The cross-chunk replay implementation was already correct. To prove the new regression can detect its loss, the baseline subtraction was temporarily replaced with the full fetch count. The single test failed exactly `assert 5 == 2`; the production subtraction was restored immediately.

## Repair implemented

- A successful chunk now becomes complete only after `JVClose` succeeds. A close failure raises `FetcherError`, so the next chunk and cache-complete marker are unreachable.
- If a provider/read exception is already unwinding, a secondary close exception is logged without replacing the primary exception.
- The range allowlist is reduced to the only live-evidenced spec, `RACE`; `SLOP` and `WOOD` use the safe start-only path pending their own provider evidence.
- CLI/help/docs now describe option 2 as start-only even for `RACE`, name the measured allowlist honestly, and distinguish the option 1/2 midnight cursor from the option 3/4 previous-second cursor.
- Added one cross-chunk recovery regression that fixes the replay count at the active chunk's two-row prefix rather than the five-row request total.

## Validation so far

- Yearly-chunk plus CLI module on Python 3.12.11: **80 passed, 10 subtests passed**.
- Affected transport/batch/cache/recovery/date/constants/retired-spec ring on Python 3.12.11: **377 passed, 10 subtests passed**.
- Workflow-equivalent Python 3.12.11 repository suite (integration/e2e/slow excluded): **4759 passed, 503 skipped, 14 deselected, 21 subtests passed**.
- Workflow fatal flake8 selection (`E9,F63,F7,F82`): zero findings.
- `python -m compileall -q src tests scripts tools`: pass.
- `scripts/validate_test_gate.py`: `TEST GATE PASS` under Python 3.12.
- `uv lock --check` and `git diff --check`: pass.
- Before the rebase, the aggregated repair commit was `a4fe2aaff8957ff34507888a524a7f606a209ac6`; the full-suite result above is bound to that exact production/test tree.
- After rebasing onto merged PR #245, the combined candidate `8783ad6478a94545dcef4da12ba803ba72873f0e` passed the affected ring including the newly merged COM transport tests: **398 passed, 10 subtests passed**. Test-gate, lock, fatal lint and diff checks also passed. The rebase added only the independently full-tested PR #245 delta; GitHub will run the workflow-equivalent full suite on the pushed combined head.

## Remaining before merge

- Push one updated contributor candidate, record its final full SHA on PR #246 (without a self-referential worklog commit), reply to/resolve the existing documentation and baseline threads, and wait for exact-head checks.
- Merge only with all checks green, unresolved threads zero, and tracked/ignored worktree clean.

## STOP conditions

- Stop on drift outside this dedicated worktree or on any live JV-Link/provider, database, cache, Wine-prefix, registration, or release mutation.
- Do not guess that an unmeasured dataspec shares RACE provider behavior.
- Do not merge if close failure can be reported as success, cache completion can survive a failed chunk lifecycle, or unresolved review threads remain.

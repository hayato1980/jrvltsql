# PR #161 retired data-spec gate worklog

## Scope and provenance

- Objective: make the 2023-08 retired JV-Data spec names fail closed at every
  supported historical JVOpen entry point, while keeping the replacement
  names usable and restoring the PR's failing CI tests without weakening the
  CLI configuration contract.
- Minimal scope: shared retired-spec validation, the public Python JV-Link
  wrapper/bridge entry points, the existing historical/CLI guards and focused
  tests, plus this worklog. Operational name replacements already present in
  the PR are reviewed but not broadened without a concrete defect.
- Repository: `miyamamoto/jrvltsql`
- Worktree: `/home/keiba/scratch/20260815_jrvltsql_pr161_fix`
- Branch: `claude/reject-legacy-dataspecs-225` (cross-repository PR branch in
  `hayato1980/jrvltsql`)
- PR: https://github.com/miyamamoto/jrvltsql/pull/161
- Base branch: `master`
- Latest base full SHA at iteration start:
  `e55b1f93f4661cf83cc7d890ebe6ee7399f354ab`
- Starting PR head full SHA:
  `b2a79a70145ddb6427fe03a7c711c5c6e3847c32`
- Base-update merge commit full SHA:
  `7e1f583aea6d027528a1eec2cf863bf1559adc7b`
- Related release: `v1.6.10`
- Dependency order: PR #159 merged as
  `0001ea2179db28be49938f4b7f178a6bd70c0942`; PR #160 merged as
  `e55b1f93f4661cf83cc7d890ebe6ee7399f354ab`; this PR now includes both.

## Claude Code sessions

- Implementation/review-fix session ID:
  `e2ec26a4-3b59-499a-b1a7-a98c1a6b27cd`
- Planned independent final-review session ID:
  `ddf27a69-bc9a-4e68-8cb6-fba082d2e181`
- Model for both: `--model fable`
- Selection reason: this is a fail-closed validator with multiple public
  entry paths (CLI, historical fetcher, in-process COM wrapper, out-of-process
  bridge). Incorrect ordering or a missed path changes whether a retired name
  reaches JVOpen and can silently request the wrong/unsupported dataset.
- Review corrections in this iteration must resume the implementation session;
  the final-review session is separate and read-only.

## Retired-name contract

- Retired → replacement mappings introduced by the PR:
  `DIFF→DIFN`, `BLOD→BLDN`, `SNAP→SNPN`, `HOSE→HOSN`, `TCOV→TCVN`,
  `RCOV→RCVN`.
- Matching is case-insensitive. Replacement/current names remain accepted.
- Rejection must occur before COM invocation or bridge command transmission,
  with an actionable message naming the replacement.

## Status at start

- Observed: original PR lint and CodeRabbit succeeded, but the Actions test job
  ran real test steps and failed: `9 failed, 745 passed, 2 skipped` on
  `b2a79a70145ddb6427fe03a7c711c5c6e3847c32`. This is a real CI failure and
  cannot be waived.
- Observed CI cause: all nine failures invoke root Click commands without a
  config file, so the root callback exits with `Configuration file not found`
  before the subcommand retired-spec guard runs. The tests therefore do not
  reach the behavior they claim to verify.
- Contract decision pending implementation review: preserve configuration as
  the root CLI prerequisite and provide a minimal config to focused CLI tests,
  unless evidence shows retired-name validation intentionally belongs before
  all root setup. Do not move business validation into the root callback just
  to satisfy a test.
- Observed bypass risk: `HistoricalFetcher.fetch`/cache paths guard retired
  names, but direct public `JVLinkWrapper.jv_open` and
  `JVLinkBridge.jv_open` calls do not yet invoke the shared guard. Direct users
  can therefore bypass the PR's intended fail-closed boundary.
- The PR has no known unresolved inline thread; review-body and CI findings
  require explicit PR conversation evidence after correction.
- Latest `origin/master` merged without conflicts; no implementation edit has
  been made in this iteration. Worktree was clean before creating this log.

## Red-first requirement

- Before production edits, add the minimum regression contract proving direct
  wrapper and bridge calls with retired names currently reach their downstream
  COM/send paths. Run on unchanged production code and record the observed red
  assertions/exit status.
- Keep replacement/current names green and prove they still reach the
  downstream path.
- Repair CLI tests so they exercise the command under its real config
  prerequisite; a missing config is not evidence about retired-spec handling.

## Implementation session evidence (e2ec26a4, 2026-08-15)

### Environment

- `uv sync --python 3.12 --extra dev --extra postgres` in the worktree;
  `.venv/bin/python -V` → `Python 3.12.11` (matches the CI job's 3.12).
- All commands below ran from the worktree root with
  `.venv/bin/python -m pytest ... -p no:cacheprovider --no-cov -q`.

### CI 9-failure diagnosis confirmed locally (unchanged code)

- Command: `pytest tests/test_retired_data_specs.py` on
  `7e1f583aea6d027528a1eec2cf863bf1559adc7b` before any edit.
- Result: `9 failed, 98 passed`, exactly the nine
  `TestCLIRejectsRetiredSpecs` tests. Representative assertion:
  `assert '2023-08' in "Error: Configuration file not found. Run 'jltsql
  init' first.\n"`.
- Root cause: the root Click callback requires a config file for every
  subcommand except `init`, and its default path is resolved relative to the
  repository source tree (`Path(__file__).parent.parent.parent /
  "config/config.yaml"`), not the CWD. CI has only `config.yaml.example`, so
  the callback exits 1 before the subcommand retired-spec guard runs; the
  tests never reached the behavior they assert. (A checkout that happens to
  have a local `config/config.yaml` would mask this, which is why it slipped
  through the PR author's local run.)
- Contract decision: keep configuration as the root prerequisite. The tests
  were repaired to write a minimal config satisfying `_validate_config`
  (`jvlink`, `database.type`, one enabled database, `auto_update_check:
  false` to avoid the update probe) inside `isolated_filesystem()` and to
  pass it via `--config`, reaching the real subcommand guard. No business
  validation was moved into the root callback.

### Red-first direct-boundary evidence (unchanged production code)

- Added `TestWrapperRejectsBeforeCOM` and `TestBridgeRejectsBeforeTransmission`
  to `tests/test_retired_data_specs.py`. Both build the object via `__new__`
  (same technique as `TestFetcherRejectsBeforeReachingJVLink`) and stub only
  the downstream layer (`_jvlink` COM mock / `_send_command` mock) with a
  successful JVOpen response, so "the guard fired before transmission" is
  observable as "downstream never called".
- Command: `pytest tests/test_retired_data_specs.py::TestWrapperRejectsBeforeCOM
  tests/test_retired_data_specs.py::TestBridgeRejectsBeforeTransmission` on
  unchanged `src/`.
- Result: exit status 1, `14 failed, 2 passed`. Every retired spelling
  (DIFF, BLOD, SNAP, HOSE, TCOV, RCOV, lowercase `diff`) failed with
  `Failed: DID NOT RAISE <class 'ValueError'>`, and the captured logs show
  the retired name reaching the downstream path on both boundaries, e.g.
  `JVOpen successful data_spec=DIFF ...` (wrapper COM mock) and
  `JVOpen via bridge data_spec=RCOV ...` (bridge send). The two replacement
  tests (`DIFN` reaches the mocked downstream) passed, proving the harness
  itself exercises the real methods.
- Full run at this point: `pytest tests/test_retired_data_specs.py` →
  `14 failed, 109 passed` (the nine repaired CLI tests are green because the
  CLI guard from the PR already works once the command is actually reached).

### Implementation (after red evidence)

- `src/jvlink/wrapper.py`: import `is_retired_data_spec` /
  `retired_data_spec_message` from `src.jvlink.constants`; `jv_open` now
  raises `ValueError(retired_data_spec_message(data_spec))` before the `try`
  block, so the rejection happens before `self._jvlink.JVOpen(...)` and is
  not re-wrapped into `JVLinkError` by the method's catch-all. Docstring
  gained the same `Raises: ValueError` line historical.py uses. `jv_rt_open`
  untouched.
- `src/jvlink/bridge.py`: same imports; `jv_open` raises the same
  `ValueError` before `_send_command({"cmd": "open", ...})`, so no bridge
  command is transmitted. `jv_rt_open` untouched (realtime specs are a
  separate namespace).
- Exception type and message reuse the shared constants helpers exactly, so
  wrapper, bridge, and `HistoricalFetcher` all fail with the identical
  actionable `ValueError` naming the replacement and `2023-08`.
- `tests/test_retired_data_specs.py`: the two new boundary classes (16 tests)
  plus the CLI repair (`MINIMAL_CLI_CONFIG` + `_invoke_cli_with_config`
  helper; the nine tests now pass `--config` with a minimal valid config
  written in `isolated_filesystem()`).
- Changed files: `src/jvlink/wrapper.py`, `src/jvlink/bridge.py`,
  `tests/test_retired_data_specs.py`, this worklog. `uv.lock` was touched by
  `uv sync` (stale `jltsql` version number only) and restored with
  `git checkout -- uv.lock`.

### Validation (after implementation)

- `pytest tests/test_retired_data_specs.py` → `123 passed`, exit 0.
- `pytest tests/test_retired_data_specs.py tests/unit/test_jvlink_bridge.py
  tests/test_jvlink_wrapper.py tests/test_jvlink_constants.py` →
  `157 passed, 22 skipped` (skips are the Windows-only wrapper module),
  exit 0.
- Workflow-equivalent selection (the exact CI pytest file list from
  `.github/workflows/test.yml`, minus coverage flags) → `779 passed,
  2 skipped, 3 subtests passed`, exit 0.
- `pytest tests/test_cli.py` → `2 failed, 21 passed`
  (`TestCLIBasic::test_version_command`, `::test_status_command`).
  Pre-existing and unrelated: the same two fail on pristine HEAD
  `7e1f583` in a clean temp worktree, pass when the class runs alone
  (order-dependent), and `test_cli.py` is not in the CI selection. Not
  touched, per minimal scope.
- Blocking lint: `flake8 src tests --count --select=E9,F63,F7,F82
  --show-source --statistics` → `0`, exit 0.
- `git diff --check` → clean.

### Boundary review (unguarded public historical JVOpen paths)

- Raw transmission exists in exactly two places: `wrapper.py`
  (`self._jvlink.JVOpen(...)`) and `bridge.py` (`{"cmd": "open", ...}`),
  both now behind the guarded public `jv_open`.
- `HistoricalFetcher.fetch` / `fetch_with_cache` are guarded by the PR;
  `fetch_with_date_range` delegates to `fetch` (verified in source). CLI
  fetch / cache build (rebuild delegates to build) guarded by the PR and now
  actually exercised by tests.
- `src/fetcher/historical.py.bak_20260210_203545` is a tracked leftover
  backup containing an old `jv_open` call, but its filename is not an
  importable Python module name, so it is not a supported bypass. Pre-dates
  this PR; left alone under minimal scope (candidate for separate cleanup).
- No NAR/second bridge variant exists; all other `JVOpen`/`jv_open` hits in
  `src/` are comments, docstrings, or progress labels.
- Realtime (`jv_rt_open`, realtime fetcher/updater) intentionally untouched.

## Remaining gates

- DONE (this session): red-first direct-boundary evidence, repaired CLI test
  setup, minimal public-boundary implementation, Python 3.12 focused and
  workflow-equivalent tests green locally, blocking flake8 and
  `git diff --check` clean.
- DONE (Codex): source-branch drift reconciliation, commit, push, exact-SHA
  local verification, and GitHub Actions test/lint success for the first
  pushed candidate `341927c0d62de97be3979672e3e813e3f12a2d9b`.
- PENDING: CodeRabbit completion, independent Claude Code GREEN review
  (session `ddf27a69-bc9a-4e68-8cb6-fba082d2e181`), unresolved thread count
  zero, matching local/remote/PR head SHA, CLEAN merge state, final PR evidence
  comment, and clean worktree.

## Next safe command

Commit this worklog-only status update, push it, then re-run the required local
checks and wait for GitHub/CodeRabbit on the resulting full SHA. After Claude
Code's account limit resets, resume the independent read-only review and stop
before merge unless it returns GREEN for that exact SHA.

## Codex verification and Claude availability note

- Codex re-ran the focused boundary suite under Python 3.12.11:
  `pytest tests/test_retired_data_specs.py tests/unit/test_jvlink_bridge.py
  tests/test_jvlink_wrapper.py tests/test_jvlink_constants.py -q --no-cov` →
  `157 passed, 22 skipped`, exit 0.
- Exact workflow pytest selection including coverage → `779 passed, 2
  skipped, 3 subtests passed`, exit 0.
- Blocking flake8 gate → `0` findings, exit 0; `git diff --check` → clean.
- Informational mypy → 85 existing errors in 22 files, exit 1; the workflow
  marks this step `continue-on-error`. The reported wrapper/bridge items are
  pre-existing `no-any-return` findings, not the new guards.
- Source drift check: contributor source remains
  `b2a79a70145ddb6427fe03a7c711c5c6e3847c32`; `origin/master` remains
  `e55b1f93f4661cf83cc7d890ebe6ee7399f354ab`; local pre-candidate HEAD is
  `7e1f583aea6d027528a1eec2cf863bf1559adc7b`.
- First candidate committed and pushed as
  `341927c0d62de97be3979672e3e813e3f12a2d9b`. Exact-SHA verification repeated:
  focused `157 passed, 22 skipped`; workflow-equivalent coverage run `779
  passed, 2 skipped, 3 subtests passed`; blocking flake8 `0`; `git diff
  --check` clean. GitHub Actions run `31855794537` then completed with both
  `test` and `lint` successful; performance-test was intentionally skipped.
- Claude implementation session
  `e2ec26a4-3b59-499a-b1a7-a98c1a6b27cd` completed the edits, red/green
  evidence, boundary audit, and worklog update, then the CLI reported its
  session usage limit with reset at `13:30 Asia/Tokyo` before emitting a final
  prose summary. No Claude process remains and no edit was left in progress.
- This does not waive the user's required final Claude Code review. Commit,
  push, and Actions may proceed, but merge remains stopped until independent
  review session `ddf27a69-bc9a-4e68-8cb6-fba082d2e181` can review the frozen
  candidate and return GREEN.
- The first independent-review invocation at 2026-08-15 10:11 JST stopped
  before reading the candidate with `You've hit your session limit · resets
  1:30pm (Asia/Tokyo)`. This is an unavailable review, not a verdict, and is
  not counted as merge evidence. No file changed during the attempt.

## STOP conditions

- Stop before push if the contributor source branch moves away from
  `b2a79a70145ddb6427fe03a7c711c5c6e3847c32` without reconciliation.
- Stop before merge if any retired spelling reaches COM/bridge transmission,
  any replacement/current name is incorrectly rejected, CLI tests still fail
  before exercising their target, Actions is not successful, final Claude
  review is not GREEN, an unresolved thread exists, tested SHA and PR head
  differ, or the worktree is dirty.

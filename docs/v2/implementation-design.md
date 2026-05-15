# ma3 v2 Implementation Design

## 1. Implementation Phases

### Phase 1: Design and API Skeleton

- Add v2 API models and route skeletons behind `/v2`.
- Add design docs and initial migration plan.
- Add tests for schema validation and route availability.

### Phase 2: Knowledge Model and Migration

- Add PostgreSQL-first schema for cases and v2 relations.
- Add migration/backfill from v1 records and relations.
- Add case assignment service with deterministic, explainable recommendation output.

### Phase 3: Workflow API and Tool Service

- Add aggregated agent workflow APIs.
- Add MCP/tool service as the primary agent interface.
- Keep CLI as wrapper for diagnostics and manual one-shot commands.

### Phase 4: Transparency and Metrics

- Add Prometheus `/metrics`.
- Add stats and search explain endpoints.
- Add performance and quality regression tests.

## 2. Public API Design

All v2 server APIs live under `/v2`. v1 APIs may remain during transition but are not the primary contract.

### 2.1 Agent Workflow

`POST /v2/agent/context`

Purpose: one-call replacement for `search` followed by selected `get-record` calls.

Request fields:

- `problem`: string
- `task_type`: string
- `goal`: string
- `target`: product/component object
- `environment`: optional environment fingerprint
- `versions`: optional version info
- `observations`: optional list
- `constraints`: optional list
- `tags`: optional list
- `max_cases`: default 3
- `max_records_per_case`: default 3
- `include_explain`: default false

Response fields:

- `cases`: matched case summaries with grouped records
- `ungrouped_records`: relevant records without a case
- `warnings`: conflicts, stale records, high-risk records, missing indexes
- `explain`: optional search and ranking diagnostics
- `server`: version and feature information

`POST /v2/agent/report`

Purpose: write back an agent result and assign it to a case.

Request fields:

- existing ingest-like fields: problem, goal, actions, outcome, result_summary, evidence, target, environment, versions
- `case_id`: optional explicit case override
- `based_on_record_ids`: optional list
- `relation_type`: optional default relation to based-on records
- `case_assignment_mode`: `auto`, `explicit`, or `none`; default `auto`
- `dry_run`: default false

Response fields:

- `record`
- `case_assignment`: chosen case, confidence, candidates, reasons, whether overridden
- `relations_created`
- `feedback_created`
- `requires_manual_review`
- `review_reasons`

### 2.2 Cases

`GET /v2/cases`

- Browse accessible cases with pagination and filters: target, tags, state, updated_since, has_conflicts.

`GET /v2/cases/{case_id}`

- Return case details, canonical record, records in timeline order, relation graph summary, and aggregate metrics.

`PATCH /v2/cases/{case_id}`

- Update title, summary, state, canonical record, tags, and manual curation metadata.

### 2.3 Search Explain

`POST /v2/search/explain`

- Same matching input as `/v2/agent/context`, but returns diagnostic detail rather than agent-optimized context.
- Includes candidate counts, FTS hits, vector hits, relation/case boosts, filters, final score breakdown, and full-scan flags.

### 2.4 Transparency APIs

`GET /v2/stats/overview`

- Total records, cases, libraries, active/draft/stale/invalid distribution, relation counts, case coverage percentage.

`GET /v2/stats/search`

- Search counts, p50/p95 latency, full-scan count, zero-result count, top query intents, index health.

`GET /v2/stats/knowledge-quality`

- Records without cases, cases without canonical record, conflicting cases, stale high-use records, low-verification high-use records.

`GET /metrics`

- Prometheus text format.

### 2.5 Diagnostics

`GET /v2/doctor`

Server-side health and compatibility details:

- service version
- min supported tool version
- database backend
- migration status
- index status
- metrics enabled

Tool service and CLI `doctor` should additionally test:

- endpoint reachability
- DNS/network failure
- TLS failure
- auth failure
- role/capability mismatch
- version mismatch

## 3. Data Model

### 3.1 cases

PostgreSQL table:

- `case_id text primary key`
- `library_id text null`
- `title text not null`
- `summary text not null default ''`
- `problem_family text not null default ''`
- `target_product text not null default ''`
- `target_component text null`
- `state text not null default 'open'`
- `canonical_record_id text null`
- `tags text[] not null default '{}'`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`
- `last_record_at timestamptz null`
- `payload_json jsonb not null default '{}'::jsonb`

Indexes:

- `(library_id, state, updated_at desc)`
- `(target_product, target_component)`
- GIN on `tags`
- tsvector/GIN index over title, summary, problem_family, target fields

### 3.2 records changes

Add production columns for fields that are currently frequently read from JSON:

- `case_id text null`
- `created_at timestamptz`
- `updated_at timestamptz`
- `risk_level text`
- `verification_level text`
- `outcome text`
- `target_product text`
- `target_component text`

Keep `payload_json` for full record fidelity.

Indexes:

- `(case_id, updated_at desc)`
- `(library_id, status, updated_at desc)`
- `(target_product, target_component)`
- `(outcome)`

### 3.3 relation improvements

Keep relation rows but support case-aware graph operations:

- `from_kind`: `record` or `case`
- `from_id`
- `to_kind`: `record` or `case`
- `to_id`
- `relation_type`
- `confidence`
- `created_by`: `agent`, `system`, or `human`
- `payload_json`

For initial implementation, record-to-record relations are mandatory; case-to-case can be added once case workflows stabilize.

### 3.4 search_events summary

Store lightweight event summaries, not raw sensitive prompts by default:

- `event_id`
- `library_id`
- `created_at`
- `route`
- `latency_ms`
- `result_count`
- `case_count`
- `full_scan`
- `error_type`
- `query_hash`

This powers stats without exposing raw user data.

## 4. Case Assignment

The case assignment service runs during `/v2/agent/report` when no explicit `case_id` is supplied.

Inputs:

- normalized problem text
- task type
- target product/component
- tags
- environment
- based-on records
- vector embedding, when available

Algorithm v1:

1. If any `based_on_record_ids` belong to a case, prefer that case.
2. Otherwise retrieve candidate cases by target, tags, text search, and vector similarity.
3. Score candidates using target match, tag overlap, text similarity, vector similarity, recency, and relation proximity.
4. Assign automatically only if top score clears threshold and margin over second candidate clears threshold.
5. Otherwise create a new case.
6. Return all candidates and reasons in `case_assignment`.

Explicit `case_id` always wins if the caller has write access to that case.

## 5. Search and Ranking

The v2 search service should:

- batch-load records, feedback, relations, and cases
- avoid per-record repository calls in scoring loops
- use PostgreSQL indexes for candidate generation
- group final records by case
- surface conflicts and supersession status in response warnings
- optionally return explain data
- retrieve a larger internal candidate pool than the final UI/API limit so later v2 reranking does not discard exact metadata matches too early
- apply deterministic v2 reranking after v1 candidate generation so explicit user-selected metadata can override noisy broad lexical matches

Ranking signals:

- lexical match
- tag match
- target match
- environment match
- version match
- vector similarity
- verification level
- reuse feedback
- freshness
- relation penalties and boosts
- case canonical record boost
- stale/superseded penalties

### 5.1 Deterministic Metadata Reranking

Observed failure mode: a query with exact rare tags such as `rdma`, `ucx`, `hpc-x`, `jobssh`, and `taskrole`
can return broad `ltp`/`job` matches while missing the intended record. This happens when high-frequency terms dominate
the v1 candidate order or when the requested `max_cases * max_records_per_case` truncates candidates before case grouping.

v2 reranking must therefore add an explainable deterministic boost on top of the v1 match score:

- exact tag overlap: boost every query tag that exactly matches a record tag, case-insensitively
- rare tag boost: additional boost for longer/specific tags and tags containing digits, `-`, `_`, or `+`
- multi-tag synergy: additional boost when three or more query tags match the same record
- target boost: exact product and component matches add score; partial product/component mismatch should not suppress exact rare-tag matches but must be visible in explain
- title/problem text exact term boost: rare query tags appearing in record title/summary/claim receive a smaller boost even if the record tags are incomplete
- candidate expansion: `/v2/agent/context` should ask v1 search for at least 50 internal primary candidates, capped at a safe upper bound, while returning only the requested case/record limits
- exact metadata candidate generation: explicit query tags should add candidates through exact tag lookup independent of FTS tokenization, so punctuation-heavy rare tags such as `hpc-x` are not lost before reranking
- low-verification knowledge handling: `L0` records remain filtered by default, but may be returned when they match at least three explicit query tags; explain must show that they are low-verification so users can treat them as candidates for review rather than fully trusted fixes

The reranking config is versioned. Any weight changes must update `ranking_config_version`, update this document, and add/adjust tests.

### 5.2 Search Explain Debug Output

`/v2/search/explain` should make ranking mistakes diagnosable without storing raw sensitive prompts.

When `include_explain=true`, the response should include:

- `score_breakdown`: final ordered candidates with base score, v2 boost score, final score, reasons, matched query tags, and target-match flags
- `stages`: candidate generation, v2 reranking, and case grouping counts
- `debug_candidates`: top reranked candidates, including candidates that did not make the final returned case list
- `candidate_pool_limit`: the internal candidate limit used for v1 retrieval

The UI should display these fields so a user can see why an expected case was below the returned cut line.

Raw problem text remains excluded from persistent operation logs by default. Query replay may store normalized tags/target/task type/result IDs and score summaries, but raw prompt retention must remain explicit and visible in `/v2/doctor`.

## 6. MCP / Tool Service

The v2 local tool service is the primary integration point for agents.

Tools:

- `ma3_context`: calls `/v2/agent/context`
- `ma3_report`: calls `/v2/agent/report`
- `ma3_case`: reads a case timeline
- `ma3_search_explain`: diagnostic search
- `ma3_doctor`: endpoint/auth/version diagnostics

Responsibilities:

- keep process warm
- reuse HTTP connections
- cache health/version/whoami responses briefly
- batch repeated record/case reads
- present compact agent-friendly output
- preserve full JSON output on request

The existing CLI should call the same internal client library used by the tool service.

## 7. Metrics

Prometheus metrics:

- `ma3_http_requests_total{route,method,status}`
- `ma3_http_request_duration_seconds{route,method}`
- `ma3_search_requests_total{path}` where path is `fts`, `vector`, `hybrid`, or `full_scan`
- `ma3_search_duration_seconds`
- `ma3_search_results_total`
- `ma3_search_zero_results_total`
- `ma3_ingest_total{outcome,risk_level}`
- `ma3_case_assignment_total{result}` where result is `explicit`, `auto_existing`, `auto_new`, `ambiguous_new`
- `ma3_case_assignment_confidence`
- `ma3_db_query_duration_seconds{operation}`
- `ma3_doctor_failures_total{failure_type}`

Implementation can start with an in-process metrics collector and Prometheus text rendering to avoid adding heavy dependencies. If dependency policy allows it later, switch to `prometheus-client`.


## 8. Iteration and Quality Feedback Loop

v2 should make knowledge and search quality continuously improvable, not just observable.

### 8.1 Search Feedback

Add a lightweight feedback channel for agent or human judgments on search results.

`POST /v2/search/feedback`

Request fields:

- `query_id` or `query_hash`: identifies the search event without requiring raw prompt storage
- `record_id`: optional, when feedback targets one result
- `case_id`: optional, when feedback targets a case group
- `judgment`: `useful`, `not_useful`, `missing_expected_result`, `ranking_wrong`, or `unsafe`
- `expected_record_id`: optional for ranking or missing-result feedback
- `comment`: optional redacted free text

Usage:

- Feed aggregate quality metrics.
- Identify records/cases that are frequently rejected.
- Provide training/evaluation data for ranking changes.
- Surface curation tasks when records are stale, unsafe, or misleading.

### 8.2 Query Replay

Store a privacy-preserving search event summary so ranking changes can be evaluated against historical traffic.

Stored replay fields:

- `query_hash`
- redacted or normalized query features
- target, tags, task type, environment categories
- result record IDs and case IDs
- score breakdown summary
- feedback judgments, when available
- ranking config version

Replay workflow:

1. Select a sample of historical query summaries.
2. Run the current and candidate ranking configs against the same inputs.
3. Compare zero-result rate, judged-useful rate, rank movement, latency, and full-scan rate.
4. Promote ranking config only if quality improves without unacceptable latency regression.

Raw user prompts should not be stored by default. If raw query retention is enabled for a controlled environment, it must be explicit and visible in `/v2/doctor`.

### 8.3 Quality Dashboard APIs

Add API-only dashboard endpoints before building any UI.

`GET /v2/stats/quality-actions`

Returns prioritized curation tasks such as:

- high-use stale records
- high-use low-verification records
- cases with unresolved conflicts
- orphan records without cases
- cases without canonical records
- records repeatedly marked `not_useful`
- frequent zero-result query clusters
- ambiguous case assignment clusters

Each task should include a reason, severity, affected case/record IDs, and suggested next action.

### 8.4 Versioned Ranking Experiments

Ranking and case-assignment behavior should be versioned.

Add a `ranking_config_version` to search responses, search event summaries, and replay reports.

A ranking config includes:

- signal weights
- candidate generation limits
- case assignment thresholds
- stale/superseded penalties
- full-scan fallback policy
- canonical-record boost policy

Operators should be able to compare config versions through query replay before making a new config the default. Initial implementation can keep configs in code; later versions can move them to database-backed admin configuration.

## 9. Migration Plan

1. Add v2 tables without modifying existing v1 payloads.
2. Backfill records with extracted production columns.
3. Create cases:
   - records connected by `derived_from`, `supersedes`, or `same_problem_family` share a case
   - otherwise group by compatible library, target, problem_family, tags, and semantic similarity
4. Set each record's `case_id`.
5. Pick canonical record per case using verification level, outcome, freshness, and supersession relation.
6. Store migration report with counts, ambiguous groups, and skipped records.

Migration must be idempotent and support dry-run.


### 9.1 v1 to v2 Case Backfill

When a v2 instance is restored from a v1 production PostgreSQL dump, existing v1 records remain readable because v2 keeps the legacy tables and `Record.case_id` is optional. However, the restored data is not fully v2-native until cases are generated and records are assigned to cases.

Add `server/scripts/migrate_v1_to_v2_cases.py` with:

- `--dry-run`: compute groups and report without writes.
- `--apply`: create/update cases and write `case_id` into record payloads.
- `--report PATH`: write a JSON migration report.

Backfill rules:

1. Build connected components from v1 record relations, prioritizing `derived_from`, `supersedes`, `same_problem_family`, and `conflicts_with` as evidence that records belong to the same problem thread.
2. For records not connected by relations, group only by conservative exact keys: library, target product/component, problem family, and tags. Avoid aggressive semantic merging in the first migration.
3. Records that still have no compatible group become one-record cases.
4. Generate deterministic migration case IDs from sorted record IDs so reruns are idempotent.
5. Choose `canonical_record_id` by verification level, successful outcome, freshness, and whether the record is superseded.
6. Preserve legacy record payloads except for adding/updating `case_id`.
7. Produce a report containing counts, created/updated cases, assigned records, orphan records before/after, and ambiguous groups.

The LTP bootstrap path should run this migration after restoring the dump and before marking the instance ready. Delta sync remains disabled until a versioned idempotent delta protocol exists; future delta imports must run incremental case assignment for new or changed records.

## 10. Testing


### Design-to-Test Traceability

Every design section must have corresponding verification. For each feature, API, migration, deployment path, UI page, logging behavior, or observability surface, the implementation must identify at least one of:

- unit test
- API/e2e test
- migration test
- deployment/bootstrap test
- performance regression test
- observability/metrics assertion
- manual acceptance checklist when automation is not practical yet

A change is not complete until tests or an explicit manual acceptance checklist cover the design intent, major edge cases, and important failure modes. When design changes, update the test plan in the same patch.

### Unit tests

- case scoring and threshold behavior
- explicit case override permission checks
- relation batch loading
- search explain score breakdown
- doctor error classification
- metrics rendering

### API tests

- `/v2/agent/context` returns grouped cases and records
- `/v2/agent/report` creates record and assigns case
- `/v2/search/explain` returns candidate and scoring diagnostics
- `/v2/search/explain` ranks exact rare-tag and target matches above broad high-frequency lexical matches
- `/v2/search/explain` exposes base score, v2 boost score, final score, matched tags, target-match flags, internal candidate pool limit, and debug candidates
- Search returns `L0` knowledge only when it has strong explicit metadata evidence, such as three or more exact query tag matches, and explains the low-verification reason
- `/v2/stats/*` returns consistent aggregate counts
- `/v2/cases` topic filters return only matching cases and support offset/limit pagination
- `/ui/topics` renders topic drill-down links and `/ui/cases` consumes query parameters for filtered pagination
- `/ui/search-explain` renders an interactive form, calls `/v2/search/explain`, displays cases/explain diagnostics, and can submit `/v2/search/feedback` judgments
- `/metrics` exposes expected metric names

### Migration tests

- v1 relation chain becomes one case
- unrelated records remain separate cases
- rerunning migration is idempotent
- dry-run produces report without writes

### Integration tests

- MCP tool flow: context → agent action simulation → report
- CLI doctor identifies missing auth, invalid token, TLS failure, and network failure
- Codex local flow verifies the ma3 tool is visible and can call v2 context/report when credentials exist

### Performance tests

- compare v1-style multi-call flow against v2 context flow
- assert search does not perform per-record feedback/relation queries
- measure p50/p95 for seeded libraries with increasing record counts

## 11. Initial File/Module Layout

Expected server additions:

- `server/app/api/routes_v2_agent.py`
- `server/app/api/routes_v2_cases.py`
- `server/app/api/routes_v2_stats.py`
- `server/app/models/v2.py`
- `server/app/services/case_service.py`
- `server/app/services/v2_search_service.py`
- `server/app/services/metrics_service.py`
- `server/app/services/doctor_service.py`
- `server/app/storage/v2_repositories.py`
- `server/scripts/migrate_v2_cases.py`

Expected client/tool additions:

- shared v2 client library extracted from `ma3_client.py`
- MCP/tool service entrypoint
- CLI `doctor`, `context`, `report`, and `case` commands as wrappers

## 12. Rollout

1. Land docs and tests for intended API contracts.
2. Add schema and migration dry-run.
3. Add server v2 APIs behind feature flag.
4. Add tool service and CLI wrappers.
5. Run migration in staging and inspect stats/explain output.
6. Switch agent instructions to prefer v2 tool service.
7. Deprecate v1 agent loop after v2 proves stable.

## 13. LTP Deployment Implementation

v2 includes deployment assets under `deploy/ltp/` so a single LTP job can start a prod-like ma3 instance without manual file upload after container startup.

### 13.1 Backup Manifest

`deploy/ltp/backup_postgres.sh` writes both a compressed PostgreSQL dump and a manifest:

- `ma3db_YYYYMMDDTHHMMSSZ.sql.gz`
- `ma3db_YYYYMMDDTHHMMSSZ.manifest.json`
- `latest.manifest.json` symlink

The manifest records dump checksum, dump size, database name, git commit, public base URL, record count, latest record timestamp, WAL LSN, and a `delta_cursor` object. Restore must verify SHA256 before importing.

### 13.2 LTP Bootstrap

`deploy/ltp/bootstrap_ma3_ltp.sh` runs inside the LTP container and performs:

1. Validate required secrets and parameters.
2. Optionally mount CephFS with `ceph-fuse` before touching backup or instance-manifest paths.
3. Start or verify PostgreSQL.
4. Clone ma3 from `MA3_GIT_REPO`.
5. Checkout `MA3_GIT_REF` and optionally pin to `MA3_GIT_COMMIT`.
6. Create Python virtualenv and install server requirements.
7. Restore the backup via `restore_postgres.sh`.
8. Normalize restored PostgreSQL JSON payload columns (`records`, `feedback`, `relations`) from legacy `TEXT` to `JSONB` before any JSONB operator is used.
9. Run `server/scripts/migrate_v1_to_v2_cases.py --apply` by default, writing a migration report under the instance workdir. `MA3_RUN_V1_TO_V2_MIGRATION=0` may disable this only for debugging.
10. Write a root-only runtime env file with `MA3_DATABASE_URL`, `MA3_API_KEY`, `MA3_PUBLIC_BASE_URL`, `MA3_INSTANCE_ID`, `MA3_GIT_COMMIT`, operation-log settings, and migration report path.
11. Start uvicorn and verify `/healthz` plus `/v2/doctor`.
12. Write an instance manifest to shared storage, including migration status/report path and excluding all secrets.
13. Tail logs to keep the LTP job alive.

### 13.3 LTP Job Template

`deploy/ltp/ma3_ltp_job.yaml.template` defines a single-node ma3 task role. The template expects secrets for:

- `MA3_ADMIN_KEY`
- `MA3_POSTGRES_PASSWORD`
- `MA3_GIT_TOKEN` or `MA3_GIT_SSH_KEY`

The template should be rendered with a pinned code ref and deployment parameters before submission. The Docker image should contain system dependencies such as Git, curl, Python venv support, PostgreSQL server/client, and any storage mount tooling required by the cluster. `bootstrap_ma3_ltp.sh` makes a best-effort `apt-get` install of missing Git/curl/Python/PostgreSQL packages on Debian/Ubuntu images, but a prebuilt internal image remains preferred for reproducibility.

If `MA3_BACKUP_DIR` points at CephFS, the LTP job must explicitly mount CephFS
inside the container. Do not use `enableLocalStorage.hostpath=/mnt/cephfs` for
this: a validation run on 2026-05-14 showed that this produced an empty
worker-local XFS path, not the submit host's CephFS backup directory.

The supported CephFS path is:

- `MA3_CEPHFS_ENABLE=1`
- `MA3_CEPHFS_USER=<ceph user>`
- `MA3_CEPHFS_KEYRING=<full current keyring from LTP secret>`
- `MA3_CEPHFS_MOUNT=/mnt/cephfs`
- `MA3_CEPHFS_FS_NAME=mycephfs`
- `MA3_CEPHFS_MON=10.100.65.50,10.100.65.51,10.100.160.70`

`MA3_CEPHFS_KEYRING` must be copied from the CephFS keyring portal
(`https://ceph-user.zhilicon.com`) close to submission time and passed via LTP
secrets. Do not assume an old local keyring cache is still valid: an expired or
reset keyring causes `ceph-fuse`/`ceph` authentication errors even if the file
header still matches the user.

`bootstrap_ma3_ltp.sh` should run the internal Ceph bootstrap helper, install
`ceph-common`/`ceph-fuse`, write the keyring and `/etc/ceph/ceph.conf`, validate
that the keyring identity matches `MA3_CEPHFS_USER`, mount with `ceph-fuse`,
wait for the path to become a real mountpoint, and only then create
`$MA3_BACKUP_DIR/instances` or call `restore_postgres.sh`. This ensures
`latest.manifest.json` and the dump file are read from real CephFS rather than
from an accidentally-created local directory.

`restore_postgres.sh` must fail fast when the manifest is missing so a broken
storage mapping does not silently start an empty instance.

LTP bootstrap should default to a lightweight server dependency file, `server/requirements-ltp.txt`, controlled by `MA3_REQUIREMENTS_FILE`. The LTP file excludes `sentence-transformers`/torch and sets `MA3_DISABLE_EMBEDDINGS=1`; ma3 already degrades to lexical/search-only behavior when embeddings are disabled. Full embedding dependencies can be enabled later by using `server/requirements.txt` in an image with cached wheels. This avoids CPU job startup failures and long pip installs.

The restore path must tolerate environment-specific backup paths. If a manifest's `dump_path` is an absolute path from another host, `restore_postgres.sh` should fall back to a dump with the same basename in the manifest directory, then to `dump_file`. Bootstrap must also detect the actual PostgreSQL cluster port with `pg_lsclusters` when `PGPORT` was not explicitly supplied; LTP shared-node jobs can have another service already listening on `127.0.0.1:5432`, so `pg_isready localhost:5432` is not sufficient proof that the job-local PostgreSQL cluster is the one being used. Detection should retry briefly after `pg_ctlcluster start` and fail fast if no job-local online cluster is visible. PostgreSQL role/database setup must run through the `postgres` system account against that detected port, explicitly clear inherited `PGUSER`/`PGHOST`/`PGPASSWORD` client environment while doing admin operations, set the ma3 user password without shell-interpolating secrets into SQL, and fail fast instead of hiding setup errors.

The template passes `MA3_RUN_V1_TO_V2_MIGRATION` to the bootstrap script. The default submitted v2 instance should keep it enabled so a restored v1 dump becomes v2-native before agents start using the instance.

Restored v1 PostgreSQL dumps may contain `payload_json` columns as `TEXT`
because v1 schema and SQLite-compatible code stored JSON as serialized strings.
The v2 PostgreSQL initializer must run `ALTER TABLE ... ALTER COLUMN
payload_json TYPE JSONB USING payload_json::jsonb` for existing `records`,
`feedback`, and `relations` tables before running status backfills, FTS, or v2
case migration. This conversion is idempotent for already-JSONB columns.

Because LTP CPU jobs may share the node network namespace with existing
services, the submitted `MA3_PORT` must be a high, job-specific port instead of
assuming `8000` is free. Bootstrap must not treat a generic `/healthz` response
as sufficient: after starting uvicorn it must verify that the child process is
still alive and that `/v2/doctor` reports this exact `MA3_INSTANCE_ID` (and, when
set, `MA3_GIT_COMMIT`). This prevents false positives where `127.0.0.1:$PORT`
is already occupied by another service on the node.

### 13.3.1 LTP Deployment Tests

Deployment changes must be checked with:

- `bash -n deploy/ltp/bootstrap_ma3_ltp.sh`
- static inspection that `ma3_ltp_job.yaml.template` passes
  `MA3_CEPHFS_ENABLE`, `MA3_CEPHFS_USER`, and the secret-backed
  `MA3_CEPHFS_KEYRING`
- a unit/static check that `bootstrap_ma3_ltp.sh` validates the keyring identity
  and waits for `mountpoint -q $MA3_CEPHFS_MOUNT` before reading backups
- a unit/static check that LTP health validation requires the uvicorn process to
  be alive and `/v2/doctor.instance_id == MA3_INSTANCE_ID` before writing the
  instance manifest
- a unit/static check that PostgreSQL setup uses the detected `PGPORT` for
  `psql`/`createdb`, uses `--set=ma3_password` rather than embedding the secret
  in SQL, and does not hide role/database setup errors
- a unit check that the PostgreSQL initializer emits JSONB normalization SQL for
  legacy `payload_json` columns before JSONB operators are used
- one fresh LTP submission using a pinned commit, no `deliver_assets`, and a real
  CephFS keyring secret; success requires `/healthz` and `/v2/doctor` to pass
  from inside the container before any SSH hot patching

### 13.4 Dynamic agents.md Base URL

`GET /agents.md` dynamically replaces the source default `https://hjk41.cc` with `MA3_PUBLIC_BASE_URL` when set. This removes the old deployment requirement to run `sed -i` after every code sync.

`GET /healthz` and `GET /v2/doctor` expose `public_base_url`, `instance_id`, and `git_commit` for instance verification.

### 13.5 Delta Sync Policy

The first implementation keeps `MA3_ENABLE_DELTA=0`. Delta import remains a placeholder until ma3 has a versioned and idempotent protocol that covers all mutable knowledge objects and tombstones. Do not enable delta in production-like clones until that protocol exists and has replay tests.

### 13.6 Production Cutover to an LTP v2 Instance

Switching `ma3.zhilicon.com` from v1 production to a v2 LTP instance is a
user-impacting operation. It must be treated as a controlled cutover rather than
as a normal debug redeploy.

The cutover design is:

1. **Document and announce the exact target instance.** Record the LTP job name,
   SSH endpoint, `MA3_INSTANCE_ID`, `MA3_GIT_COMMIT`, service port, and expected
   public URL before changing DNS or nginx.
2. **Use a final full backup, not best-effort delta.** Until a versioned
   idempotent delta protocol exists, data completeness is proven by taking a
   fresh production PostgreSQL backup immediately before cutover and restoring
   that manifest into the target v2 instance (or into a new v2 instance launched
   from that manifest). A clone restored from an older `latest.manifest.json`
   is not sufficient for production cutover.
3. **Quiesce or minimize writes during the final backup window.** To guarantee no
   v1 writes are missed, either briefly freeze/stop v1 writes before the final
   backup or accept and explicitly document a bounded write-loss risk. The
   default production rule is no intentional loss: freeze v1 writes, take the
   final backup, restore/migrate v2, then switch traffic.
4. **Compare data counts and high-water marks.** Before switching traffic,
   compare v1 production and v2 target for:
   - library count
   - token count
   - record count
   - feedback count
   - relation count
   - v2 case count and `records_with_case == records_total`
   - latest record/update timestamp from the backup manifest and from the
     restored database
5. **Verify runtime identity from both sides.** The v2 target must pass
   `/healthz` and `/v2/doctor`, and those responses must report the planned
   `MA3_INSTANCE_ID`, `MA3_GIT_COMMIT`, `database_backend=postgresql`, and
   `public_base_url=https://ma3.zhilicon.com`.
6. **Switch through dns-manager/nginx, not direct LTP HTTPS.** The LTP job keeps
   serving HTTP on its high internal port. Public HTTPS is terminated by the
   existing `dns.zhilicon.com`/dns-manager/nginx infrastructure on the infra
   host. The dns-manager record for `ma3` should point to the v2 backend IP/port
   with proxy enabled, then nginx config must be generated, tested, and reloaded.
7. **Issue or reinstall the certificate through dns-manager ACME DNS-01.** The
   supported HTTPS path is `acme.sh --dns dns_dnsmanager` with
   `DNSMANAGER_URL=http://localhost:8053` on the infra host and a valid
   `DNSMANAGER_TOKEN` supplied from an LTP token. Certificates must be installed
   to the nginx certificate directory and `nginx -s reload` must be part of the
   install/renew hook. Do not print tokens or private keys.
8. **Post-cutover verification gates.** After DNS/nginx/HTTPS change, verify:
   - `https://ma3.zhilicon.com/healthz`
   - `https://ma3.zhilicon.com/v2/doctor`
   - `https://ma3.zhilicon.com/client/manifest.json`
   - `https://ma3.zhilicon.com/ui/overview`
   - one authenticated v2 search/explain request
   - one non-mutating v1 compatibility search request if v1 clients are still in use
9. **Install the v2 database backup cron before declaring cutover complete.**
   Once traffic points at v2, v2 becomes the write source of truth. A root-only
   cron wrapper on the LTP instance must run `deploy/ltp/backup_postgres.sh`
   against the v2 PostgreSQL database and write fresh manifests/dumps to the
   same CephFS backup directory. Run one manual backup after cutover and after
   any validation write-back so the latest post-cutover data is captured.
10. **Rollback path.** Keep the old v1 backend process and its last backup intact
   until the HTTPS checks and agent smoke tests pass. Rollback is to restore the
   dns-manager `ma3` record to the previous backend IP/port, regenerate/reload
   nginx, and verify `https://ma3.zhilicon.com/healthz`.

#### 13.6.1 Production Cutover Tests

Every cutover run must collect evidence for:

- final v1 backup manifest timestamp, record count, latest record timestamp, and
  checksum verification during restore
- v1/v2 count comparison for libraries/tokens/records/feedback/relations
- v2 migration report showing no orphan records and successful case assignment
- `/healthz` and `/v2/doctor` identity checks on the target before DNS cutover
- nginx config test (`nginx -t`) before reload
- HTTPS certificate subject/issuer/notAfter check after install
- external HTTPS smoke checks after DNS cutover
- v2 backup cron syntax check, crontab entry, and one successful post-cutover
  backup manifest
- rollback record: previous backend IP/port and command/API path used to restore
  it if validation fails

## 14. Knowledge Observatory Web UI Implementation

The first web UI should be a lightweight static frontend served by FastAPI under `/ui`. It should use v2 APIs and avoid direct database coupling.

### 14.1 MVP Pages

- `/ui/overview`: consumes `/v2/stats/overview`, `/v2/stats/search`, and `/v2/stats/knowledge-quality`.
- `/ui/topics`: consumes a new `/v2/topics` API that aggregates records/cases by product, component, tags, problem family, and case clusters. Every topic bucket is a drill-down link to `/ui/cases?topic_kind=...&topic=...`.
- `/ui/cases`: consumes `/v2/cases` and `/v2/cases/{case_id}`. It accepts optional `topic_kind`/`topic` query parameters and paginates the filtered case list with `limit`/`offset`.
- `/ui/search-explain`: provides an interactive query form for problem/task/goal/target/tags/max results plus an optional locally saved API key, submits to `/v2/search/explain`, renders grouped cases plus score breakdown/stages/query hash, and writes useful/not-useful judgments to `/v2/search/feedback`.
- `/ui/quality-actions`: consumes `/v2/stats/quality-actions`.

### 14.2 Additional APIs

Add these APIs before or alongside the UI:

- `GET /v2/topics`: topic distribution and coverage metrics.
- `GET /v2/cases?topic_kind=product|component|tag|problem_family&topic=...&limit=...&offset=...`: filtered case list for topic drill-down. The filter is applied to case metadata and to records assigned to each case, so migrated cases remain discoverable even if the case-level tags are sparse.
- `GET /v2/graph?case_id=...|record_id=...|q=...`: 1-2 hop knowledge graph for selected objects.
- `PATCH /v2/records/{record_id}/review`: curation actions such as stale, verification level, tags, and summary edits.
- `PATCH /v2/cases/{case_id}/canonical-record`: set the canonical record.
- `POST /v2/cases/{case_id}/merge`: merge duplicate cases.
- `POST /v2/cases/{case_id}/relations`: add case/record relations.

### 14.3 Frontend Choice

MVP can use a simple Vite/React frontend or static HTML with HTMX/Alpine. Prefer a minimal dependency set. Recommended visualization libraries:

- ECharts for overview, topic distribution, and trends.
- Cytoscape.js for the knowledge graph.
- TanStack Table or a simple table component for case/record lists.

### 14.4 Access Control

Initial UI can be protected by the existing admin/library token model. Review and mutation actions require write/admin permissions. Read-only views follow the same library visibility rules as v2 APIs.

### 14.5 Review Workflow

The UI should support lightweight governance operations:

- mark record stale or invalid
- set canonical record
- merge/split cases
- add `supersedes`, `conflicts_with`, or `same_problem_family` relation
- raise/lower verification level
- edit tags and summaries
- resolve conflict notes

All review operations must emit operation log events.

## 15. Operation Logging and Log Archival

ma3 should record operation logs for later analysis. Current volume is expected to be low, so a simple append-only JSONL log is sufficient for the initial implementation.

### 15.1 What to Log

Log every meaningful operation, including:

- HTTP request summary: method, route, status, latency, actor type, library id, request id.
- Agent operations: context search, report ingest, case assignment result, risk assessment result.
- Search explain and feedback submissions.
- Review operations from the web UI.
- Case mutations: create, update, merge, canonical record changes.
- Record mutations: create, update, reject, delete, stale, verification changes.
- Relation mutations.
- Backup/restore/bootstrap events.
- Doctor failures and startup health events.

Do not log raw secrets. Free-text payloads should be redacted or summarized. Raw query logging should remain disabled by default; store query hash and redacted feature summary unless explicitly enabled.

## 16. Submission Redaction and Anonymization Control

Write-time redaction must protect secrets without destroying valuable operational knowledge. Paths, hostnames, IPs, email addresses, and similar infrastructure identifiers can be either sensitive or essential retrieval/diagnostic context. For example, replacing the actual HPC-X `mpirun` path with `<redacted_path>` can make an LTP/MPI knowledge record much less useful.

### 16.1 Agent Detection and User Choice

ma3 is primarily an agent tool. The agent/client should detect potentially sensitive or contextual values before submission, explain what it found, and ask the user whether to anonymize them. The server should not infer policy from library type; it should only apply the submitter's explicit choice.

Detected values include paths, IPs, emails, API keys, tokens, passwords, private keys, AWS access keys, long opaque tokens, and explicit secret assignments.

### 16.2 API Contract

Submission APIs that create records accept a `redaction_mode` field:

- `auto` (default): redact detected contextual and sensitive values.
- `none`: preserve detected values exactly as submitted.

Initial coverage:

- `POST /agent/ingest`
- `POST /v2/agent/report`
- `POST /knowledge`

Direct low-level `POST /records` keeps default `auto` behavior for now unless an explicit API extension is designed later.

Stored records do not need to persist `redaction_mode`; it is a submission-time control.

### 16.3 Client Interaction

The bundled CLI should detect contextual identifiers and secret-like values before write operations. If running interactively and no explicit `--redaction-mode` or payload `redaction_mode` is provided, it should prompt:

- redact detected values (default, safer), or
- keep detected values.

Non-interactive callers keep the default `auto` mode unless they explicitly pass `redaction_mode` or `--redaction-mode`.

### 16.4 Tests

Tests must verify:

- default submissions still redact paths/IPs/emails and secrets
- `redaction_mode=none` preserves paths/IPs/emails and secrets
- v1 agent ingest, v2 agent report, and `/knowledge` honor the mode

## 17. Client/Skill Upgrade Detection and Auto-Update

ma3 is an agent tool, so an already-installed v1/v2 client skill should be able to
notice that the server has moved forward and update itself before the agent depends
on stale instructions or an incompatible CLI.

### 17.1 Server Contract

`GET /healthz` advertises the client compatibility envelope:

- `min_client_version`: hard compatibility floor. Clients older than this must update before use.
- `recommended_client_version`: soft desired client version. Clients older than this should update at warmup.
- `client_manifest_url`: canonical URL path for the server-published client file manifest.

`GET /client/manifest.json` returns the files that make up the installable skill package:

- `client_version`
- `min_client_version`
- `recommended_client_version`
- `files[]` with `path`, `url`, `sha256`, and `size`

The manifest uses plugin-relative paths such as `skills/ma3/scripts/ma3_client.py`
so the same update flow works for Codex, Claude Code, and direct script installs.

### 17.2 Client Behavior

- `healthz` remains non-mutating: it reports `version_warning` or
  `recommended_version_warning` when the server says the local client is old.
- `self-update` first downloads `/client/manifest.json`, verifies each downloaded
  file's SHA256 when provided, and writes the manifest paths into the local plugin
  root. If the manifest is unavailable it falls back to the legacy hard-coded file
  list, then to `git pull`.
- `warmup` is the automatic detection point. It checks `/healthz`; when the local
  `CLIENT_VERSION` is below `min_client_version` or `recommended_client_version`,
  it runs `self-update` once, reports `self_update_performed: true`, and asks the
  agent to rerun warmup before continuing. The current process does not re-exec
  because the Python code already loaded may be the old version.
- `MA3_DISABLE_AUTO_UPDATE=1` disables the `warmup` mutation path for debugging
  and hermetic tests.

Agent-facing docs must instruct agents to run `warmup` before the first ma3
operation in a turn. If warmup updates the local skill, rerun warmup once and then
continue with search/ingest.

### 17.3 Tests

Tests must verify:

- `/healthz` exposes `recommended_client_version` and `client_manifest_url`.
- `/client/manifest.json` includes the CLI, skill docs, agent docs, and examples
  with valid `sha256` and `size`.
- Client code still compiles after self-update changes.

### 15.2 Log Format

Use JSONL with one event per line. Suggested fields:

- `ts`
- `event_type`
- `request_id`
- `actor_type`
- `token_id`
- `library_id`
- `route`
- `method`
- `status`
- `latency_ms`
- `record_id`
- `case_id`
- `relation_id`
- `query_hash`
- `operation_result`
- `error_type`
- `payload_summary`
- `instance_id`
- `git_commit`

### 15.3 Local Retention and CephFS Sync

Write local logs to `/var/log/ma3/ops/YYYY-MM-DD.jsonl`. A daily archival script should:

1. Flush/close the current day's log if needed.
2. Compress completed logs with gzip.
3. Copy compressed logs to CephFS/3FS, for example `$MA3_LOG_ARCHIVE_DIR/$MA3_INSTANCE_ID/`.
4. Write or update a small archive manifest.
5. Delete local compressed logs older than the configured retention window.

Recommended env vars:

- `MA3_OP_LOG_DIR=/var/log/ma3/ops`
- `MA3_LOG_ARCHIVE_DIR=/mnt/3fs/data/ma3/logs`
- `MA3_LOG_LOCAL_RETENTION_DAYS=2`
- `MA3_LOG_REDACT_RAW=1`

The LTP bootstrap should start cron or a lightweight background loop to run this archival script daily. This keeps local disk bounded while preserving logs for later analysis.

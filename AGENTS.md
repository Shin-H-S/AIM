# AIM Project Instructions

## 1. Project identity

* Project name: **AIM**
* Current team size: **1 developer**
* Project type: AI-powered web service quality assessment and monitoring platform
* Current stage: MVP planning and initial implementation
* Primary language for documentation and explanations: Korean
* Code, identifiers, API paths, database fields, and commit messages should use clear English naming.

AIM stands for a platform that helps developers evaluate and monitor web services by registering a service URL and critical user flows.

AIM is not a simple uptime checker.

Its main value is:

1. Continuously checking whether a web service is available.
2. Evaluating performance, accessibility, SEO, and browser best practices.
3. Testing critical user flows in a real browser.
4. Comparing current results with previous results.
5. Detecting regressions after deployment.
6. Generating an evidence-based AI diagnosis.
7. Helping developers decide what to fix first and whether a deployment is risky.

---

## 2. Product definition

A user registers a web service URL and configures important user scenarios.

AIM then:

1. Verifies that the user owns or controls the target service.
2. Checks HTTP availability, response time, redirects, and SSL status.
3. Runs Lighthouse-based quality checks.
4. Runs Playwright-based browser scenarios.
5. Collects console errors, failed network requests, and failure screenshots.
6. Stores normalized results and raw artifacts.
7. Compares the result with a previous or baseline run.
8. Calculates a quality score and deployment risk.
9. Uses an LLM to summarize the evidence and recommend priorities.
10. Sends an alert when availability or critical functionality degrades.

The central product question is:

> “Is the newly deployed service actually more stable and better than the previous version?”

---

## 3. Primary users

AIM is initially intended for:

* Solo developers
* Side-project teams
* Early-stage startup development teams
* Teams without dedicated QA engineers
* Bootcamp and educational project teams
* Developers who need simple deployment regression checks

Do not design the MVP for large enterprises or massive traffic.

---

## 4. MVP user flow

The complete MVP flow is:

1. User signs up and logs in.
2. User creates a project.
3. User registers a service URL and environment.
4. AIM validates the URL.
5. AIM verifies domain ownership.
6. User requests the first scan.
7. The API creates a check run.
8. The scan job is placed in a queue.
9. A worker runs availability and Lighthouse checks.
10. The user creates a critical Playwright scenario.
11. A worker executes the browser scenario.
12. AIM stores results and artifacts.
13. AIM calculates category scores and overall risk.
14. AIM compares the run with the previous run.
15. AIM generates an evidence-based AI report.
16. The dashboard displays results and priorities.
17. AIM sends an alert if a critical threshold is violated.

---

## 5. MVP scope

### Required MVP capabilities

#### Authentication

* Email and password signup
* Login and logout
* JWT-based authentication
* Project ownership checks

#### Project management

* Create, read, update, and delete a project
* Register service name, URL, description, and environment
* Supported environments:

  * development
  * staging
  * production
* Configure scan interval
* Configure response-time and quality thresholds

#### Ownership verification

The first MVP should support HTML meta-tag verification.

Example:

```html
<meta
  name="aim-verification"
  content="aim_verify_generated_token"
/>
```

A target must not receive recurring scans until ownership is verified.

#### Availability checks

* DNS and connection success
* HTTP status code
* Response time
* Redirect count
* HTTPS usage
* SSL certificate validity
* SSL expiration date
* Timeout detection
* Consecutive failure detection
* Incident start and recovery time

#### Lighthouse checks

* Performance
* Accessibility
* SEO
* Best Practices
* LCP
* CLS
* TBT
* Main opportunities and diagnostics
* Mobile mode is required for the MVP
* Store normalized metrics and the raw JSON result

#### Playwright scenario checks

Initially support these actions:

* navigate
* click
* fill
* wait
* assert element exists
* assert text exists
* assert URL
* take screenshot

For each scenario run, collect:

* Overall success or failure
* Result of each step
* Failed step
* Browser console errors
* Failed network requests
* Failure screenshot
* Execution duration

#### Check-run management

Supported states:

* QUEUED
* RUNNING
* ANALYZING
* COMPLETED
* FAILED
* CANCELLED

Long-running scans must not execute inside the FastAPI request process.

#### Result history and comparison

* Store all scan runs
* Compare a run with the immediately previous run
* Support explicit baseline-versus-target comparison
* Calculate score and metric changes
* Highlight improvements and regressions

#### AI diagnosis

The AI report must include:

* Short summary
* Deployment risk
* Top issues in priority order
* Evidence for every issue
* Expected user impact
* Recommended next action
* Improved areas
* Regressed areas

The AI must distinguish:

* Confirmed observation
* Evidence-based inference
* Unknown cause

The AI must never invent:

* Source-code locations it has not inspected
* Internal server causes that cannot be inferred from external data
* Logs or metrics that were not collected
* Successful checks that did not run

#### Alerts

Initial alert triggers:

* Service connection failure
* Repeated 5xx response
* Critical scenario failure
* Performance score below threshold
* Response time above threshold
* Recovery from an incident

Alert emails are per-project opt-in and default to off; check-result emails must not be sent unless a project explicitly enables them. The planned primary alert channel is per-project Slack/Discord incoming webhooks. Keep the SMTP delivery pipeline — its primary role is transactional mail such as password reset. See [docs/decisions/0001-alert-channels-email-and-webhook.md](docs/decisions/0001-alert-channels-email-and-webhook.md).

---

## 6. Explicit non-goals for the first MVP

Do not implement these unless a task explicitly requests them:

* Kubernetes
* Kafka
* Microservice architecture
* Multi-region scanning
* Automatic code modification
* Automatic rollback
* Production database query analysis
* CPU or memory monitoring inside target services
* Full OpenTelemetry integration
* GitHub PR automatic scanning
* AI agent that directly deploys code
* Payment functionality
* Complex organization billing
* Custom LLM hosting
* Elasticsearch
* Multi-tenant enterprise RBAC
* Destructive browser scenarios such as actual payment, deletion, or production data modification

Prefer finishing the complete MVP flow over adding advanced infrastructure.

---

## 7. Initial technical architecture

Use a monorepo and a modular-monolith approach.

```text
aim/
├── apps/
│   ├── web/               # Next.js frontend
│   ├── api/               # FastAPI application
│   └── worker/            # Scan and analysis workers
├── packages/
│   └── contracts/         # Shared API contracts if needed
├── infra/
│   ├── compose.yaml
│   └── compose.dev.yaml
├── migrations/
├── docs/
│   ├── architecture/
│   ├── api/
│   └── decisions/
├── scripts/
├── tests/
├── .github/
│   └── workflows/
├── .env.example
├── AGENTS.md
└── README.md
```

Do not split the project into independent microservices unless actual scaling requirements justify it.

---

## 8. Preferred technology stack

### Frontend

* Next.js
* TypeScript
* Tailwind CSS
* TanStack Query
* React Hook Form
* Zod

### Backend

* Python 3.12 or the repository’s pinned Python version
* FastAPI
* Pydantic
* Pydantic Settings
* SQLAlchemy 2
* Alembic
* HTTPX
* PostgreSQL

### Worker and scheduling

* Redis
* Celery or the queue system already selected in the repository
* Celery Beat or an equivalent scheduler
* Playwright
* Lighthouse CLI

Do not introduce a second queue framework without a clear reason.

### Artifact storage

* MinIO for local development
* Object storage (e.g., Oracle Cloud Object Storage) for production later
* Store only artifact metadata and paths in PostgreSQL

Artifacts include:

* Failure screenshots
* Playwright traces
* Lighthouse JSON
* Lighthouse HTML reports
* Network logs
* Generated diagnosis reports

### Development and deployment

* Docker Compose for local development
* GitHub Actions for CI
* Deployment target: Oracle Cloud Ampere A1 (arm64) single VM with Docker Compose
  (migrated from GCP on 2026-07-17 — see docs/deployment/vm-compose.md)
* Future migration may use managed containers or a managed database if scale demands

Do not introduce Kubernetes during the MVP.

---

## 9. Core domain entities

Expected core entities include:

* User
* Project
* ServiceTarget
* VerificationToken
* CheckSchedule
* CheckRun
* AvailabilityResult
* LighthouseResult
* TestScenario
* TestStep
* ScenarioRun
* StepResult
* ConsoleError
* NetworkFailure
* Artifact
* ScoreResult
* AIReport
* Alert
* Incident

Keep business concepts explicit. Avoid generic names such as `Data`, `Item`, `Manager`, or `Handler` when a domain-specific name exists.

---

## 10. Scoring principles

Initial scoring categories:

* Availability: 25%
* Functional stability: 30%
* Web performance: 20%
* Accessibility: 10%
* SEO and basic quality: 5%
* Regression stability: 10%

The final score must not hide critical failures.

Apply gate rules before assigning the final grade.

Examples:

* Service unavailable → deployment risk
* Critical login scenario failure → deployment risk
* Repeated 5xx responses → deployment risk
* Response time over twice the configured threshold → deployment warning
* Performance score drop of 20 or more → deployment warning
* SEO-only regression → improvement recommendation, not automatic deployment failure

Suggested grades:

* A: Stable
* B: Minor improvements needed
* C: Verification needed before deployment
* D: Deployment risk
* F: Service unavailable or critical failure

Scoring rules must be deterministic and tested separately from LLM output.

The LLM does not calculate the authoritative score. It explains structured results produced by application logic.

---

## 11. Security requirements

AIM accepts user-provided URLs, so SSRF prevention is a core requirement.

Before requesting any user-provided URL:

* Allow only HTTP and HTTPS.
* Reject localhost.
* Reject loopback addresses.
* Reject private IP ranges.
* Reject link-local addresses.
* Reject multicast and reserved ranges.
* Reject cloud metadata endpoints.
* Resolve DNS and validate all resolved IP addresses.
* Revalidate every redirect destination.
* Set strict connection and response timeouts.
* Limit redirect count.
* Limit response size.
* Limit concurrent scans.
* Do not expose internal network information in user-facing errors.

Ownership verification is required before recurring scans.

Test credentials and browser storage state are secrets:

* Never commit them.
* Never log raw passwords, cookies, tokens, or API keys.
* Store secrets encrypted or through a secret-management abstraction.
* Mask secret values in logs and reports.

Browser workers must run with constrained permissions.

Never disable security checks merely to make a test pass.

---

## 12. Engineering rules

### General

* Prefer the smallest maintainable solution.
* Do not overengineer for hypothetical scale.
* Keep the MVP flow working end to end.
* Preserve existing behavior unless the task explicitly requests a change.
* Do not silently change public API contracts.
* Do not add a production dependency without explaining why it is needed.
* Reuse existing project patterns before introducing a new abstraction.
* Do not create empty architecture layers with no real responsibility.
* Avoid files that grow without clear boundaries.
* Use explicit types and schemas at system boundaries.
* Validate all external input.

### Backend

* Keep routers thin.
* Put business rules in application or service modules.
* Keep database access out of route handlers where practical.
* Use SQLAlchemy 2 style.
* Use Alembic for schema changes.
* Do not mutate the database schema manually without a migration.
* Use timezone-aware UTC timestamps in storage.
* Return consistent error responses.
* Make scan-task creation idempotent where appropriate.
* Use structured logs with identifiers such as:

  * project_id
  * check_run_id
  * scenario_id
  * task_id

### Worker

* A worker task must have a timeout.
* A worker task must record failure state.
* Retried tasks must not create duplicate authoritative results.
* Separate raw scanner output from normalized domain results.
* Treat browser crashes, scan timeouts, and target failures as different conditions.
* Clean up temporary files and browser processes.
* Do not let a failed AI report change a successful scan into a failed scan.
* AI report generation should be separately retryable.

### Frontend

* Use TypeScript strict mode.
* Handle loading, empty, error, and partial-result states.
* Do not present AI inference as a confirmed fact.
* Visually distinguish:

  * observation
  * inference
  * recommendation
* Critical failures must be visible without opening a detailed page.
* Do not block the entire page while a scan runs.
* Polling is acceptable for the MVP; do not add WebSockets unless required.

---

## 13. Testing and verification

When modifying code, run the checks relevant to the changed area.

Expected checks may include:

### Python

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

### Frontend

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Use the repository’s actual scripts if they differ.

Important test targets:

* URL parsing and validation
* SSRF protection
* Redirect revalidation
* Project ownership
* Verification tokens
* Check-run state transitions
* Worker timeout and retry behavior
* Score calculation
* Risk gate rules
* Comparison calculations
* AI report schema validation
* Permission checks
* Secret masking

For changes affecting a user flow, add or update an end-to-end test when practical.

Never weaken or delete a test just to make the suite pass unless the product requirement has genuinely changed and the reason is documented.

---

## 14. Documentation rules

Keep these documents current as the project evolves:

* `README.md`: setup and project overview
* `docs/architecture/`: architecture and important flows
* `docs/api/`: API contracts
* `docs/decisions/`: meaningful architectural decisions
* `.env.example`: required environment variables without real secrets

When making an architectural decision, record:

* Context
* Decision
* Alternatives considered
* Consequences

Do not duplicate large blocks of documentation across files. Link to the canonical document.

---

## 15. How to work in this repository

Before making changes:

1. Read this `AGENTS.md`.
2. Inspect the current repository structure.
3. Read relevant README and documentation files.
4. Inspect existing code and tests.
5. Check the current Git diff.
6. Identify whether the requested feature already partially exists.
7. State assumptions when repository evidence is insufficient.

For a complex task:

1. Summarize the current state.
2. Propose a short implementation plan.
3. Identify files likely to change.
4. Identify risks and security implications.
5. Implement in small, reviewable steps.
6. Run relevant tests and checks.
7. Review the final diff for regressions.

Do not rebuild working parts of the project from scratch without a demonstrated need.

Do not make unrelated cleanup changes during a focused task.

---

## 16. Response format after completing a coding task

Report:

1. What changed
2. Why it changed
3. Main files changed
4. Tests and checks executed
5. Test results
6. Remaining limitations or risks
7. Recommended next step, only when directly relevant

Clearly state when a test could not be run and why.

Never claim that a test passed unless it was actually executed successfully.

---

## 17. Current development priority

Because AIM is currently a one-person project, prioritize implementation in this order:

### Phase 1: Foundation

1. Monorepo structure
2. Local Docker Compose
3. FastAPI skeleton
4. PostgreSQL connection
5. Alembic setup
6. Next.js skeleton
7. Project CRUD
8. Basic authentication
9. URL validation
10. Domain verification

### Phase 2: First scan

1. CheckRun domain model
2. Redis task queue
3. HTTP availability scanner
4. SSL inspection
5. Scanner result normalization
6. Scan status polling
7. Basic result page

### Phase 3: Quality assessment

1. Lighthouse worker integration
2. Metric normalization
3. Artifact storage
4. Score calculation
5. Run history
6. Previous-run comparison

### Phase 4: Functional testing

1. Test scenario model
2. Supported test-step actions
3. Playwright worker
4. Step-level results
5. Console and network failure capture
6. Failure screenshots

### Phase 5: Diagnosis and alerts

1. Deterministic deployment-risk rules
2. Structured AI report input
3. Structured AI report output
4. Evidence display
5. Email alerts
6. Recovery detection

Do not skip directly to advanced AI features before the deterministic scan and comparison pipeline works.

---

## 18. Definition of MVP done

The MVP is complete when the following works end to end:

1. A user creates an account.
2. The user creates a project.
3. The user registers and verifies a service URL.
4. The user starts a scan.
5. The API queues the scan without blocking.
6. A worker runs availability and Lighthouse checks.
7. The user creates and runs at least one Playwright scenario.
8. AIM stores normalized results and artifacts.
9. AIM calculates scores and applies risk gates.
10. AIM compares the current result with a prior result.
11. AIM generates an evidence-based AI report.
12. The dashboard shows status, results, regressions, and priorities.
13. A critical failure triggers an alert.
14. Relevant automated tests pass.
15. No private or internal URL can be scanned through a known SSRF bypass in the test suite.

---

## 19. Instruction for ambiguous requests

When a request is ambiguous:

* First inspect the repository for established patterns and current progress.
* Prefer the interpretation that preserves existing architecture and MVP scope.
* Ask a question only when different interpretations would cause materially different or destructive implementations.
* Otherwise, state the assumption and proceed with the smallest reversible implementation.

The project owner will explicitly notify the repository when the team grows beyond one person. Until then, optimize for clear code, low operational burden, and solo-developer maintainability.

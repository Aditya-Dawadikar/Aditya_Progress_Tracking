# LeetCode Performance Tracker

A personal Django LMS for measuring algorithmic problem-solving ability over
time — not "how many problems have I solved," but *how* I solve them: how
fast I recognize a pattern, whether I can turn recognition into an algorithm,
how well I construct adversarial test cases, and where my implementations
actually fail.

The intended loop:

```
ChatGPT (or you) writes a TestPlan JSON
        ↓
Import it into this app
        ↓
Take the assessment — click through phases, the app times you
        ↓
Review: predicted pattern vs. the plan's answer key, timing breakdown,
        expected vs. actual failure modes
        ↓
Export CSV
        ↓
Feed the CSV back to an LLM to plan the next assessment
```

This app is deliberately *not* a general LeetCode tracker, not a scraper, and
does not talk to an LLM itself — it's the measurement instrument in the
middle. See `Instructions.md` / `Instructions2.md` (untracked, local planning
docs) for the full original spec.

## Tech stack

Django monolith, SQLite, server-rendered templates, vanilla JS for the phase
timer. No React, no REST API, no Celery/Redis. `Dockerfile` + Railway config
for deployment; everything also runs with zero config via `manage.py
runserver`.

## Core domain model

```
TestPlan            — curriculum: what SHOULD be tested (imported as JSON)
  └─ TestPlanProblem — one problem in that plan, + hidden evaluator metadata
       └─ ExpectedFailureMode

Test                 — one actual execution of a plan (or an ad-hoc test)
  └─ ProblemAttempt   — your attempt at one problem during that test
       ├─ AttemptEvent      — append-only timeline (PROBLEM_STARTED, ACCEPTED, ...)
       ├─ GeneratedTestCase — test cases you wrote while solving
       └─ SubmissionFailure — a failed submission's categorized reason
```

A `ProblemAttempt`'s phase timers (`reading_seconds`, `pseudocode_seconds`,
`test_design_seconds`, `implementation_seconds`, `debugging_seconds`) are a
cache; the `AttemptEvent` log is the source of truth and can always
reconstruct them. Nothing about a finished attempt is ever overwritten in
place.

**Pattern info stays hidden while you're solving.** A `TestPlanProblem`'s
expected pattern, selection reasoning, and expected failure modes only
render once that specific `ProblemAttempt` is completed or abandoned — not
when the rest of the test finishes, and never before.

## Local development

```bash
python -m venv venv
./venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

python manage.py migrate
python manage.py seed_patterns
python manage.py createsuperuser
python manage.py runserver
```

No environment variables are required locally — `DEBUG` defaults on and the
dev `SECRET_KEY` is fine for local use.

## Test Plan JSON format

Imported at `/test-plans/import/`. A working example ships in the repo at
[`tracker/static/tracker/samples/sample_test_plan.json`](tracker/static/tracker/samples/sample_test_plan.json)
and is downloadable directly from that page in the UI.

Minimal shape:

```json
{
  "schema_version": "1.0",
  "name": "Weekly Assessment 04",
  "description": "Mixed-pattern weekly assessment",
  "target_distribution": { "medium": 8, "hard": 2 },
  "problems": [
    {
      "order": 1,
      "leetcode_number": 1234,
      "title": "Example Problem",
      "url": "https://leetcode.com/problems/example/",
      "difficulty": "Medium",
      "novelty": "Never Seen",
      "evaluation": {
        "primary_pattern": "Sliding Window",
        "secondary_patterns": ["Hash Map"],
        "selection_reason": "Tests variable-size sliding window recognition",
        "expected_failure_modes": [
          "Incorrect shrinking condition",
          "Duplicate handling",
          "Off-by-one boundary"
        ]
      }
    }
  ]
}
```

Field notes:

- `schema_version` must be `"1.0"` — the importer rejects anything else
  outright, so the format can change later without silently corrupting old
  plans.
- `difficulty` is case-insensitive `"Medium"` / `"Hard"`.
- `novelty` is one of `Never Seen`, `Seen But Never Solved`, `Solved Long
  Ago`, `Recently Solved`, `Unknown` (defaults to `Unknown` if omitted or
  unrecognized — a warning, not a hard error).
- `evaluation` is the **hidden answer key** — never shown until that
  problem's attempt is finished. `primary_pattern` / `secondary_patterns`
  are matched or created against the shared `Pattern` catalog by name.
- Problems referenced by `leetcode_number` that don't exist in the catalog
  yet are auto-created; existing ones are reused as-is (their catalog
  `primary_pattern` is *not* overwritten by the plan's `evaluation`).
- Validation is fail-closed on structural problems (duplicate
  `leetcode_number`, invalid `difficulty`, missing `title`/`order`,
  duplicate `order`, wrong `schema_version`) and warn-only on the
  medium/hard distribution drifting from `target_distribution` (or 80/20 if
  that's omitted).

Import is two-stage: validate + import creates a `draft` `TestPlan` you can
review (with the answer key still hidden), then **Mark Ready** and **Start
Assessment**, or **Discard** it entirely if it's wrong.

## CSV exports

Six endpoints under `/export/`: `tests.csv`, `problems.csv`, `attempts.csv`,
`events.csv`, `test-cases.csv`, `failures.csv` — plus a per-test
`/tests/<id>/export.csv`. `attempts.csv` is the one worth handing to an LLM:
denormalized, one row per attempt, every timing/pattern/failure/test-case
metric in one place. `events.csv` is the raw behavioral timeline underneath
it, in case you want to recompute metrics differently later.

## Deployment (Docker / Railway)

```bash
docker build -t leetcode-tracker .
docker run -p 8000:8000 -e SECRET_KEY=... -e DEBUG=False leetcode-tracker
```

Required env vars once `DEBUG=False`: `SECRET_KEY` (Django refuses to boot
with the insecure default otherwise). See `.env.example` for the rest
(`ALLOWED_HOSTS`, `SQLITE_PATH`, `WEB_CONCURRENCY`).

On Railway specifically, two things bit us during setup and are now handled
automatically in `config/settings.py` — worth knowing if you fork this:

1. **Healthcheck host.** Railway's internal healthcheck prober sends
   `Host: healthcheck.railway.app` regardless of your actual domain. Without
   that host in `ALLOWED_HOSTS`, every healthcheck 400s and the deploy never
   goes healthy.
2. **Healthcheck over plain HTTP.** That same prober connects before the
   deployment is live, over plain HTTP, and doesn't follow redirects. A
   blanket `SECURE_SSL_REDIRECT` turns its expected 200 into a 301.
   `tracker/middleware.py` redirects everything to HTTPS *except* that one
   host, so real traffic still gets HTTPS enforcement.

**SQLite persistence:** the container filesystem is ephemeral, so
`db.sqlite3` resets on every redeploy unless `SQLITE_PATH` points at a
mounted Railway volume (e.g. `/data/db.sqlite3`).

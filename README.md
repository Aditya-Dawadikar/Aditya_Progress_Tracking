# Goalpost

A public, shared goal tracker. Anyone can track financial, health, career,
or any other kind of goal — with nested subgoals, drag-and-drop Kanban
boards, and a normalized leaderboard comparing everyone's pace regardless
of how different their goals or timelines are.

## Core domain model

```
GoalBoard        — a shared board (e.g. "2026 Goals")
  └─ Goal         — title, description, owner, category, start/end date,
                     status (Not Started / In Progress / Completed / Abandoned)
       └─ Goal     — a subgoal (same shape, recursive)
```

- A goal's `start_date`/`end_date` are optional — a goal with no deadline
  just has no `pace_score` and doesn't count toward the leaderboard. When
  both are set, a subgoal's dates must fall within its parent's range.
- A goal with subgoals has no progress of its own — its progress is always
  the average of its subgoals' progress, recursively. A leaf goal's
  progress is set directly (0-100%).
- `Category` is a small shared taxonomy (name + color), seeded with
  Financial/Health/Career/Personal — manage it at `/categories/`, where
  anyone can add more from a fixed color palette (`CATEGORY_PALETTE` in
  `tracker/models.py`).
- Goals are reorganized via drag-and-drop between status columns on a
  board (or, for subgoals, on their parent goal's page) — see
  `tracker/static/tracker/js/board.js`, backed by SortableJS and a single
  `/reorder/` endpoint that re-synchronizes an entire board's column state
  per drop. Each status column gets its own accent color.
- A board's Kanban view has filters (keyword, category, owner, start-after,
  end-before) as plain GET params, so filtered views are shareable links.
- **Bulk transfer**: any board can be exported to a JSON file (`Export
  JSON`) and re-imported into any board (`Import JSON`) — the same nested
  shape a board exports is what import expects (see
  `tracker/services/goal_io.py`). Import never overwrites existing goals;
  members and categories named in the file are created if they don't
  already exist.
- **Leaderboard scoring** (`tracker/services/scoring.py`): each goal has a
  `pace_score` (0-100, `Goal.pace_score` in `tracker/models.py`) —
  `50 + 50 * (progress_fraction - time_elapsed_fraction)`, clamped to
  0-100. 50 means exactly on schedule; higher is ahead, lower is behind.
  This normalizes goals of wildly different scope and duration onto the
  same scale. A member's leaderboard score is the average `pace_score`
  across their top-level goals that have a deadline.

## Identity

There's no password-based auth — this is a small, informal, shared tool.
Visiting `/whoami/` lets you pick an existing name or add a new one; it's
stored in your session and attributes anything you create. Everything is
publicly viewable regardless of whether you've picked a name; picking one
is only required to create, edit, delete, or drag-and-drop reorganize
goals and boards (and only that goal's/board's owner can edit or delete
it).

## Local development

```bash
python -m venv venv
./venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

set MONGO_URL=mongodb://localhost:27017                      # Windows cmd
# export MONGO_URL=mongodb://localhost:27017                  # macOS/Linux
# Optional: set MONGO_DB_NAME=goalpost-local
python manage.py migrate
python manage.py seed_demo   # optional: a few members/boards/goals to look at
python manage.py runserver
```

MongoDB is required in every environment. `DEBUG` defaults on and the dev
`SECRET_KEY` is fine for local use.

## Deployment (Docker / Railway)

```bash
docker build -t goalpost .
docker run -p 8000:8000 -e SECRET_KEY=... -e DEBUG=False goalpost
```

Required env vars once `DEBUG=False`: `SECRET_KEY` (Django refuses to boot
with the insecure default otherwise). Railway production uses
`MONGO_PRIVATE_URL`, automatically supplied by its MongoDB service. See
`.env.example` for the rest (`ALLOWED_HOSTS`, `WEB_CONCURRENCY`).

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

**MongoDB persistence:** add a Railway MongoDB service to the same
environment and make its `MONGO_PRIVATE_URL` available to this application.
At startup, `entrypoint.sh` runs the Django migrations against MongoDB.


# Job Board with Applicant Tracking System

A job board with a built-in ATS, built for the Sudan region. The interface is
Arabic and right-to-left; resumes and job descriptions are written in English.

The defining technical decision of this project is that **every comparison
between a resume and a job is semantic**. There is no keyword matching, no
TF-IDF, no synonym dictionary and no curated skills list. Resume text and job
requirements are turned into vectors with `sentence-transformers` and compared
by cosine similarity. A job requiring `React` matches a resume line reading
*"built single-page apps with Next.js and Redux"* because the model places
those two phrases close together — there is no shared word for a keyword
matcher to find.

## Stack

| Concern | Choice |
|---|---|
| Framework | Django 5.2 |
| Database | SQLite (Django default) |
| Templates | Django template language |
| Styling | Tailwind CSS via CDN — no npm, no build step |
| Interactivity | Vanilla JavaScript, only where needed |
| PDF text extraction | `pdfplumber` |
| DOCX text extraction | `python-docx` |
| Matching | `sentence-transformers` (`all-MiniLM-L6-v2`) |
| Email | Django console backend (development) |
| File storage | Local `MEDIA_ROOT` |

No REST API, no React, no Docker, no Redis, no Celery, no websockets. The
project runs with `python manage.py runserver` and nothing else.

## Getting started

```bash
python -m venv .venv && .venv\Scripts\activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open http://127.0.0.1:8000/.

### First run: what to expect

- **`pip install` is slow and large.** `sentence-transformers` depends on
  `torch`, and on Windows the CPU wheel installs to about **509 MB**, with
  `transformers` adding another ~104 MB. Budget roughly 620 MB and several
  minutes on a first install. This is the price of running the model locally
  instead of calling a paid API.
- **The first embedding call downloads the model.** `all-MiniLM-L6-v2` is
  fetched once, on the first call to `get_model()`, and cached on disk (measured
  at 87 MB under `~/.cache/huggingface`). That first call takes around ten seconds; every call
  afterwards is fast because the model is held in a module-level singleton and
  never reloaded per request.
- **Resume upload is synchronous** and takes roughly 3–6 seconds, almost all
  of it embedding. That is acceptable for a project of this size. Production
  would move parsing to a queue.

## Running the tests

```bash
python manage.py test
```

## Regional configuration

| Setting | Value | Why |
|---|---|---|
| `LANGUAGE_CODE` | `ar` | Arabic interface. Also gives Django's own Arabic translations for form errors and the admin site for free. |
| `TIME_ZONE` | `Africa/Khartoum` | UTC+2. |
| Text direction | `dir="rtl"` on `base.html` | Every page is right-to-left. Latin runs such as email addresses are wrapped in a `.ltr` span so their punctuation does not drift. |
| Salary currency | SDG (Sudanese Pound) | Single currency, so no conversion logic anywhere. |
| Embedding model | `all-MiniLM-L6-v2` | Resume and job text is English. **If Arabic resumes are ever accepted this must change** to a multilingual model such as `paraphrase-multilingual-MiniLM-L12-v2` — the current model scores Arabic at close to noise. |

## Moving a candidate through the pipeline

The recruiter is never asked to pick a stage. Each candidate card carries two
buttons -- accept, which names where the candidate is going ("accept to
screening"), and reject -- and the **server** decides the destination from where
they currently are. `next_stage()` holds that sequence in one place, and
`stage_moved()` applies it.

The reasons this is better than a stage picker:

- Choosing "interview" for someone at "applied" is a mechanical step. Leaving it
  to a human invites a pipeline where candidates skip stages by accident.
- The request carries an **intent**, never a stage name. A hand-edited POST
  cannot move someone straight from applied to hired, and there is a test
  asserting exactly that.
- `hired` and `rejected` are terminal, so the accept button disappears rather
  than offering a move that would fail.

The buttons call a small JSON endpoint with `fetch()` and update the board in
place, so a recruiter working through a list of candidates never waits for a
page reload. The same view serves the no-JavaScript path: it returns JSON when
the caller asks for it and redirects otherwise, so the permission and ownership
rules cannot drift apart between the two.

This departs from the original specification, which called for a form POST with
a redirect and no AJAX. The change was requested deliberately after the picker
proved awkward to use.

## Design decisions worth defending

**Embeddings are stored as JSON in a `TextField`.** SQLite has no vector type,
and this project does not need one. Resume counts are in the hundreds, so
loading the vectors into a NumPy array and doing brute-force cosine similarity
is fast enough — a vector database here would be answering a scaling problem
the project does not have.

**Resumes are embedded twice: once whole, once per chunk.** A single
384-dimension vector is an *average* of the whole document, so one mention of
Kubernetes in a five-page CV is washed out by four pages of unrelated text.
Splitting the resume into lines, discarding anything under four words and
embedding each one separately preserves that localised signal. For each
required skill, the score is the **maximum** similarity across all chunks, and
the chunk at the argmax is kept as the evidence string shown to the recruiter.

**`Resume` is a separate model from `Application`.** A candidate uploads once
and reuses the resume across applications. Real ATS software works this way.

**`StageHistory` exists alongside `Application.stage`.** The stage field is the
current position; the history table is the audit trail. Both dashboards render
their timeline from the same rows.

**Authorisation is enforced by view decorators, not by hiding buttons.** A
hidden link is not a control — anyone can type the URL. See
`accounts/decorators.py` and the decorator tests in `accounts/tests.py`.

## Build status

| Phase | Scope | Status |
|---|---|---|
| 1 | Scaffold, custom user model, profiles, registration, login, role redirect, base template, empty dashboards | **done** |
| 2 | Job model, company job CRUD, public listing, filters, detail page, saved jobs | **done** |
| 3 | Matching engine in isolation: model singleton, chunking, cosine similarity, scoring, unit tests | **done** |
| 4 | Resume model, upload, validation, synchronous parsing and embedding | **done** |
| 5 | Apply flow, pipeline view, stage changes, notes, per-skill evidence table | **done** |
| 6 | Notifications: `notify()`, poll endpoint, navbar badge, emails | **done** |
| 7 | Dashboard stats, recommended jobs, `seed_demo_data`, `calibrate_threshold` | **done** |

## Project layout

```
config/          settings, root URL conf
accounts/        custom user model, profiles, registration, decorators, dashboards
jobs/            Job and SavedJob models, company CRUD, public listing and detail
matching/        the embedding and scoring engine -- no models, just functions
applications/    Resume, Application, stage history, notes, apply and pipeline
notifications/   Notification model, notify(), the poll endpoint and list page
templates/       base.html and per-app templates
static/          static assets
media/           uploaded files (resumes, company logos)
sample_data/     sample resumes (PDF and DOCX) used by the tests and the seed
                 command, plus generate.py which rebuilds them
```

All five apps are now in place.

## Notifications are polled, not pushed

The navbar badge asks `/notifications/poll/` for an unread count every
`NOTIFICATION_POLL_SECONDS` (20 by default) and stops asking while the tab is
in the background. There are no websockets and no Django Channels.

That is a deliberate trade, and it is the right one here. Channels would mean
running an ASGI server and a message broker alongside a project that otherwise
starts with `manage.py runserver` and nothing else — real operational weight
bought for notifications that nobody needs within the second. A `setInterval`
costs one cheap indexed query per logged-in user per 20 seconds, and the
whole mechanism fits in about twenty lines of `base.html` that a reader can
check at a glance.

Every notification in the project is created through `notifications.services.notify()`,
so `grep -rn "notify("` gives the complete list of things the system tells
people about. There are four: a new application (to the company), a stage
change and a rejection (to the candidate), and a resume that failed to parse
(to the candidate). Stage changes and rejections also send email, through the
console backend in development.

`notify()` and `send_email()` both swallow their own failures. A notification
is a side effect of something that matters more — a candidate applying, a
recruiter making a decision — and a notification table being unavailable must
never roll back the thing that triggered it. There is a test for exactly that.

## Browsing is not matching

The job listing filters by title, city and employment type with ordinary
database `icontains` lookups, and that does not contradict the semantic-only
rule. That rule governs the comparison between a **resume and a job** — the
scoring that ranks candidates — and that path never compares strings. The
filters are **browsing**: someone typing "Khartoum" expects to see Khartoum,
and running a transformer on every keystroke would be slower and less
predictable without helping. See the note at the top of `jobs/services.py`.

## Measured behaviour of the matching engine

Every number below came from `matching/tests.py` running against its fixture
resumes. They are reproducible with `python manage.py test matching`.

### It separates candidates correctly

Three resumes scored against the same backend job:

| Resume | score | semantic | coverage | skills met |
|---|---|---|---|---|
| Backend engineer (Python, Django, PostgreSQL) | 0.79 | 0.59 | 1.00 | 4 / 4 |
| Frontend developer (Next.js, TypeScript) | 0.17 | 0.34 | 0.00 | 0 / 4 |
| Head chef | 0.07 | 0.13 | 0.00 | 0 / 4 |

### It matches meaning, not words

Compared against the frontend resume, where **not one of these phrases shares a
single word with the line it was matched to**:

| Required skill | best similarity | matched resume line |
|---|---|---|
| component-based user interface frameworks | 0.57 | "Implemented reusable component libraries and design systems in TypeScript" |
| React development | 0.36 | same line |
| COBOL mainframe programming | 0.18 | same line |
| Kubernetes | 0.11 | same line |

A keyword matcher scores every row in that table at zero. The ranking is
produced entirely by where the model places the phrases.

### How a skill is worded changes its score

| Skill phrasing | similarity | line it matched |
|---|---|---|
| building REST APIs with Django and Python | **0.76** | the line describing that work |
| Django | 0.48 | the same work line |
| 3+ years of Python development | 0.40 | **the education line** |
| Python development | 0.39 | the work line |
| Python | 0.39 | **the education line** |

Two lessons, and the second one was a surprise:

1. A descriptive phrase beats a bare keyword by a wide margin — 0.76 against
   0.39 for the same underlying skill.
2. A **duration prefix hurts**. "3+ years of Python development" drifted to the
   *education* line, because "3+ years" carries credential meaning rather than
   work meaning. "Python development" matched the work line correctly.

So the guidance to give companies is not "write longer phrases" but **describe
the work, not the credential** — the model matches an activity to an activity.
The job form's help text and placeholder now say exactly that, because the
wording a company types directly determines how well its candidates score.
### How the threshold was chosen

`SKILL_MATCH_THRESHOLD` is **0.38**, and that number came from measurement.

```bash
python manage.py calibrate_threshold
```

Every sample resume and every sample job in `sample_data/` carries a category
— backend, frontend, data, devops, hospitality, finance. That gives ground
truth: a skill compared against a resume in the *same* field should match, one
from a *different* field should not. The command scores all 450 such pairs and
sweeps every threshold:

| | min | p10 | median | p90 | max |
|---|---|---|---|---|---|
| same field (should match) | 0.178 | 0.243 | 0.550 | 0.793 | 0.871 |
| different field (should not) | -0.003 | 0.094 | 0.196 | 0.341 | 0.608 |

| threshold | recall | precision | F1 |
|---|---|---|---|
| 0.30 | 0.85 | 0.54 | 0.66 |
| 0.35 | 0.78 | 0.65 | 0.71 |
| **0.38** | **0.76** | **0.70** | **0.73** |
| 0.45 | 0.64 | 0.82 | 0.72 |
| 0.60 | 0.42 | 0.97 | 0.59 |

F1 picks the winner because the extremes are both useless: a threshold of 0
has perfect recall and no precision, and a threshold of 1 has the reverse.

The value has moved twice, each time on better evidence. 0.45 was the spec's
default and sat above the bottom of the true-positive range. 0.32 came from
only three fixtures, whose negatives were topically distant (a chef against a
backend job), and admitted too many near-misses once realistic resumes were
added. 0.38 comes from 450 labelled pairs.

**The labels are coarser than the reality, and that matters.** The command
reports its worst false positive as *"building continuous delivery pipelines"*
scoring 0.608 against a backend engineer's *"Kept the continuous integration
pipeline green"*. Category labels call that wrong because the skill belongs to
a devops posting — but a backend engineer who maintains CI genuinely has that
skill, so the model is right and the label is wrong. The same happens in
reverse: the hardest "true positive" is *"applying tax and social insurance
rules"* against a finance CV that never mentions tax. Assuming every skill in
a field matches every resume in that field is an approximation. So the F1
figures above are a **lower bound** on real quality, and 0.38 is the best
choice available from the evidence rather than a proven optimum.

## Demo data

```bash
python manage.py seed_demo_data
```

Creates 3 companies, 15 jobs, 10 job seekers and about 30 applications spread
across all six stages, so the project demonstrates from a fresh clone without
anyone clicking through it first. Every seeded account uses the password
`demo1234`.

Each resume is a real PDF or DOCX from `sample_data/`, pushed through the same
upload path a candidate would use — parsed, chunked and embedded. Nothing is
faked, which is why the command takes a couple of minutes.

Each candidate applies to jobs in their own field *and* one outside it. That is
deliberate: a pipeline where everyone scores well demonstrates nothing, and the
mismatch is what makes the evidence table worth opening. A test asserts that
every seeded candidate's in-field application outscores their out-of-field one.

For a smaller dataset to click through by hand, `python manage.py
seed_manual_test` creates one company, one job and one seeker.


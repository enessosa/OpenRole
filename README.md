# OpenRole

**Get notified when the companies you care about post a role that fits you.**

> **Status:** Planning phase. Nothing here is implemented yet; this README describes the intended design.

---

## The problem

Job portals are noisy, and the companies you actually want to work for often post new roles only on their own career pages. Checking ten career pages by hand every few days is tedious, and good roles for working students fill up quickly.

## The idea

OpenRole is a small self-hosted service that watches the career pages of a fixed list of companies. Every few hours it collects their open roles, detects which ones are new, matches them against each user's filters and sends a short notification with a link to the role.

```
🔔 2 new matching roles

adesso · Working Student Data Engineering · Munich
→ https://…/job/4711

BMW Group · Working Student Software Development · Munich
→ https://…/job/0815
```

It is built for a small number of users (two), each with their own companies, filters and notification channel.

## How it works

1. **Schedule:** Every 3 hours (with a small random offset), a run starts.
2. **Fetch:** For each company, an adapter fetches the open roles and returns them in one common format: title, location, link. Each company is fetched once per run, no matter how many users follow it.
3. **Detect changes:** A role is new if its link hasn't been seen before. Roles that disappear are marked as removed.
4. **Match:** New roles are checked against each user's filters (keywords in the title, location).
5. **Notify:** Matches go into an outbox per user. The notifier sends them and marks them as sent, so nothing is lost and nothing is sent twice.

## Architecture

```
┌──────────────────────────── openrole (Docker) ────────────────────────────┐
│                                                                           │
│   ┌─────────────┐            ┌──────────────────────────────┐             │
│   │ config.yaml │──────────▶ │ Scheduler (every 3h + jitter)│             │
│   │ ─────────── │            └──────────────┬───────────────┘             │
│   │ companies   │                           │ per company                 │
│   │ users       │                           ▼                             │
│   │ filters     │      ┌───────────────── Adapters ──────────────────┐    │
│   └─────────────┘      │  common interface:                          │    │
│                        │  fetch_jobs(company) -> [title, loc, link]  │    │
│                        │                                             │    │
│                        │ ┌──────────┐ ┌────────────┐ ┌─────────────┐ │    │
│                        │ │ Personio │ │ Greenhouse │ │    HTML     │ │    │
│                        │ │  (XML)   │ │   (JSON)   │ │ (selectors) │ │    │
│                        │ └──────────┘ └────────────┘ └─────────────┘ │    │
│                        │  + robots.txt check, timeout, retry         │    │
│                        └──────────────────────┬──────────────────────┘    │
│                                               │ list of roles             │
│                      0 roles? ──┐             ▼                           │
│                                 │   ┌───────────────────┐                 │
│                                 │   │  Change detector  │                 │
│                                 │   │  link seen yet?   │                 │
│                                 │   └─────────┬─────────┘                 │
│                                 │             │ new roles only            │
│                                 │             ▼                           │
│                                 │   ┌───────────────────┐                 │
│                                 │   │      Matcher      │                 │
│                                 │   │ keywords + place  │                 │
│                                 │   │     per user      │                 │
│                                 │   └────┬─────────┬────┘                 │
│                                 │        │ A       │ B                    │
│                                 ▼        ▼         ▼                      │
│  ┌──────────────────────────── SQLite (/data) ───────────────────────┐    │
│  │ companies │ jobs (link, title, location, first/last seen)         │    │
│  │ users     │ outbox (user, job, sent?) │ runs (status per company) │    │
│  └───────────┬───────────────────────────────────────────┬───────────┘    │
│              │ read                                      │ pending        │
│              ▼                                           ▼                │
│  ┌───────────────────────┐                 ┌─────────────────────────┐    │
│  │ Web UI                │                 │ Notifier                │    │
│  │ · roles per user      │                 │ ┌─────────────────────┐ │    │
│  │ · status per company  │                 │ │ Email               │─┼──▶ │
│  │   (last run, ok?)     │                 │ ├─────────────────────┤ │    │
│  └───────────────────────┘                 │ │ Telegram (later)    │─┼──▶ │
│                                            │ ├─────────────────────┤ │    │
│                                            │ │ Webhook (later)     │─┼──▶ │
│                                            │ └─────────────────────┘ │    │
│                                            └─────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

- **Adapters per source type, not per company.** Many companies use the same applicant tracking system (e.g. Personio, Greenhouse). One adapter serves all companies on that system. Only custom career pages need the HTML adapter, configured with CSS selectors in `config.yaml`.
- **No LLM.** Titles, locations and links are extracted with plain, deterministic code. An LLM could be added later as an optional fallback for pages whose selectors break.
- **Outbox instead of a message broker.** Pending notifications are rows in SQLite. That gives reliable, exactly-once-per-user delivery without running Kafka or a similar system.
- **Health check.** If a company suddenly returns zero roles, its selectors probably broke. The run is logged as suspicious and shown in the web UI instead of failing silently.
- **One container.** Scheduler, pipeline, notifier and web UI run in a single process, with the database and configuration in a mounted `/data` volume.
- **Server-rendered web UI.** FastAPI renders HTML pages with Jinja2; HTMX swaps parts of a page without a full reload. There is no separate frontend project, no JSON API to keep in sync and no build step. Pico CSS styles plain HTML without custom CSS.

## Configuration

Companies, users and filters live in one file:

```yaml
companies:
  - id: example
    name: Example GmbH
    source: personio
    company_id: example-gmbh

  - id: custom
    name: Custom AG
    source: html
    url: https://example.com/careers
    selectors:
      job: "li.job-item"
      title: "h3"
      location: ".job-location"
      link: "a@href"

users:
  - name: user-a
    notify: email
    email: user-a@example.com
    companies: [example, custom]
    filters:
      title_any: ["Werkstudent", "Working Student"]
      title_also_any: ["Data", "Software", "Python"]
      location_any: ["München", "Munich"]
```

Secrets (SMTP credentials, later bot tokens) come from environment variables, never from the config file.

## Planned features

### MVP
- [ ] Adapter interface and a first adapter
- [ ] CLI to fetch and list roles for one company
- [ ] SQLite storage with change detection
- [ ] Keyword matcher per user
- [ ] Email notifications via outbox
- [ ] Scheduler (every 3 hours)

### Next
- [ ] More adapters (depending on the companies' systems)
- [ ] Health check per company
- [ ] Web UI: roles per user, status per company
- [ ] Docker image and `compose.yaml`

### Later
- [ ] Telegram notifications
- [ ] Webhook notifications (e.g. to trigger n8n workflows)
- [ ] Optional LLM fallback for broken selectors or profile-based matching

## Tech stack

| Area | Technology |
|---|---|
| Language | Python 3.14, uv |
| HTTP | httpx |
| HTML parsing | selectolax or BeautifulSoup |
| Models and config | Pydantic, pydantic-settings, YAML |
| Database | SQLite, SQLAlchemy, Alembic |
| Scheduling | APScheduler |
| Web server | FastAPI |
| Web UI | Jinja2 templates, HTMX, Pico CSS |
| CLI | Typer, rich |
| Tests and quality | pytest, respx, Ruff |
| Deployment | Docker image, self-hosted |

## Project layout

| Folder | Content |
|---|---|
| `core/` | The service: scheduler, adapters, pipeline, database, notifiers, web UI (templates) |
| `docs/` | Design documents |

## Fair use

OpenRole only reads public career pages and is meant for personal use.

- Prefer official job feeds and APIs of applicant tracking systems over HTML pages.
- Respect `robots.txt` and each site's terms of use before adding a company.
- Fetch rarely (every few hours) and identify honestly with a descriptive user agent.
- Never bypass logins, captchas or blocks. If a site blocks access, it is removed.
- Don't republish collected postings. This repository contains code, not data.
- Don't store personal data such as recruiter names or contact details.
- Job portals such as LinkedIn, Indeed or StepStone are out of scope.

## License

[MIT](LICENSE)

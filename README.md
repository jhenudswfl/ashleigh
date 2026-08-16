# Ashleigh — Setup Guide

Ashleigh is the Utter Declutter pace agent.

One script, run on a free scheduled automation (GitHub Actions), that every Monday at 7 AM pulls the last 14 days from Meta and GoHighLevel, computes the game-plan KPIs, runs the decision matrix, and texts + emails you a digest telling you whether to hold, increase, or reduce spend, how much reinvestment is owed to the ad budget, and how close you are to the price-raise gate.

## What it tracks

CPL (reported only — never used for decisions), booking rate, close rate (per lead and per consult), average project value, CAC, cost per booked crew day vs. the $100 model, booked days sold vs. crew days delivered, backlog growth pace, business-margin ROI per ad dollar, and the reinvestment amount owed under the $100-per-booked-day rule.

## The decision rules it enforces

These are hard-coded from the agreed plan. If the plan changes, change the constants at the top of `pace_agent.py`.

| Rule | Value |
|---|---|
| Cost per booked day model | $100 |
| Breakeven / target / ceiling daily spend | $60 / $100 / $150 |
| Reinvestment per booked day | $100, pre-funded by closed revenue |
| Price-raise gate | 30 consecutive days booked, zero idle (manual calendar check — the agent reminds you) |
| Price step | +10–15%, new quotes only |
| Close-rate floor after a price step | 8% of leads |
| 60–90 days booked | second-crew signal, not a price signal |
| CPL | banned as a decision metric |

## Setup — about 30 minutes

### 1. Get three credentials

**Meta access token.** business.facebook.com → Business Settings → Users → System Users → create one (name it `pace-agent`, Admin not required — Advertiser role on the ad account is enough) → Generate Token → select the ads_read permission → assign the Utter Declutter Ads account (3179454915545190). Copy the token.

**GHL Private Integration token.** GHL → Settings → Private Integrations → Create. Scopes needed: `opportunities.readonly`, `calendars.readonly`, `calendars/events.readonly` (upcoming-consults count reads real calendar bookings, not opportunity stage), `conversations/message.write` (only if you want the SMS digest). Copy the token, your Location ID (Settings → Business Profile), and the Pipeline ID (Settings → Pipelines → click your pipeline, the ID is in the URL).

**Your GHL contact ID** (for the SMS digest): open your own contact record in GHL — the ID is in the URL. Optional; skip if email-only.

### 2. Create the repo

1. github.com → New repository → `ud-pace-agent`, private.
2. Upload `pace_agent.py` to the root.
3. Create the folder path `.github/workflows/` and upload `pace-agent.yml` there.

### 3. Add secrets

Repo → Settings → Secrets and variables → Actions → New repository secret. Add: `META_ACCESS_TOKEN`, `GHL_API_TOKEN`, `GHL_LOCATION_ID`, `GHL_PIPELINE_ID`, `DIGEST_SMS_CONTACT_ID` (optional), and the four SMTP values if you want email (any Gmail app password works: `SMTP_HOST=smtp.gmail.com`, `SMTP_USER=you@gmail.com`, `SMTP_PASS=<app password>`, `DIGEST_EMAIL_TO=you@...`).

### 4. Match your stage names

The workflow file assumes your pipeline stages are named `Consult Booked` and `Won`. If yours differ, edit those two lines in `pace-agent.yml` to the exact names.

### 5. Test it

Repo → Actions tab → Ashleigh → Run workflow. The digest prints in the run log even if SMS/email aren't configured yet. Verify the numbers against Ads Manager and your pipeline before trusting it.

## Reading the digest

- **ACTIONS** are the calls: hold / step up / reduce, plus the reinvestment amount owed this window.
- **FLAGS** are things needing your judgment — the close-rate floor after a price step, backlog shrinking below breakeven pace, and the standing reminder to check the 30-day calendar gate (the agent can't see your crew calendar, so that check stays manual until crew scheduling lives in a system it can read).

## Known limits (v1)

- Backlog is *revenue-implied* (won value ÷ $1,000/day), not calendar-actual. Good enough to steer; the 30-day gate check is yours.
- Attribution: it counts all pipeline opportunities in the window against Meta spend. Once cold-call and email volume grows, add a source filter (tag or custom field in GHL) so paid CAC isn't polluted by other channels — one-line change in `fetch_opportunities`.
- Meta tokens from a System User don't expire; the GHL Private Integration token doesn't either. If a run fails, the Actions tab shows the error.

## Live dashboard

Every run also appends the snapshot to `history.json` and regenerates `docs/dashboard.html` — a brand-styled page with this week's decision call, KPI cards with week-over-week deltas, the price-gate progress bar, four trend charts (funnel, cost-per-booked-day vs. the $100 model, spend vs. margin, booking pace vs. capacity), and a full weekly history table.

To get the bookmarkable URL: upload `dashboard.py` to the repo root alongside `pace_agent.py`, then repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder `/docs` → Save. Your dashboard lives at `https://<your-username>.github.io/ud-pace-agent/dashboard.html` and refreshes automatically after every scheduled run. Note: Pages on a private repo requires a paid GitHub plan — the free workaround is to make the repo public (the dashboard contains only aggregate metrics, no client data, no tokens; secrets live in Actions and are never committed) or just open `docs/dashboard.html` from the repo directly.

## Changing cadence

Weekly Monday is the default. For a mid-week pulse too, add a second cron line in the workflow: `- cron: "0 11 * * 4"` (Thursday).

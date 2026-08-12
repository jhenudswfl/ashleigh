#!/usr/bin/env python3
"""
Ashleigh — Utter Declutter growth-loop monitor.

Pulls ad spend + leads from Meta, pipeline data from GoHighLevel,
computes the game-plan KPIs, applies the decision matrix, and sends
a digest via SMS (through GHL) and/or email.

Decision rules encoded (do not edit casually — these are the agreed plan):
  - $100 of ad spend ≈ 1 booked crew day (at $20 CPL, 10% close, 2-day jobs)
  - Breakeven spend: $60/day. Target: $100/day. Ceiling: $150/day
    (ceiling = Jhen's solo sales capacity; raise only when John takes sales volume)
  - Reinvestment rule: $100 per booked day, pre-funded by closed revenue
  - Price-raise trigger: 30 consecutive calendar days booked, zero idle days
    -> raise day rate 10-15% on NEW quotes only, watch close rate over next
       10-15 quotes; hold if close rate stays >= 8%
  - 60-90 days booked out = capacity signal (second crew), NOT price signal
  - CPL is REPORTED but is NEVER a decision metric. Decisions run on booked
    consults, close rate, average project value, CAC, and backlog.
"""

import os
import sys
import json
import smtplib
import datetime as dt
from email.mime.text import MIMEText
from urllib import request, parse

# ----------------------------------------------------------------------------
# CONFIG — everything comes from environment variables (GitHub Actions secrets)
# ----------------------------------------------------------------------------
META_TOKEN        = os.environ["META_ACCESS_TOKEN"]
META_ACCOUNT_ID   = os.environ.get("META_ACCOUNT_ID", "3179454915545190")  # Utter Declutter Ads — NEVER the secondary account
GHL_TOKEN         = os.environ["GHL_API_TOKEN"]           # Private Integration token
GHL_LOCATION_ID   = os.environ["GHL_LOCATION_ID"]
GHL_PIPELINE_ID   = os.environ["GHL_PIPELINE_ID"]

# Stage names in your GHL pipeline (edit to match exactly — case-insensitive)
STAGE_CONSULT_BOOKED = os.environ.get("STAGE_CONSULT_BOOKED", "Consult Booked")
STAGE_WON            = os.environ.get("STAGE_WON", "Won")

# Business constants (the agreed model)
DAY_RATE          = float(os.environ.get("DAY_RATE", "1000"))    # labor revenue per crew day
BUSINESS_SHARE    = float(os.environ.get("BUSINESS_SHARE", "300"))  # business cut per delivered day
CREW_DAYS_PER_MO  = float(os.environ.get("CREW_DAYS_PER_MO", "18"))
COST_PER_BOOKED_DAY = 100.0
SPEND_BREAKEVEN   = 60.0
SPEND_TARGET      = 100.0
SPEND_CEILING     = 150.0
CLOSE_RATE_FLOOR  = 0.08
PRICE_GATE_DAYS   = 30

# Reporting window
LOOKBACK_DAYS     = int(os.environ.get("LOOKBACK_DAYS", "14"))
# If set, the window never starts earlier than this date — so right after an
# ad relaunch the report doesn't pull in stale pre-relaunch data. The window
# grows day by day and naturally caps at the normal LOOKBACK_DAYS rolling
# window once CAMPAIGN_START_DATE is more than LOOKBACK_DAYS in the past.
CAMPAIGN_START_DATE = os.environ.get("CAMPAIGN_START_DATE", "")

# Digest delivery (either or both)
DIGEST_SMS_CONTACT_ID = os.environ.get("DIGEST_SMS_CONTACT_ID", "")  # GHL contact ID for Jhen
SMTP_HOST  = os.environ.get("SMTP_HOST", "")
SMTP_PORT  = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER  = os.environ.get("SMTP_USER", "")
SMTP_PASS  = os.environ.get("SMTP_PASS", "")
DIGEST_EMAIL_TO = os.environ.get("DIGEST_EMAIL_TO", "")

GHL_BASE = "https://services.leadconnectorhq.com"


def http_json(url, headers=None, data=None, method="GET"):
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "ashleigh-pace-agent/1.0")
    req = request.Request(url, headers=headers, method=method)
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ----------------------------------------------------------------------------
# 1. META — spend + leads for the window
# ----------------------------------------------------------------------------
def fetch_meta(since, until):
    fields = "spend,actions"
    tr = json.dumps({"since": since, "until": until})
    url = (f"https://graph.facebook.com/v21.0/act_{META_ACCOUNT_ID}/insights?"
           + parse.urlencode({"fields": fields, "time_range": tr,
                              "access_token": META_TOKEN}))
    data = http_json(url)
    spend, leads = 0.0, 0
    for row in data.get("data", []):
        spend += float(row.get("spend", 0))
        # Meta reports the same lead conversions under multiple action_types
        # (e.g. "lead" and "onsite_conversion.lead_grouped" both count the
        # identical events) — take the best single count per row, don't sum them.
        row_leads = 0
        for a in row.get("actions", []) or []:
            if a.get("action_type") in ("lead", "onsite_conversion.lead_grouped",
                                        "offsite_conversion.fb_pixel_lead"):
                row_leads = max(row_leads, int(float(a.get("value", 0))))
        leads += row_leads
    return spend, leads


# ----------------------------------------------------------------------------
# 2. GHL — opportunities by stage for the window
# ----------------------------------------------------------------------------
def ghl_headers():
    return {"Authorization": f"Bearer {GHL_TOKEN}",
            "Version": "2021-07-28", "Accept": "application/json"}


def fetch_pipeline_stages():
    url = f"{GHL_BASE}/opportunities/pipelines?locationId={GHL_LOCATION_ID}"
    data = http_json(url, ghl_headers())
    for p in data.get("pipelines", []):
        if p.get("id") == GHL_PIPELINE_ID:
            return {s["name"].strip().lower(): s["id"] for s in p.get("stages", [])}
    raise RuntimeError("Pipeline not found — check GHL_PIPELINE_ID")


def _search_opportunities_pages(extra_params):
    """Cursor-paginate /opportunities/search (this endpoint ignores `page` past
    page 1 — real pagination is via the startAfter/startAfterId cursor the API
    returns in `meta`). Yields each page's opportunity list, newest-created first."""
    cursor = {}
    while True:
        params = {"location_id": GHL_LOCATION_ID, "pipeline_id": GHL_PIPELINE_ID,
                   "limit": 100, **extra_params, **cursor}
        data = http_json(f"{GHL_BASE}/opportunities/search?{parse.urlencode(params)}",
                          ghl_headers())
        batch = data.get("opportunities", [])
        if not batch:
            return
        yield batch
        meta = data.get("meta", {})
        start_after, start_after_id = meta.get("startAfter"), meta.get("startAfterId")
        if len(batch) < 100 or start_after is None:
            return
        cursor = {"startAfter": start_after, "startAfterId": start_after_id}


def fetch_open_pipeline(stages):
    """All OPEN opportunities regardless of created date:
    upcoming consults on the books + total open pipeline value."""
    consult_id = stages.get(STAGE_CONSULT_BOOKED.strip().lower())
    upcoming, open_value = 0, 0.0
    for batch in _search_opportunities_pages({"status": "open"}):
        for o in batch:
            open_value += float(o.get("monetaryValue") or 0)
            if o.get("pipelineStageId") == consult_id:
                upcoming += 1
    return upcoming, open_value


def fetch_opportunities(since_iso):
    """All opportunities created on/after since_iso. The search endpoint has no
    server-side date filter (a `date` param 400s), so this pages newest-first
    and stops as soon as it crosses the window boundary."""
    opps = []
    for batch in _search_opportunities_pages({}):
        stop = False
        for o in batch:
            if o.get("createdAt", "") < since_iso:
                stop = True
                break
            opps.append(o)
        if stop:
            break
    return opps


# ----------------------------------------------------------------------------
# 3. KPI computation
# ----------------------------------------------------------------------------
def compute(spend, meta_leads, opps, stages, days_in_window):
    consult_stage_id = stages.get(STAGE_CONSULT_BOOKED.strip().lower())
    won_stage_id     = stages.get(STAGE_WON.strip().lower())

    leads = max(meta_leads, len(opps))  # GHL count wins if forms bypass Meta lead event
    consults = sum(1 for o in opps
                   if o.get("pipelineStageId") == consult_stage_id
                   or o.get("status") == "won")  # won implies it consulted
    wins = [o for o in opps if o.get("status") == "won"
            or o.get("pipelineStageId") == won_stage_id]
    won_value = sum(float(o.get("monetaryValue") or 0) for o in wins)

    n_wins = len(wins)
    avg_value   = won_value / n_wins if n_wins else 0
    booking_rate = consults / leads if leads else 0
    close_rate_lead = n_wins / leads if leads else 0
    close_rate_consult = n_wins / consults if consults else 0
    cpl = spend / leads if leads else 0
    cac = spend / n_wins if n_wins else 0
    booked_days = won_value / DAY_RATE  # revenue-implied crew days sold
    cost_per_booked_day = spend / booked_days if booked_days else 0
    roi = (won_value * (BUSINESS_SHARE / DAY_RATE * 2)) if False else None  # placeholder
    biz_margin = booked_days * BUSINESS_SHARE
    ltv_cac = (avg_value * (BUSINESS_SHARE + BUSINESS_SHARE) / DAY_RATE) / cac if cac else 0
    # simpler, honest ROI: business margin generated per ad dollar
    romi = biz_margin / spend if spend else 0
    reinvest_owed = booked_days * COST_PER_BOOKED_DAY

    daily_spend = spend / days_in_window
    booked_days_per_mo = booked_days / days_in_window * 30
    net_backlog_growth = booked_days_per_mo - CREW_DAYS_PER_MO

    return dict(spend=spend, leads=leads, consults=consults, wins=n_wins,
                won_value=won_value, avg_value=avg_value, cpl=cpl, cac=cac,
                booking_rate=booking_rate, close_rate_lead=close_rate_lead,
                close_rate_consult=close_rate_consult, booked_days=booked_days,
                cost_per_booked_day=cost_per_booked_day, romi=romi,
                biz_margin=biz_margin, reinvest_owed=reinvest_owed,
                daily_spend=daily_spend, booked_days_per_mo=booked_days_per_mo,
                net_backlog_growth=net_backlog_growth)


# ----------------------------------------------------------------------------
# 4. Decision matrix — the game plan, as code
# ----------------------------------------------------------------------------
def decide(k):
    actions, flags = [], []

    # --- Spend decision (never on CPL) ---
    if k["wins"] == 0 and k["spend"] > 0:
        actions.append("HOLD SPEND — no closes this window yet. Do not judge "
                       "the campaign before 14 full days at the new budget. "
                       "Check speed-to-lead and consult show rate first.")
    elif k["cost_per_booked_day"] > 0 and k["cost_per_booked_day"] <= 120:
        if k["daily_spend"] < SPEND_TARGET:
            actions.append(f"INCREASE SPEND — cost/booked-day is "
                           f"${k['cost_per_booked_day']:.0f} (model: $100). "
                           f"Step daily budget up toward ${SPEND_TARGET:.0f}.")
        elif k["daily_spend"] < SPEND_CEILING and k["close_rate_lead"] >= 0.08:
            actions.append(f"ELIGIBLE TO STEP UP — economics hold at "
                           f"${k['daily_spend']:.0f}/day. Next step: "
                           f"${SPEND_CEILING:.0f}/day, ONLY if lead follow-up "
                           "speed is holding (leads contacted <5 min).")
        else:
            actions.append("HOLD SPEND — at ceiling or close rate soft. "
                           "Ceiling lifts when John takes sales volume.")
    elif k["cost_per_booked_day"] > 200:
        actions.append(f"REDUCE/HOLD — cost/booked-day ${k['cost_per_booked_day']:.0f} "
                       "is 2x model. Diagnose in order: (1) consult show rate, "
                       "(2) close rate vs 8% floor, (3) creative fatigue. "
                       "Do NOT kill creative on CPL.")
    else:
        actions.append("HOLD SPEND — economics within tolerance of the model.")

    # --- Close rate floor ---
    if k["leads"] >= 20 and k["close_rate_lead"] < CLOSE_RATE_FLOOR:
        flags.append(f"⚠ Close rate {k['close_rate_lead']:.0%} is below the 8% "
                     "floor on meaningful volume. If this follows a price step, "
                     "hold price. If not, it's a sales-process issue, not pricing.")

    # --- Reinvestment ledger ---
    actions.append(f"REINVEST: ${k['reinvest_owed']:.0f} owed to ad budget this "
                   f"window (${COST_PER_BOOKED_DAY:.0f} × {k['booked_days']:.1f} "
                   f"booked days). Business margin retained after reinvest: "
                   f"${k['biz_margin'] - k['reinvest_owed']:.0f}.")

    # --- Backlog / price gate ---
    if k["net_backlog_growth"] > 0:
        months_to_full = PRICE_GATE_DAYS / k["net_backlog_growth"] if k["net_backlog_growth"] else 99
        actions.append(f"BACKLOG: growing ~{k['net_backlog_growth']:.0f} days/mo. "
                       f"On pace to hit the 30-day zero-gap price gate in "
                       f"~{months_to_full:.1f} months at this rate.")
    else:
        flags.append("⚠ Backlog SHRINKING — booking slower than delivery. "
                     "You are below breakeven pace ($60/day equivalent).")

    flags.append("PRICE GATE (manual check): if the calendar shows 30 consecutive "
                 "days booked with ZERO idle days → raise day rate 10-15% on new "
                 "quotes only. 60-90 days booked = second-crew signal, not price.")

    return actions, flags


# ----------------------------------------------------------------------------
# 5. Digest
# ----------------------------------------------------------------------------
def build_digest(k, actions, flags, since, until):
    L = [f"ASHLEIGH — WEEKLY PACE REPORT — {since} → {until}", "-" * 40,
         f"Spend: ${k['spend']:.0f} (${k['daily_spend']:.0f}/day)",
         f"Leads: {k['leads']}  |  CPL: ${k['cpl']:.0f} (reported, not a decision metric)",
         f"Consults booked: {k['consults']}  ({k['booking_rate']:.0%} of leads)",
         f"Wins: {k['wins']}  |  Close: {k['close_rate_lead']:.0%} of leads / {k['close_rate_consult']:.0%} of consults",
         f"Won value: ${k['won_value']:,.0f}  |  Avg project: ${k['avg_value']:,.0f}",
         f"CAC: ${k['cac']:.0f}  |  Cost per booked day: ${k['cost_per_booked_day']:.0f} (model: $100)",
         f"Booked days sold: {k['booked_days']:.1f}  (~{k['booked_days_per_mo']:.0f}/mo vs {CREW_DAYS_PER_MO:.0f} delivered)",
         f"Ad ROI: ${k['romi']:.2f} business margin per $1 spent",
         "", "ACTIONS:"]
    L += [f"• {a}" for a in actions]
    if flags:
        L += ["", "FLAGS:"] + [f"• {f}" for f in flags]
    return "\n".join(L)


def send_sms_via_ghl(text):
    if not DIGEST_SMS_CONTACT_ID:
        return
    # SMS has length limits — send the top summary only
    short = text.split("ACTIONS:")[0] + "ACTIONS:\n" + \
            "\n".join(l for l in text.split("ACTIONS:")[1].splitlines() if l)[:600]
    http_json(f"{GHL_BASE}/conversations/messages", ghl_headers(),
              data={"type": "SMS", "contactId": DIGEST_SMS_CONTACT_ID,
                    "message": short}, method="POST")


def send_email(text, since, until):
    if not (SMTP_HOST and DIGEST_EMAIL_TO):
        return
    msg = MIMEText(text)
    msg["Subject"] = f"Ashleigh — Pace Report {since} to {until}"
    msg["From"] = SMTP_USER
    msg["To"] = DIGEST_EMAIL_TO
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)


# ----------------------------------------------------------------------------
def main():
    until = dt.date.today()
    since = until - dt.timedelta(days=LOOKBACK_DAYS)
    if CAMPAIGN_START_DATE:
        since = max(since, dt.date.fromisoformat(CAMPAIGN_START_DATE))
    s, u = since.isoformat(), until.isoformat()
    days_in_window = max((until - since).days, 1)

    spend, meta_leads = fetch_meta(s, u)
    stages = fetch_pipeline_stages()
    opps = fetch_opportunities(s + "T00:00:00Z")
    k = compute(spend, meta_leads, opps, stages, days_in_window)
    k["upcoming_consults"], k["pipeline_value"] = fetch_open_pipeline(stages)
    actions, flags = decide(k)
    digest = build_digest(k, actions, flags, s, u)

    print(digest)
    send_sms_via_ghl(digest)
    send_email(digest, s, u)

    # Update the live dashboard (history.json + docs/dashboard.html)
    try:
        import dashboard
        history = dashboard.append_snapshot(k, actions, flags)
        dashboard.render_dashboard(history)
        print(f"\nDashboard regenerated with {len(history)} snapshots.")
    except Exception as e:
        print(f"Dashboard generation failed (digest still sent): {e}")


if __name__ == "__main__":
    sys.exit(main())

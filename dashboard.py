"""
Dashboard generator for Ashleigh (UD pace agent).
Each run appends the current KPI snapshot to history.json and regenerates
docs/dashboard.html - a simple, glanceable page served by GitHub Pages.
"""

import json
import os
import datetime as dt

HISTORY_PATH = os.environ.get("HISTORY_PATH", "history.json")
DASHBOARD_PATH = os.environ.get("DASHBOARD_PATH", "docs/dashboard.html")


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return []


def append_snapshot(k, actions, flags):
    history = load_history()
    snap = dict(k)
    snap["date"] = dt.date.today().isoformat()
    snap["actions"] = actions
    snap["flags"] = flags
    history = [h for h in history if h.get("date") != snap["date"]]
    history.append(snap)
    history = history[-52:]
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=1)
    return history


def render_dashboard(history):
    os.makedirs(os.path.dirname(DASHBOARD_PATH) or ".", exist_ok=True)
    html = TEMPLATE.replace("__HISTORY__", json.dumps(history))
    html = html.replace("__GENERATED__", dt.datetime.now().strftime("%b %d, %Y %I:%M %p"))
    with open(DASHBOARD_PATH, "w") as f:
        f.write(html)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ashleigh — UD Pace</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1"></script>
<style>
:root{--bg:#F5F5F7;--card:#FFF;--ink:#1D1D1F;--muted:#86868B;--accent:#0071E3;--pos:#34C759;--neg:#FF3B30;--radius:14px}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:20px;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto}
.top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px}
.top h1{font-size:17px;font-weight:600}
.top .date{font-size:12px;color:var(--muted)}
.hero{background:var(--card);border-radius:var(--radius);padding:28px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.money{display:flex;align-items:center;justify-content:center;gap:20px;flex-wrap:wrap;text-align:center}
.money .num{font-size:44px;font-weight:700;letter-spacing:-1px}
.money .lbl{font-size:12px;color:var(--muted);font-weight:500;margin-top:2px}
.money .arrow{font-size:26px;color:var(--muted)}
.roi{text-align:center;margin-top:16px;font-size:20px;font-weight:600}
.roi span{color:var(--pos)}
.roi.bad span{color:var(--neg)}
.call{background:var(--ink);color:#fff;border-radius:var(--radius);padding:18px 24px;margin-bottom:12px;font-size:16px;font-weight:600;line-height:1.45}
.call .tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:1px;padding:3px 10px;border-radius:20px;margin-right:10px;vertical-align:2px}
.tag.up{background:var(--pos)} .tag.hold{background:var(--accent)} .tag.down{background:var(--neg)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:12px}
.tile{background:var(--card);border-radius:var(--radius);padding:18px 20px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.tile .v{font-size:26px;font-weight:700;letter-spacing:-.5px}
.tile .l{font-size:12px;color:var(--muted);font-weight:500;margin-top:2px}
.tile .d{font-size:12px;font-weight:600;margin-top:4px}
.d.pos{color:var(--pos)}.d.neg{color:var(--neg)}
.recs{background:var(--card);border-radius:var(--radius);padding:18px 24px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.recs h3{font-size:13px;font-weight:600;color:var(--muted);margin-bottom:8px}
.recs li{margin:6px 0 6px 18px;font-size:14px;line-height:1.5}
.recs li.warn{color:var(--neg)}
.chartcard{background:var(--card);border-radius:var(--radius);padding:20px 24px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.chartcard h3{font-size:13px;font-weight:600;color:var(--muted);margin-bottom:12px}
.chartcard canvas{max-height:220px}
details{background:var(--card);border-radius:var(--radius);padding:16px 24px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
summary{font-size:14px;font-weight:600;cursor:pointer;color:var(--accent)}
details ul{margin:12px 0 4px 18px;font-size:13px;line-height:1.7}
details .warn{color:var(--neg)}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:12px}
th{text-align:right;padding:7px 8px;border-bottom:1px solid #E5E5EA;color:var(--muted);font-weight:600}
td{text-align:right;padding:7px 8px;border-bottom:1px solid #F2F2F7}
th:first-child,td:first-child{text-align:left}
tr:last-child td{border-bottom:none}
footer{text-align:center;font-size:11px;color:var(--muted);margin-top:16px}
@media(max-width:600px){.money .num{font-size:32px}.tiles{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><h1>Ashleigh <span style="color:var(--muted);font-weight:400">· Utter Declutter pace</span></h1><div class="date">Updated __GENERATED__ · last 14 days</div></div>

  <div class="hero">
    <div class="money">
      <div><div class="num" id="mIn">$0</div><div class="lbl">MARKETING IN</div></div>
      <div class="arrow">&#8594;</div>
      <div><div class="num" id="mOut">$0</div><div class="lbl">REVENUE WON</div></div>
    </div>
    <div class="roi" id="roi"></div>
  </div>

  <div class="call" id="call"></div>

  <div class="tiles" id="tiles"></div>

  <div class="recs">
    <h3>Ashleigh's recommendations</h3>
    <ul id="recs"></ul>
  </div>

  <div class="chartcard"><h3>Money in vs. money out, by week</h3><canvas id="moneyChart"></canvas></div>

  <details>
    <summary>Details &amp; full history</summary>
    <ul id="actions"></ul>
    <ul id="flags"></ul>
    <table id="histTable"><thead><tr>
      <th>Week</th><th>Spend</th><th>Leads</th><th>Consults</th><th>Wins</th>
      <th>Revenue</th><th>Close %</th><th>CAC</th><th>$/Booked Day</th>
    </tr></thead><tbody></tbody></table>
  </details>

  <footer>Decisions run on booked consults, close rate &amp; project value — never CPL.</footer>
</div>

<script>
const H = __HISTORY__;
const cur = H[H.length-1] || {};
const prev = H[H.length-2] || null;
const fmtD = v => '$' + Math.round(v||0).toLocaleString();

document.getElementById('mIn').textContent  = fmtD(cur.spend);
document.getElementById('mOut').textContent = fmtD(cur.won_value);
const x = cur.spend ? (cur.won_value||0)/cur.spend : 0;
const roiEl = document.getElementById('roi');
roiEl.innerHTML = 'Every $1 in &#8594; <span>$' + x.toFixed(0) + '</span> back in booked revenue';
if (x < 5) roiEl.classList.add('bad');

const first = (cur.actions||[''])[0];
let tag='hold', word='HOLD';
if(/INCREASE|ELIGIBLE TO STEP/i.test(first)){tag='up';word='STEP UP'}
else if(/REDUCE/i.test(first)){tag='down';word='PULL BACK'}
document.getElementById('call').innerHTML =
  '<span class="tag ' + tag + '">' + word + '</span>' + first.replace(/^[A-Z \/]+\u2014\s*/,'');

function dlt(now,before,goodUp){
  if(before==null||!before) return '';
  const dd=now-before; if(!dd) return '';
  const good=(dd>0)===(goodUp!==false);
  return '<div class="d ' + (good?'pos':'neg') + '">' + (dd>0?'\u25B2':'\u25BC') + ' vs last week</div>';
}
// Days booked out: revenue-implied crew-days sold since the report window
// opened (cur.booked_days), none yet confirmed delivered. NOT a sum across
// snapshots — the window grows from campaign start, so each day's booked_days
// already includes every prior win; summing them double/triple-counts the
// same jobs. Once deliveries start, this will overstate backlog until crew
// scheduling is trackable — see README "Known limits."
var backlog = cur.booked_days || 0;
const tiles=[
  {v:fmtD(cur.cac), l:'Cost to win a job (CAC)', dd:dlt(cur.cac,prev&&prev.cac,false)},
  {v:cur.wins||0, l:'Jobs closed', dd:dlt(cur.wins,prev&&prev.wins)},
  {v:fmtD(cur.avg_value), l:'Avg job value', dd:dlt(cur.avg_value,prev&&prev.avg_value)},
  {v:Math.round(backlog)+' days', l:'Booked out (est.)', dd:''},
  {v:fmtD(cur.daily_spend)+'/day', l:'Current ad spend', dd:''},
  {v:((cur.close_rate_resolved||0)*100).toFixed(0)+'%', l:'Close rate ('+(cur.n_resolved||0)+' resolved, '+(cur.pending_consults||0)+' pending)', dd:dlt(cur.close_rate_resolved,prev&&prev.close_rate_resolved)},
  {v:((cur.booking_rate||0)*100).toFixed(0)+'%', l:'Booking rate', dd:dlt(cur.booking_rate,prev&&prev.booking_rate)},
  {v:fmtD(cur.cpl), l:'CPL (context only)', dd:''},
  {v:cur.upcoming_consults||0, l:'Upcoming consults', dd:dlt(cur.upcoming_consults,prev&&prev.upcoming_consults)},
  {v:cur.n_resolved||0, l:'Appointments sat', dd:dlt(cur.n_resolved,prev&&prev.n_resolved)},
];
document.getElementById('tiles').innerHTML = tiles.map(function(t){
  return '<div class="tile"><div class="v">'+t.v+'</div><div class="l">'+t.l+'</div>'+t.dd+'</div>';}).join('');

new Chart(moneyChart,{type:'bar',data:{labels:H.map(h=>h.date.slice(5)),datasets:[
  {label:'In (ad spend)',data:H.map(h=>h.spend),backgroundColor:'#C7C7CC',borderRadius:6},
  {label:'Out (revenue won)',data:H.map(h=>h.won_value),backgroundColor:'#0071E3',borderRadius:6}]},
  options:{responsive:true,plugins:{legend:{labels:{font:{size:11},boxWidth:12}}},
  scales:{x:{grid:{display:false},ticks:{font:{size:10},color:'#86868B'}},
          y:{grid:{color:'#F2F2F7'},ticks:{font:{size:10},color:'#86868B',callback:function(v){return '$'+(v>=1000?(v/1000)+'k':v)}}}}}});

(cur.actions||[]).forEach(function(a){var li=document.createElement('li');li.textContent=a;document.getElementById('recs').appendChild(li)});
(cur.flags||[]).forEach(function(f){
  var li=document.createElement('li');li.textContent=f;
  if(f.indexOf('PRICE GATE')===0){document.getElementById('flags').appendChild(li);}
  else{li.className='warn';document.getElementById('recs').appendChild(li);}
});
document.querySelector('#histTable tbody').innerHTML=[].concat(H).reverse().map(function(h){
  return '<tr><td>'+h.date+'</td><td>'+fmtD(h.spend)+'</td><td>'+h.leads+'</td><td>'+h.consults+'</td><td>'+h.wins+
  '</td><td>'+fmtD(h.won_value)+'</td><td>'+((h.close_rate_resolved||0)*100).toFixed(0)+'%</td><td>'+fmtD(h.cac)+
  '</td><td>'+fmtD(h.cost_per_booked_day)+'</td></tr>';}).join('');
</script>
</body>
</html>"""

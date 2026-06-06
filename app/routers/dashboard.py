"""Dashboard visual de pedidos (tablero tipo kanban) y panel de atención humana.

Se sirve como una sola página HTML autocontenida que consume la API /admin/*.
En producción protégela con autenticación y sirve solo el negocio del usuario.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_PAGE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel de pedidos</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#f6f2ea; --card:#fffdf8; --ink:#211d18; --muted:#8a8174;
    --border:#e6dfd1; --green:#1f7a4d; --amber:#b9770e; --slate:#3c4a57; --red:#a23b2d;
    --shadow:0 1px 2px rgba(33,29,24,.06),0 8px 24px rgba(33,29,24,.05);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
    font-family:"IBM Plex Sans",sans-serif;
    background-image:radial-gradient(circle at 1px 1px, rgba(33,29,24,.04) 1px, transparent 0);
    background-size:22px 22px;}
  header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;
    padding:22px 28px;border-bottom:1px solid var(--border);background:rgba(246,242,234,.85);
    backdrop-filter:blur(6px);position:sticky;top:0;z-index:5;flex-wrap:wrap}
  .brand{font-family:"Bricolage Grotesque",sans-serif;font-weight:800;font-size:24px;letter-spacing:-.02em}
  .brand span{color:var(--green)}
  .biz{font-size:14px;color:var(--muted)}
  .live{display:inline-flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--green);animation:p 1.8s infinite}
  @keyframes p{0%,100%{opacity:1}50%{opacity:.3}}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;padding:22px 28px}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}
  .stat .k{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
  .stat .v{font-family:"Bricolage Grotesque",sans-serif;font-weight:800;font-size:26px;margin-top:6px;letter-spacing:-.02em}
  .stat.money .v{color:var(--green)}
  h2{font-family:"Bricolage Grotesque",sans-serif;font-weight:600;font-size:15px;
    text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:8px 0}
  .board{display:flex;gap:16px;padding:8px 28px 40px;overflow-x:auto;align-items:flex-start}
  .col{flex:0 0 250px;background:rgba(255,253,248,.5);border:1px solid var(--border);
    border-radius:16px;padding:12px}
  .col .head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
  .col .head .n{background:var(--ink);color:var(--paper);border-radius:20px;font-size:11px;
    padding:2px 9px;font-weight:600}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:13px;
    margin-bottom:10px;box-shadow:var(--shadow);animation:f .35s ease}
  @keyframes f{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  .card .top{display:flex;justify-content:space-between;align-items:baseline}
  .card .id{font-size:12px;color:var(--muted);font-weight:600}
  .card .cust{font-weight:600;margin:2px 0 8px}
  .card ul{margin:0 0 8px;padding-left:16px;font-size:13px;color:#4a443b}
  .card li{margin:1px 0}
  .card .tot{font-family:"Bricolage Grotesque",sans-serif;font-weight:800;font-size:17px;color:var(--green)}
  .card .pm{font-size:11px;color:var(--amber);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
  .acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
  button{font-family:inherit;font-size:12px;font-weight:600;border-radius:8px;padding:6px 11px;
    cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--ink);transition:.15s}
  button:hover{transform:translateY(-1px)}
  button.primary{background:var(--ink);color:var(--paper);border-color:var(--ink)}
  button.ghost{color:var(--red);border-color:#e7c9c3}
  .handoff{margin:0 28px 40px;background:var(--card);border:1px solid var(--border);
    border-radius:16px;padding:18px;box-shadow:var(--shadow)}
  .ho{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 0;border-top:1px solid var(--border)}
  .ho:first-of-type{border-top:0}
  .ho .who{font-weight:600;min-width:120px}
  .ho .msg{flex:1;color:#4a443b;font-size:13px}
  .ho input{flex:2;min-width:160px;padding:8px 11px;border:1px solid var(--border);border-radius:8px;font-family:inherit}
  .empty{color:var(--muted);font-size:13px;padding:6px 0}
  .badge-amber{color:var(--amber)}
</style>
</head>
<body>
<header>
  <div>
    <div class="brand">Pedidos<span>.</span></div>
    <div class="biz" id="biz">Cargando…</div>
  </div>
  <div class="live"><span class="dot"></span> En vivo · actualiza cada 8s</div>
</header>

<div class="stats" id="stats"></div>

<div style="padding:0 28px"><h2>Tablero de pedidos</h2></div>
<div class="board" id="board"></div>

<div class="handoff">
  <h2>Atención humana</h2>
  <div id="handoffs"></div>
</div>

<script>
const BID = __BID__;
const COLS = [
  ["draft","Borrador"],["awaiting_payment","Por pagar"],["payment_review","Por verificar"],
  ["paid","Pagado"],["preparing","Preparando"],["completed","Completado"]
];
const NEXT = {
  draft:[["cancelled","Cancelar","ghost"]],
  awaiting_payment:[["paid","Marcar pagado","primary"],["cancelled","Cancelar","ghost"]],
  payment_review:[["paid","Verificar ✓","primary"],["cancelled","Rechazar","ghost"]],
  paid:[["preparing","Preparando","primary"],["completed","Completado","primary"]],
  preparing:[["completed","Completado","primary"]],
  completed:[],cancelled:[]
};
const esc = s => (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

async function api(path, opts){ const r = await fetch(path, opts); return r.ok ? r.json() : null; }

async function load(){
  const [board, report] = await Promise.all([
    api(`/admin/businesses/${BID}/board`),
    api(`/admin/businesses/${BID}/report`)
  ]);
  if(report){
    document.getElementById("biz").textContent = report.business + " · " + report.date;
    document.getElementById("stats").innerHTML = `
      <div class="stat"><div class="k">Pedidos hoy</div><div class="v">${report.orders_total}</div></div>
      <div class="stat"><div class="k">Pagados</div><div class="v">${report.orders_paid}</div></div>
      <div class="stat money"><div class="k">Ingresos</div><div class="v">${report.revenue}</div></div>
      <div class="stat money"><div class="k">Ticket promedio</div><div class="v">${report.avg_ticket}</div></div>`;
  }
  if(board){ renderBoard(board.orders); renderHandoffs(board.handoffs); }
}

function renderBoard(orders){
  const board = document.getElementById("board");
  board.innerHTML = "";
  for(const [key,label] of COLS){
    const list = orders.filter(o=>o.status===key);
    const col = document.createElement("div"); col.className="col";
    col.innerHTML = `<div class="head"><span>${label}</span><span class="n">${list.length}</span></div>`;
    for(const o of list) col.appendChild(cardEl(o));
    board.appendChild(col);
  }
}

function cardEl(o){
  const el = document.createElement("div"); el.className="card";
  const items = (o.items||[]).map(i=>`<li>${i.quantity}× ${esc(i.name)}</li>`).join("");
  const pm = o.payment_method ? `<div class="pm">${esc(o.payment_method)}</div>` : "";
  const acts = (NEXT[o.status]||[]).map(([s,t,cls])=>
    `<button class="${cls}" onclick="setStatus(${o.order_id},'${s}')">${t}</button>`).join("");
  el.innerHTML = `<div class="top"><span class="id">#${o.order_id}</span><span class="tot">${o.total}</span></div>
    <div class="cust">${esc(o.customer)}</div><ul>${items}</ul>${pm}<div class="acts">${acts}</div>`;
  return el;
}

function renderHandoffs(hs){
  const box = document.getElementById("handoffs");
  if(!hs || !hs.length){ box.innerHTML = `<div class="empty">Sin conversaciones que requieran una persona. 🎉</div>`; return; }
  box.innerHTML = "";
  for(const h of hs){
    const row = document.createElement("div"); row.className="ho";
    row.innerHTML = `<span class="who">${esc(h.customer)}</span>
      <span class="msg">“${esc(h.last_message)}”</span>
      <input placeholder="Escribe tu respuesta…" id="r${h.conversation_id}">
      <button class="primary" onclick="reply(${h.conversation_id})">Enviar</button>
      <button onclick="release(${h.conversation_id})">Devolver al bot</button>`;
    box.appendChild(row);
  }
}

async function setStatus(id, status){
  await api(`/admin/orders/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});
  load();
}
async function reply(cid){
  const input = document.getElementById("r"+cid); const text = input.value.trim(); if(!text) return;
  await api(`/admin/conversations/${cid}/reply`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
  input.value=""; load();
}
async function release(cid){
  await api(`/admin/conversations/${cid}/handoff`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"release"})});
  load();
}

load();
setInterval(load, 8000);
</script>
</body>
</html>"""


@router.get("/dashboard/{business_id}", response_class=HTMLResponse)
def dashboard(business_id: int):
    return _PAGE.replace("__BID__", str(business_id))

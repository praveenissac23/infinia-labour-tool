// Working offline - the banner at the top and the list of saves waiting (the work itself is done by /sw.js).
// Server down (an update restarting it, an outage, the office internet): a yellow banner, work goes on, every
// save is kept on this computer. Back: the saves go up by themselves, the banner turns green and goes.
(function () {
  if (!("serviceWorker" in navigator)) return;
  const TOP = window.parent === window;                    // pages in a frame (Estimation, Trello ...) leave the banner to the page around them
  let S = { offline: false, pending: 0, failed: 0, items: [] }, okTimer = 0, ping = 0, bar = null, list = null;
  try { navigator.serviceWorker.register("/sw.js").catch(() => {}); } catch (e) {}
  const post = m => { const c = navigator.serviceWorker.controller; if (c) c.postMessage(m); };
  navigator.serviceWorker.addEventListener("message", e => { const d = e.data || {}; if (d.type === "offline-state") update(d); });
  navigator.serviceWorker.ready.then(() => { post({ type: "offline-hello" }); post({ type: "offline-replay" }); });
  addEventListener("online", () => post({ type: "offline-up" }));
  addEventListener("offline", () => update(Object.assign({}, S, { offline: true })));

  if (!TOP) return;
  const css = document.createElement("style");
  css.textContent = `#off-bar{position:fixed;top:0;left:0;right:0;z-index:6000;display:none;align-items:center;gap:14px;padding:10px 18px;font:14px/1.35 Inter,-apple-system,"Segoe UI",sans-serif;box-shadow:0 2px 10px rgba(0,0,0,.18)}
  #off-bar.on{display:flex} #off-bar b{font-weight:700} #off-bar .sp{flex:1}
  #off-bar.off{background:#FFF1D6;color:#5A3D00;border-bottom:2px solid #E0A526} #off-bar.syn{background:#E4EEFB;color:#1D3F70;border-bottom:2px solid #5B8DD6}
  #off-bar.ok{background:#E3F4E4;color:#1E5B2A;border-bottom:2px solid #4CAF50} #off-bar.bad{background:#FBE0DE;color:#7A1F16;border-bottom:2px solid #C0392B}
  #off-bar .dot{width:10px;height:10px;border-radius:50%;background:currentColor;flex:none;opacity:.8}
  #off-bar.off .dot{background:#E0A526;box-shadow:0 0 0 4px rgba(224,165,38,.25);animation:offp 1.6s infinite} @keyframes offp{50%{box-shadow:0 0 0 7px rgba(224,165,38,.08)}}
  #off-bar .off-pill{text-transform:none;letter-spacing:0;background:#fff;border:1px solid rgba(0,0,0,.12);border-radius:20px;padding:3px 12px;font-weight:600;font-size:13px;white-space:nowrap}
  #off-bar button{text-transform:none;letter-spacing:0;box-shadow:none;height:auto;border:1px solid rgba(0,0,0,.18);background:#fff;border-radius:7px;padding:5px 12px;font:600 13px Inter,sans-serif;color:inherit;cursor:pointer;white-space:nowrap}
  #off-list{position:fixed;top:52px;right:18px;width:min(560px,calc(100vw - 32px));max-height:70vh;overflow:auto;background:#fff;border-radius:12px;box-shadow:0 18px 50px rgba(0,0,0,.35);z-index:6001;font:13.5px/1.4 Inter,-apple-system,sans-serif;color:#2B2B2B;display:none}
  #off-list.on{display:block} #off-list h3{margin:0;padding:13px 18px;border-bottom:1px solid #eee;font-size:15px;display:flex;align-items:center}
  #off-list h3 span{flex:1} #off-list h3 button{border:0;background:none;font-size:20px;cursor:pointer;color:#888}
  #off-list .it{display:flex;gap:12px;padding:10px 18px;border-bottom:1px solid #f1eeea;align-items:center}
  #off-list .it small{display:block;color:#888;font-size:12px} #off-list .it .er{color:#9B2C20;font-size:12px}
  #off-list .tag{margin-left:auto;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
  #off-list .w{background:#FFF1D6;color:#7A5200} #off-list .f{background:#FBE0DE;color:#9B2C20}
  #off-list .x{border:1px solid #e3d9d0;background:#fff;border-radius:6px;padding:3px 8px;font-size:12px;cursor:pointer}
  #off-list .note{padding:12px 18px;color:#6B625A;font-size:12.5px} body.off-pad{padding-top:44px}
  @media (max-width:700px){#off-bar{font-size:12.5px;padding:8px 12px;gap:8px;flex-wrap:wrap}}`;
  document.head.appendChild(css);
  bar = document.createElement("div"); bar.id = "off-bar"; bar.setAttribute("role", "status");
  list = document.createElement("div"); list.id = "off-list";
  const mount = () => { document.body.appendChild(bar); document.body.appendChild(list); };
  if (document.body) mount(); else addEventListener("DOMContentLoaded", mount);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const p2 = n => String(n).padStart(2, "0");      // dd/mm/yyyy HH:mm, as every date in the app reads
  const hm = t => { const d = new Date(t); return `${p2(d.getDate())}/${p2(d.getMonth() + 1)}/${d.getFullYear()} ${d.toTimeString().slice(0, 5)}`; };

  function draw() {
    if (!bar) return;
    const n = S.pending, f = S.failed;
    let cls = "", html = "";
    if (S.offline) {
      cls = "off";
      html = `<span class="dot"></span><span><b>Working offline</b> - the server can't be reached (update or outage). Keep working: your saves stay on this computer and upload by themselves.</span><span class="sp"></span>${n ? `<span class="off-pill">${n} saved on this computer</span><button data-off="list">See them</button>` : ""}`;
    } else if (S.syncing && n) {
      cls = "syn"; html = `<span class="dot"></span><span><b>Back online</b> - uploading ${n} saved item${n === 1 ? "" : "s"}... keep this page open a moment.</span><span class="sp"></span>`;
    } else if (f) {
      cls = "bad"; html = `<span class="dot"></span><span><b>${f} saved item${f === 1 ? "" : "s"} could not be uploaded</b> - the server refused ${f === 1 ? "it" : "them"} (see why, then redo).</span><span class="sp"></span><button data-off="list">See why</button>`;
    } else if (n) {
      cls = "off"; html = `<span class="dot"></span><span><b>${n} saved item${n === 1 ? "" : "s"} waiting to upload</b> from this computer.</span><span class="sp"></span><button data-off="list">See them</button><button data-off="retry">Upload now</button>`;
    } else if (okTimer) {
      cls = "ok"; html = `<span class="dot"></span><span><b>Back online</b> - ${S.uploaded || ""} saved item${S.uploaded === 1 ? "" : "s"} uploaded. Everything is up to date.</span><span class="sp"></span><button data-off="refresh">Refresh the page</button><button data-off="ok">OK</button>`;
    }
    bar.className = cls ? "on " + cls : ""; bar.innerHTML = html;
    document.body && document.body.classList.toggle("off-pad", !!cls);
    bar.querySelectorAll("[data-off]").forEach(b => b.onclick = () => {
      const a = b.dataset.off;
      if (a === "list") { drawList(); list.classList.toggle("on"); }
      if (a === "retry") post({ type: "offline-up" });
      if (a === "ok") { clearTimeout(okTimer); okTimer = 0; draw(); }
      if (a === "refresh") location.reload();
    });
    if (list.classList.contains("on")) drawList();
  }
  function drawList() {
    const it = S.items || [];
    list.innerHTML = `<h3><span>${S.offline ? "Waiting to upload - kept on this computer" : "Saved on this computer"}</span><button title="Close">&times;</button></h3>
      ${it.length ? it.map(x => `<div class="it"><div>${esc(x.where)}: ${esc(x.label)}<small>saved ${hm(x.at)}</small>${x.err ? `<div class="er">${esc(x.err)}</div>` : ""}</div>
        ${x.st === "failed" ? `<span class="tag f">not saved</span><button class="x" data-drop="${x.n}" title="Remove it from this list (redo it on its page)">Remove</button>` : `<span class="tag w">waiting</span>`}</div>`).join("") : `<div class="note">Nothing waiting.</div>`}
      <div class="note">These stay on this computer even if the browser is closed or the computer is switched off - they upload the next time the app is opened here. Things that need the server (a new LPO or invoice number, sending to Zoho) wait until it's back.</div>`;
    list.querySelector("h3 button").onclick = () => list.classList.remove("on");
    list.querySelectorAll("[data-drop]").forEach(b => b.onclick = () => post({ type: "offline-drop", n: +b.dataset.drop }));
  }
  function update(d) {
    const was = S;
    S = Object.assign({}, S, d);
    if (d.justUploaded && !S.pending && !S.failed) {
      // the page was drawn from what was kept: show what is on the server now (unless someone is typing)
      const a = document.activeElement, typing = a && /INPUT|TEXTAREA|SELECT/.test(a.tagName) && a.id !== "qa-title";
      if (!typing) { try { sessionStorage.setItem("off_up", String(d.justUploaded)); } catch (e) {} setTimeout(() => location.reload(), 600); }
      clearTimeout(okTimer); okTimer = setTimeout(() => { okTimer = 0; draw(); }, 8000);
    }
    if (d.justQueued && window.toast) { try { toast("Saved on this computer - it uploads when the server is back"); } catch (e) {} }
    // while it's down: ask the server every 8 seconds; the moment it answers, the saves go up
    if (S.offline && !ping) ping = setInterval(async () => {
      try { const r = await fetch("/health?off=" + Date.now(), { cache: "no-store" }); if (r.ok) { clearInterval(ping); ping = 0; post({ type: "offline-up" }); } } catch (e) {}
    }, 8000);
    if (!S.offline && ping) { clearInterval(ping); ping = 0; }
    if (was.offline && !S.offline && !S.pending) { /* came back with nothing to send */ }
    draw();
  }
  try { const up = +sessionStorage.getItem("off_up"); if (up) { sessionStorage.removeItem("off_up"); S.uploaded = up; okTimer = setTimeout(() => { okTimer = 0; draw(); }, 8000); setTimeout(draw, 0); } } catch (e) {}
  // Closing with saves not uploaded yet: the browser asks first (they are kept either way).
  addEventListener("beforeunload", e => { if (S.pending > 0) { e.preventDefault(); e.returnValue = ""; } });
  window.OFFLINE_STATE = () => S;
})();

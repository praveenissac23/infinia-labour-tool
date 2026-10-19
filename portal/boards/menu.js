/* Estimation > Trello - the board menu (right panel), Share, Automation (Butler), Power-Ups, background, export. */
"use strict";
function boardMenu(section, preset) {
  let m = $("#bmenu");
  if (m && !section) { m.remove(); return; }
  if (!m) { m = h(`<aside id="bmenu"><div class="bm-h"><span data-back></span><h2></h2><button class="x" data-x>${ic("x")}</button></div><div class="bm-b"></div></aside>`); $("#board").appendChild(m); m.querySelector("[data-x]").onclick = () => m.remove(); }
  const show = (title, html, back = true) => {
    m.querySelector("h2").textContent = title;
    m.querySelector("[data-back]").outerHTML = back ? `<button class="x" data-back>${ic("left")}</button>` : "<span data-back></span>";
    const bb = m.querySelector("[data-back]"); if (back) bb.onclick = () => boardMenu("main");
    m.querySelector(".bm-b").innerHTML = html; return m.querySelector(".bm-b");
  };
  const b = S.board, admin = b.role === "admin";
  const sec = section || "main";
  if (sec === "main") {
    const body = show("Menu", `
      <button class="mi" data-s="about">${ic("info", "s20")}<div>About this board<small>Add a description to your board</small></div></button>
      <button class="mi" data-s="visibility">${ic(b.visibility === "private" ? "lock" : "team", "s20")}<div>Visibility: ${b.visibility === "private" ? "Private" : "Workspace"}</div></button>
      <button class="mi" data-s="export">${ic("print", "s20")} Print, export, and share</button>
      <button class="mi" data-s="star">${ic("star", "s20")} ${b.starred ? "Unstar" : "Star"}</button>
      <hr>
      <button class="mi" data-s="settings">${ic("gear", "s20")} Settings</button>
      <button class="mi" data-s="background"><span class="swatch" style="background:${bgCss(b.bg, b.bg_url)}"></span> Change background</button>
      <button class="mi" data-s="fields">${ic("field", "s20")} Custom Fields</button>
      <hr>
      <button class="mi" data-s="automation">${ic("bolt", "s20")}<div>Automation<small>${b.rules} rule${b.rules === 1 ? "" : "s"} · buttons · schedules</small></div></button>
      <button class="mi" data-s="powerups">${ic("plug", "s20")} Power-Ups</button>
      <button class="mi" data-s="labels">${ic("tag", "s20")} Labels</button>
      <hr>
      <button class="mi" data-s="activity">${ic("act", "s20")} Activity</button>
      <button class="mi" data-s="archived">${ic("archive", "s20")} Archived items</button>
      <hr>
      <button class="mi" data-s="copy">${ic("copy", "s20")} Copy board</button>
      ${admin ? `<button class="mi" data-s="template">${ic("tpl", "s20")} ${b.is_template ? "Stop being a template" : "Make template"}</button>` : ""}
      <button class="mi" data-s="leave">${ic("leave", "s20")} Leave board</button>
      ${admin ? `<button class="mi" data-s="close" style="color:var(--danger)">${ic("archive", "s20")} Close board</button>` : ""}`, false);
    $$("[data-s]", body).forEach(x => x.onclick = () => boardMenu(x.dataset.s));
    return;
  }
  if (sec === "star") { POST(`/store/kb/boards/${b.id}/star`).then(r => { b.starred = r.starred; renderHeader(); boardMenu("main"); }); return; }
  if (sec === "visibility") { m.remove(); visibilityPop($("#bh-vis") || $("#bh-menu")); return; }
  if (sec === "leave") { confirmPop($("#bh-menu"), "Leave board?", "You will be removed from all cards on this board.", "Leave", async () => { try { await DEL(`/store/kb/boards/${b.id}/members/${S.me.id}`); m.remove(); go("#/"); } catch (e) { fail(e); } }); return; }
  if (sec === "template") { PATCH(`/store/kb/boards/${b.id}`, { is_template: !b.is_template }).then(() => { toast(b.is_template ? "No longer a template" : "This board is now a template - find it under Templates"); reloadBoard(true).then(() => boardMenu("main")); }).catch(fail); return; }
  if (sec === "close") {
    const body = show("Close board?", `<p>You can find and reopen closed boards at the bottom of your boards page.</p><button class="b dng" style="width:100%" data-c>Close</button>`);
    body.querySelector("[data-c]").onclick = async () => { try { await PATCH(`/store/kb/boards/${b.id}`, { closed: true }); m.remove(); toast("Board closed"); go("#/"); } catch (e) { fail(e); } };
    return;
  }
  if (sec === "about") {
    const body = show("About this board", `<h4 style="margin:4px 0 8px;display:flex;gap:8px;align-items:center">${ic("users")} Board admins</h4>
      ${b.members.filter(x => x.board_role === "admin").map(x => `<div class="share-row">${av(x, "lg")}<div class="nm">${esc(x.name)}<small>@${esc(x.username)}</small></div></div>`).join("")}
      <h4 style="margin:16px 0 8px;display:flex;gap:8px;align-items:center">${ic("desc")} Description</h4>
      <div data-d>${b.desc ? `<div class="md desc-view" style="cursor:pointer">${md(b.desc)}</div>` : `<div class="desc-empty" style="cursor:pointer;padding:8px 12px;border-radius:3px;background:var(--neutral)">Add a description to let your teammates know what this board is used for.</div>`}</div>`);
    body.querySelector("[data-d]").onclick = () => {
      const box = body.querySelector("[data-d]"); box.onclick = null;
      box.innerHTML = `<textarea class="t" rows="6">${esc(b.desc)}</textarea><div style="display:flex;gap:8px;margin-top:8px"><button class="b pri" data-s>Save</button><button class="b sub" data-x>Cancel</button></div>`;
      box.querySelector("textarea").focus();
      box.querySelector("[data-s]").onclick = async () => { try { await PATCH(`/store/kb/boards/${b.id}`, { desc: box.querySelector("textarea").value }); await reloadBoard(true); boardMenu("about"); } catch (e) { fail(e); } };
      box.querySelector("[data-x]").onclick = () => boardMenu("about");
    };
    return;
  }
  if (sec === "settings") {
    const p = b.prefs || {};
    const body = show("Settings", `
      <h4 style="margin:4px 0 4px">Workspace</h4><p class="muted" style="margin:0 0 12px">Infinia Estimation</p>
      <h4 style="margin:4px 0 4px">Permissions</h4>
      <button class="mi" data-p="comments"><div>Commenting<small>${p.comments === "members" ? "Members (observers cannot comment)" : "Members and observers"}</small></div></button>
      <button class="mi" data-p="visibility"><div>Visibility<small>${b.visibility === "private" ? "Private" : "Workspace"}</small></div></button>
      <hr><h4 style="margin:4px 0 4px">Cards</h4>
      <button class="mi" data-t="auto_cover"><div style="flex:1">Card covers<small>Show the first image as the cover</small></div><span class="tgl ${p.auto_cover !== false ? "on" : ""}"></span></button>
      <button class="mi" data-t="card_numbers"><div style="flex:1">Card numbers<small>Show #12 on each card</small></div><span class="tgl ${p.card_numbers ? "on" : ""}"></span></button>
      <button class="mi" data-t="lab_open"><div style="flex:1">Label names on cards<small>Show label text, not just colour (; key)</small></div><span class="tgl ${document.body.classList.contains("lab-open") ? "on" : ""}"></span></button>`);
    $$("[data-t]", body).forEach(x => x.onclick = async () => {
      const k = x.dataset.t;
      if (k === "lab_open") { document.body.classList.toggle("lab-open"); try { localStorage.setItem("kb_lab_open", document.body.classList.contains("lab-open") ? "1" : ""); } catch (e) {} boardMenu("settings"); return; }
      const v = k === "auto_cover" ? p.auto_cover === false : !p[k];
      try { await PATCH(`/store/kb/boards/${b.id}`, { prefs: { [k]: v } }); await reloadBoard(true); boardMenu("settings"); } catch (e) { fail(e); }
    });
    body.querySelector('[data-p="comments"]').onclick = async () => { try { await PATCH(`/store/kb/boards/${b.id}`, { prefs: { comments: p.comments === "members" ? "all" : "members" } }); await reloadBoard(true); boardMenu("settings"); } catch (e) { fail(e); } };
    body.querySelector('[data-p="visibility"]').onclick = e => visibilityPop(e.currentTarget);
    return;
  }
  if (sec === "background") {
    const keys = Object.keys(BG);
    const body = show("Change background", `<div class="pop" style="position:static;width:auto;box-shadow:none;padding:0;animation:none">
      <h5 style="margin-top:4px">Photos</h5><button class="b" style="width:100%" data-up>${ic("upload")} Upload a photo</button><input type="file" accept="image/*" class="hide" data-f>
      <h5>Gradients</h5><div class="bggrid">${keys.filter(k => k.startsWith("g_")).map(k => `<button data-bg="${k}" class="${b.bg === k ? "on" : ""}" style="background:${BG[k]}"></button>`).join("")}</div>
      <h5>Colors</h5><div class="bggrid">${keys.filter(k => !k.startsWith("g_")).map(k => `<button data-bg="${k}" class="${b.bg === k ? "on" : ""}" style="background:${BG[k]}"></button>`).join("")}</div>
      <h5>Custom colour</h5><input type="color" data-cc value="${bgBase(b.bg)}" style="width:100%;height:40px;border:0;padding:0;background:none"></div>`);
    const setBg = async v => { try { await PATCH(`/store/kb/boards/${b.id}`, { bg: v }); await reloadBoard(false); boardMenu("background"); } catch (e) { fail(e); } };
    $$("[data-bg]", body).forEach(x => x.onclick = () => setBg(x.dataset.bg));
    body.querySelector("[data-cc]").onchange = e => setBg("c:" + e.target.value);
    const f = body.querySelector("[data-f]"); body.querySelector("[data-up]").onclick = () => f.click();
    f.onchange = async () => { const file = await shrinkImage(f.files[0]); const fd = new FormData(); fd.append("file", file, file.name); try { toast("Uploading..."); await api(`/store/kb/boards/${b.id}/background`, { method: "POST", body: fd }); await reloadBoard(false); boardMenu("background"); } catch (e) { fail(e); } };
    return;
  }
  if (sec === "labels") {
    const body = show("Labels", `<p class="muted" style="margin:0 0 8px">Labels</p>${b.labels.map(l => `<div class="pop" style="position:static;width:auto;box-shadow:none;padding:0;animation:none"><div class="lrow">${labHtml(l)}<button class="x" data-e="${l.id}">${ic("edit", "s14")}</button></div></div>`).join("")}<button class="b" style="width:100%;margin-top:8px" data-new>Create a new label</button>`);
    $$("[data-e]", body).forEach(x => x.onclick = () => { const p = pop(x, "Labels", ""); labelEditPop(p, null, b.labels.find(l => l.id === +x.dataset.e), () => { closePops(); boardMenu("labels"); }); });
    body.querySelector("[data-new]").onclick = e => { const p = pop(e.currentTarget, "Labels", ""); labelEditPop(p, null, null, () => { closePops(); boardMenu("labels"); }); };
    return;
  }
  if (sec === "fields") {
    const types = { text: "Text", number: "Number", date: "Date", checkbox: "Checkbox", list: "Dropdown" };
    const body = show("Custom Fields", `${b.fields.map(f => `<div class="rule"><div class="rh">${ic("field")}<div class="rt"><b>${esc(f.name)}</b><div class="rr">${types[f.type]}${f.type === "list" ? ": " + f.options.map(o => esc(o.text)).join(", ") : ""} · ${f.on_front ? "shown on front of card" : "hidden on front"}</div></div><button class="x" data-ed="${f.id}">${ic("edit", "s14")}</button></div></div>`).join("") || '<p class="muted">Custom Fields let you add structured data to cards - e.g. Value (AED), Stage, Consultant, Plot no.</p>'}
      <button class="b pri" style="width:100%;margin-top:8px" data-new>${ic("plus", "s14")} New field</button>`);
    const edit = f => {
      const fb = show(f ? "Edit field" : "New field", `<label class="fl">Title</label><input class="t" data-n value="${esc(f ? f.name : "")}" placeholder="Add a title…">
        <label class="fl">Type</label><select class="t" data-ty ${f ? "disabled" : ""}>${Object.entries(types).map(([k, v]) => `<option value="${k}" ${f && f.type === k ? "selected" : ""}>${v}</option>`).join("")}</select>
        <div data-opts></div>
        <div style="margin-top:12px"><label class="chk"><input type="checkbox" data-fr ${!f || f.on_front ? "checked" : ""}> Show field on front of card</label></div>
        <div style="display:flex;gap:8px;margin-top:16px"><button class="b pri" data-s>${f ? "Save" : "Create"}</button>${f ? '<button class="b dng" data-d>Delete field</button>' : ""}</div>`);
      fb.querySelector("[data-back]") || 0;
      m.querySelector("[data-back]").onclick = () => boardMenu("fields");
      let opts = f ? f.options.map(o => ({ ...o })) : [];
      const drawOpts = () => { const ty = fb.querySelector("[data-ty]").value; fb.querySelector("[data-opts]").innerHTML = ty !== "list" ? "" : `<label class="fl">Options</label>${opts.map((o, i) => `<div style="display:flex;gap:6px;margin-bottom:6px"><select class="t" data-oc="${i}" style="width:90px">${["", ...COVER_COLORS].map(c => `<option value="${c}" ${o.color === c ? "selected" : ""}>${c || "none"}</option>`).join("")}</select><input class="t" data-ot="${i}" value="${esc(o.text)}"><button class="x" data-orm="${i}">${ic("x", "s14")}</button></div>`).join("")}<div style="display:flex;gap:6px"><input class="t" data-onew placeholder="Add item…"><button class="b" data-oadd>Add</button></div>`;
        $$("[data-ot]", fb).forEach(x => x.oninput = () => opts[+x.dataset.ot].text = x.value); $$("[data-oc]", fb).forEach(x => x.onchange = () => opts[+x.dataset.oc].color = x.value);
        $$("[data-orm]", fb).forEach(x => x.onclick = () => { opts.splice(+x.dataset.orm, 1); drawOpts(); });
        const add = fb.querySelector("[data-oadd]"); if (add) { const n = fb.querySelector("[data-onew]"); const doAdd = () => { if (n.value.trim()) { opts.push({ text: n.value.trim(), color: "" }); drawOpts(); fb.querySelector("[data-onew]").focus(); } }; add.onclick = doAdd; n.onkeydown = e => { if (e.key === "Enter") doAdd(); }; } };
      fb.querySelector("[data-ty]").onchange = drawOpts; drawOpts();
      fb.querySelector("[data-s]").onclick = async () => {
        const name = fb.querySelector("[data-n]").value.trim(); if (!name) return;
        try { if (f) await PATCH(`/store/kb/fields/${f.id}`, { name, on_front: fb.querySelector("[data-fr]").checked, options: opts });
          else await POST(`/store/kb/boards/${b.id}/fields`, { name, type: fb.querySelector("[data-ty]").value, on_front: fb.querySelector("[data-fr]").checked, options: opts });
          await reloadBoard(true); boardMenu("fields"); } catch (e) { fail(e); }
      };
      const d = fb.querySelector("[data-d]"); if (d) d.onclick = () => confirmPop(d, "Delete field?", "The values on every card will be removed. There is no undo.", "Delete", async () => { await DEL(`/store/kb/fields/${f.id}`); await reloadBoard(true); boardMenu("fields"); });
    };
    $$("[data-ed]", body).forEach(x => x.onclick = () => edit(b.fields.find(f => f.id === +x.dataset.ed)));
    body.querySelector("[data-new]").onclick = () => edit(null);
    return;
  }
  if (sec === "powerups") {
    const on = (b.prefs.powerups || DEFAULT_PU);
    const list = [
      ["dashboard", "chart", "#6E5DC6", "Dashboard", "Team workload, work distribution, progress and due-date charts (Jira style)."],
      ["calendar", "cal", "#0C66E4", "Calendar", "See cards with dates on a calendar; drag to reschedule."],
      ["timeline", "timeline", "#227D9B", "Timeline", "Gantt bars from start to due date, by list or by member."],
      ["table", "table", "#1F845A", "Table", "Every card in a sortable table."],
      ["mindmap", "mind", "#AE4787", "Mind Map", "The board as a mind map: board > lists > cards."],
      ["fields", "field", "#C25100", "Custom Fields", "Add your own fields to cards: text, number, date, checkbox, dropdown."],
      ["automation", "bolt", "#0055CC", "Automation (Butler)", "Rules, schedules, due-date commands, card and board buttons - across boards."],
      ["priority", "flag", "#C9372C", "Priority & story points", "Jira-style priority (Highest … Lowest), story points and estimates."],
      ["time", "timer", "#5B7F24", "Time tracking", "Log hours on cards against an estimate; totals per person."],
      ["voting", "thumb", "#1868DB", "Voting", "Members vote on cards; sort a list by votes."],
      ["repeater", "repeat", "#943D73", "Card Repeater", "Make a copy of a card every day, week, month or year."],
      ["limits", "board", "#626F86", "List Limits", "Set a card limit per list; the list turns red when it is over."],
      ["aging", "clock", "#A54800", "Card Aging", "Cards fade the longer nobody touches them."],
      ["buttons", "btn", "#216E4E", "Card & board buttons", "One-click buttons that run a set of actions."],
    ];
    const body = show("Power-Ups", `<p class="muted" style="margin:0 0 12px">All Power-Ups are free and unlimited here.</p>` + list.map(([k, i, col, t, d]) => `<div class="pu"><span class="pi" style="background:${col}">${ic(i, "s20")}</span><div class="pt"><b>${t}</b><small>${d}</small></div><button class="tgl ${on.includes(k) ? "on" : ""}" data-pu="${k}" ${admin || b.role === "member" ? "" : "disabled"}></button></div>`).join(""));
    $$("[data-pu]", body).forEach(x => x.onclick = async () => {
      const k = x.dataset.pu; const cur = [...(b.prefs.powerups || DEFAULT_PU)];
      const nxt = cur.includes(k) ? cur.filter(y => y !== k) : [...cur, k];
      try { await PATCH(`/store/kb/boards/${b.id}`, { prefs: { powerups: nxt } }); await reloadBoard(true); if (!pu(S.view) && S.view !== "board") setView("board"); boardMenu("powerups"); } catch (e) { fail(e); }
    });
    return;
  }
  if (sec === "activity") {
    const body = show("Activity", `<div style="display:flex;gap:4px;margin-bottom:12px"><button class="b on" data-f="all">All</button><button class="b" data-f="comments">Comments</button></div><div data-feed><div class="spin dk" style="margin:24px auto"></div></div>`);
    const load = async (only) => {
      const d = await GET(`/store/kb/boards/${b.id}/activity${only ? "?only=" + only : ""}`);
      const items = only === "comments" ? d.activity.filter(a => a.kind === "comment") : d.activity;
      body.querySelector("[data-feed]").innerHTML = items.map(a => `<div class="fe act"><span class="av" style="background:${avColor(a.who.length)};width:32px;height:32px">${esc(a.initials)}</span><div class="bd"><div class="line"><b>${esc(a.who)}</b> ${actText(a, false)}</div><a class="when">${ago(a.at)}</a></div></div>`).join("") || '<p class="muted">No activity yet.</p>';
      $$("[data-goc]", body).forEach(x => x.onclick = () => go(`#/b/${b.id}/c/${x.dataset.goc}`));
    };
    $$("[data-f]", body).forEach(x => x.onclick = () => { $$("[data-f]", body).forEach(y => y.classList.toggle("on", y === x)); load(x.dataset.f === "comments" ? "comments" : ""); });
    load("");
    return;
  }
  if (sec === "archived") {
    const body = show("Archived items", `<div style="display:flex;gap:8px;margin-bottom:12px"><input class="t" data-q placeholder="Search archive…"><button class="b" data-sw>Switch to lists</button></div><div data-l><div class="spin dk" style="margin:24px auto"></div></div>`);
    let mode = "cards", data = null;
    const draw = () => {
      const q = body.querySelector("[data-q]").value.toLowerCase(); const box = body.querySelector("[data-l]");
      if (mode === "cards") {
        const cs = data.cards.filter(c => !q || c.title.toLowerCase().includes(q));
        box.innerHTML = cs.map(c => `<div style="margin-bottom:12px"><div class="card" data-c="${c.id}" style="cursor:pointer">${cardHtml(c).replace(/^<div class="card[^"]*"[^>]*>/, "").replace(/<\/div>$/, "")}</div><div style="font-size:12px;margin-top:4px"><a data-re="${c.id}" style="cursor:pointer;text-decoration:underline;color:var(--text-subtle)">Restore</a> · <a data-del="${c.id}" style="cursor:pointer;text-decoration:underline;color:var(--danger)">Delete</a> · <span class="muted">${esc(c.list_title)}</span></div></div>`).join("") || '<p class="muted">No archived cards.</p>';
      } else {
        const ls = data.lists.filter(l => !q || l.title.toLowerCase().includes(q));
        box.innerHTML = ls.map(l => `<div class="share-row"><div class="nm"><b>${esc(l.title)}</b></div><button class="b" data-rl="${l.id}">Restore</button></div>`).join("") || '<p class="muted">No archived lists.</p>';
      }
      $$("[data-re]", box).forEach(x => x.onclick = async () => { await PATCH(`/store/kb/cards/${x.dataset.re}`, { closed: false }); await reloadBoard(true); load(); });
      $$("[data-del]", box).forEach(x => x.onclick = () => confirmPop(x, "Delete card?", "All actions will be removed from the activity feed and you won't be able to re-open the card. There is no undo.", "Delete", async () => { await DEL(`/store/kb/cards/${x.dataset.del}`); load(); }));
      $$("[data-rl]", box).forEach(x => x.onclick = async () => { await PATCH(`/store/kb/lists/${x.dataset.rl}`, { closed: false }); await reloadBoard(true); load(); });
      $$(".card[data-c]", box).forEach(x => x.onclick = () => go(`#/b/${b.id}/c/${x.dataset.c}`));
    };
    const load = async () => { data = await GET(`/store/kb/boards/${b.id}/archived`); draw(); };
    body.querySelector("[data-q]").oninput = draw;
    body.querySelector("[data-sw]").onclick = e => { mode = mode === "cards" ? "lists" : "cards"; e.target.textContent = mode === "cards" ? "Switch to lists" : "Switch to cards"; draw(); };
    load();
    return;
  }
  if (sec === "copy") {
    const body = show("Copy board", `<label class="fl">Title</label><input class="t" data-t value="${esc(b.title)} (copy)"><div style="margin-top:12px"><label class="chk"><input type="checkbox" data-k checked> Keep cards</label></div>
      <p class="muted">Activity, comments, and members will not be copied to the new board.</p><button class="b pri" data-go>Create</button>`);
    body.querySelector("[data-go]").onclick = async () => { try { const r = await POST(`/store/kb/boards/${b.id}/copy`, { title: body.querySelector("[data-t]").value.trim(), keep_cards: body.querySelector("[data-k]").checked }); m.remove(); toast("Board copied"); go("#/b/" + r.id); } catch (e) { fail(e); } };
    return;
  }
  if (sec === "export") {
    const q = exportQuery();
    const body = show("Print, export, and share", `<p class="muted" style="margin:0 0 8px">${filterActive() ? "Only the cards that match your filter are included." : "All cards on the board."}</p>
      <button class="mi" data-e="preview">${ic("eye", "s20")}<div>Preview<small>See the board as a report</small></div></button>
      <button class="mi" data-e="pdf">${ic("print", "s20")}<div>Export PDF<small>Infinia letterhead, landscape</small></div></button>
      <button class="mi" data-e="excel">${ic("table", "s20")}<div>Export Excel</div></button>
      <button class="mi" data-e="json">${ic("json", "s20")}<div>Export as JSON<small>Everything on the board, for backup</small></div></button>
      <button class="mi" data-e="share">${ic("share", "s20")}<div>Share<small>WhatsApp, mail, any app</small></div></button>
      <hr><button class="mi" data-e="link">${ic("link", "s20")} Copy link to board</button><button class="mi" data-e="print">${ic("print", "s20")} Print board</button>`);
    $$("[data-e]", body).forEach(x => x.onclick = async () => {
      const k = x.dataset.e;
      try {
        if (k === "link") return copyText(cardUrl(b.id), "Link copied");
        if (k === "print") return window.print();
        if (k === "json") { const d = await GET(`/store/kb/boards/${b.id}/json`); const blob = new Blob([JSON.stringify(d, null, 1)], { type: "application/json" }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = b.title.replace(/[^\w]+/g, "_") + ".json"; a.click(); return; }
        const t = await POST("/auth/download-token").catch(() => null);
        const tok = t && (t.token || t.download_token);
        if (!tok) throw new Error("Could not make the download link.");
        const url = `/export/kb/${b.id}?token=${encodeURIComponent(tok)}&${q}&format=${k === "share" ? "pdf" : k}`;
        if (k === "share") {
          const r = await fetch(url); const blob = await r.blob(); const file = new File([blob], b.title.replace(/[^\w]+/g, "_") + ".pdf", { type: "application/pdf" });
          if (navigator.canShare && navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: b.title });
          else { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = file.name; a.click(); toast("Sharing isn't available here - the PDF was downloaded"); }
          return;
        }
        window.open(url, "_blank");
      } catch (e) { fail(e); }
    });
    return;
  }
  if (sec === "automation") { automationPanel(m, show, preset); return; }
}
function exportQuery() {
  const f = S.filter || emptyFilter(); const p = new URLSearchParams();
  if (f.q) p.set("q", f.q); if (f.members.length === 1) p.set("member_id", f.members[0]); if (f.labels.length === 1) p.set("label_id", f.labels[0]);
  if (f.due.includes("over")) p.set("due", "overdue"); if (f.status === "complete") p.set("due", "complete");
  return p.toString();
}

// ---------- Share ----------
function shareDlg() {
  const b = S.board, admin = b.role === "admin";
  const d = dlg(`<h2><span>Share board</span><button class="x" data-close>${ic("x")}</button></h2>
    <div style="display:flex;gap:8px;position:relative"><input class="t" data-q placeholder="Name or username" autocomplete="off"><select class="t" data-r style="width:130px"><option value="member">Member</option><option value="observer">Observer</option>${admin ? '<option value="admin">Admin</option>' : ""}</select><button class="b pri" data-add>Share</button><div data-sug class="pop hide" style="position:absolute;top:40px;left:0;width:100%;padding:8px"></div></div>
    <div style="display:flex;align-items:center;gap:12px;margin:16px 0 8px"><span style="width:32px;height:32px;border-radius:50%;background:var(--neutral);display:flex;align-items:center;justify-content:center">${ic("link")}</span><div style="flex:1">Share this board with a link<div><a data-link style="cursor:pointer">Copy link</a></div></div></div>
    <div style="border-bottom:2px solid var(--brand);display:inline-block;padding:4px 0;font-weight:600;color:var(--brand);margin-top:8px">Board members <span class="filt-n" style="background:var(--neutral);border-radius:10px;padding:0 6px;color:var(--text-subtle)">${b.members.length}</span></div>
    <div style="border-top:1px solid var(--border);margin-top:-2px;padding-top:8px" data-ml>${b.members.map(m => `<div class="share-row">${av(m, "lg")}<div class="nm">${esc(m.name)}${m.id === S.me.id ? " (you)" : ""}<small>@${esc(m.username)} · Workspace member</small></div>
      <select class="t" data-role="${m.id}" ${admin || m.id === S.me.id ? "" : "disabled"}>${["admin", "member", "observer"].map(r => `<option value="${r}" ${m.board_role === r ? "selected" : ""}>${r[0].toUpperCase() + r.slice(1)}</option>`).join("")}<option value="remove">${m.id === S.me.id ? "Leave board" : "Remove from board"}</option></select></div>`).join("")}</div>
    <p class="muted" style="margin-top:12px">No limits: add as many people as you like. Anyone with an Infinia login and the Estimation &gt; Trello tick can be added.</p>`, 584);
  let picked = [];
  const q = d.querySelector("[data-q]"), sug = d.querySelector("[data-sug]");
  q.oninput = () => {
    const v = q.value.toLowerCase().replace(/^@/, ""); if (!v) { sug.classList.add("hide"); return; }
    const ppl = b.people.filter(p => !b.members.some(m => m.id === p.id) && (p.name.toLowerCase().includes(v) || p.username.toLowerCase().includes(v))).slice(0, 8);
    sug.innerHTML = ppl.map(p => `<div class="memrow" data-u="${p.id}">${av(p, "lg")}<div class="nm">${esc(p.name)}<small>@${esc(p.username)}</small></div></div>`).join("") || '<div class="muted" style="padding:8px">No one found - they may already be on the board, or need a login.</div>';
    sug.classList.remove("hide");
    $$("[data-u]", sug).forEach(r => r.onclick = () => { picked = [+r.dataset.u]; q.value = (b.people.find(p => p.id === picked[0]) || {}).name || ""; sug.classList.add("hide"); });
  };
  d.querySelector("[data-add]").onclick = async () => {
    if (!picked.length) { const v = q.value.toLowerCase(); const p = b.people.find(x => x.username.toLowerCase() === v || x.name.toLowerCase() === v); if (p) picked = [p.id]; }
    if (!picked.length) { q.focus(); return; }
    try { await POST(`/store/kb/boards/${b.id}/members`, { user_ids: picked, role: d.querySelector("[data-r]").value }); await reloadBoard(true); d.remove(); shareDlg(); toast("Added to the board"); } catch (e) { fail(e); }
  };
  d.querySelector("[data-link]").onclick = () => copyText(cardUrl(b.id), "Link copied");
  $$("[data-role]", d).forEach(s => s.onchange = async () => {
    const uid = +s.dataset.role;
    try { if (s.value === "remove") await DEL(`/store/kb/boards/${b.id}/members/${uid}`); else await PATCH(`/store/kb/boards/${b.id}/members/${uid}`, { role: s.value });
      await reloadBoard(true); d.remove(); if (s.value === "remove" && uid === S.me.id && b.visibility === "private") go("#/"); else shareDlg(); } catch (e) { fail(e); d.remove(); shareDlg(); }
  });
}

// ---------- Automation (Butler) ----------
const TRIG = {
  card_added: "When a card is added to list…", card_moved: "When a card is moved into list…", card_created: "When a card is created (any list)",
  card_complete: "When a card is marked complete", card_archived: "When a card is archived", due_set: "When a due date is set on a card",
  checklist_done: "When all checklist items on a card are done", item_done: "When a checklist item is checked",
  label_added: "When a label is added to a card…", member_added: "When a member is added to a card…", comment_added: "When a comment is posted to a card",
  schedule: "On a schedule (every day / week / month)", due_in: "When a card is due in … days",
};
const ACT = {
  move: "Move the card to list…", move_top: "Move the card to the top of list…", complete: "Mark the card complete", incomplete: "Mark the card incomplete",
  add_label: "Add label…", remove_label: "Remove label…", add_member: "Add member…", remove_member: "Remove member…", join: "Add the person who did it",
  set_due: "Set due date … days from now", clear_due: "Remove the due date", archive: "Archive the card", comment: "Post a comment…",
  add_checklist: "Add a checklist with items…", set_cover: "Set the cover colour…", remove_cover: "Remove the cover", watch: "Watch the card",
  notify: "Notify the card's members…", sort_list: "Sort a list…",
  move_board: "Move the card to another board…", copy_board: "Copy the card to another board…", mirror_board: "Mirror the card on another board (stays in sync)…",
};
async function automationPanel(m, show, preset) {
  const b = S.board;
  let tab = preset && preset.tab || "rules";
  const draw = async () => {
    const d = await GET(`/store/kb/boards/${b.id}/rules`);
    const lists = Object.fromEntries(b.lists.map(l => [l.id, l.title]));
    const rules = d.rules.filter(r => tab === "rules" ? !["schedule", "due_in"].includes(r.trigger.type) : tab === "schedule" ? r.trigger.type === "schedule" : r.trigger.type === "due_in");
    const btns = tab === "card_buttons" ? (b.prefs.card_buttons || []) : tab === "board_buttons" ? (b.prefs.board_buttons || []) : null;
    const body = show("Automation", `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">${[["rules", "Rules"], ["schedule", "Scheduled"], ["due", "Due date"], ["card_buttons", "Card buttons"], ["board_buttons", "Board buttons"]].map(([k, l]) => `<button class="b sm ${tab === k ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}</div>
      ${btns ? btns.map((x, i) => `<div class="rule"><div class="rh">${ic("btn")}<div class="rt"><b>${esc(x.name)}</b><div class="rr">${(x.actions || []).map(a => esc(actWords(a))).join(" · ")}${x.list_id ? ` · on cards in "${esc(lists[x.list_id] || "?")}"` : ""}</div></div><button class="x" data-bdel="${i}">${ic("trash", "s14")}</button></div></div>`).join("") || `<p class="muted">${tab === "card_buttons" ? "Card buttons show on the back of every card. One click runs their actions on that card." : "Board buttons show in the board header. One click runs their actions on every card in a list."}</p>`
      : rules.map(r => `<div class="rule"><div class="rh"><button class="tgl ${r.enabled ? "on" : ""}" data-en="${r.id}" title="On / off"></button><div class="rt"><b>${esc(r.words)}</b>, ${r.actions.map(a => esc(actWords(a))).join(", then ")}
          <div class="rr">Ran ${r.runs} time${r.runs === 1 ? "" : "s"}${r.log && r.log[0] ? " · last " + ago(r.log[0].at) : ""} ${r.log && r.log.length ? `· <a data-log="${r.id}" style="cursor:pointer;text-decoration:underline">log</a>` : ""}</div></div>
          ${r.trigger.type === "schedule" ? `<button class="x" data-run="${r.id}" title="Run now">${ic("bolt", "s14")}</button>` : ""}<button class="x" data-rdel="${r.id}" title="Delete">${ic("trash", "s14")}</button></div><div data-logbox="${r.id}" class="hide" style="margin-top:6px;font-size:12px">${(r.log || []).map(l => `<div class="muted">${ago(l.at)} · ${esc(l.card || "board")} · ${esc((l.did || []).join(", "))}</div>`).join("")}</div></div>`).join("") || `<p class="muted">${tab === "rules" ? "Rules run when something happens on a card - including moving, copying or mirroring it to another board." : tab === "schedule" ? "Scheduled commands run every day, week or month at a set time." : "Due date commands run a set number of days before or after cards are due."}</p>`}
      <button class="b pri" style="width:100%;margin-top:8px" data-new>${ic("plus", "s14")} ${btns ? "Create button" : "Create rule"}</button>`);
    $$("[data-tab]", body).forEach(x => x.onclick = () => { tab = x.dataset.tab; draw(); });
    $$("[data-en]", body).forEach(x => x.onclick = async () => { const r = d.rules.find(y => y.id === +x.dataset.en); await PATCH(`/store/kb/rules/${r.id}`, { enabled: !r.enabled }); draw(); });
    $$("[data-rdel]", body).forEach(x => x.onclick = () => confirmPop(x, "Delete rule?", "The rule will stop running. There is no undo.", "Delete", async () => { await DEL(`/store/kb/rules/${x.dataset.rdel}`); await reloadBoard(true); draw(); }));
    $$("[data-run]", body).forEach(x => x.onclick = async () => { try { const r = await POST(`/store/kb/rules/${x.dataset.run}/run`); toast(`Ran on ${r.cards} card${r.cards === 1 ? "" : "s"}`); await reloadBoard(true); draw(); } catch (e) { fail(e); } });
    $$("[data-log]", body).forEach(x => x.onclick = () => body.querySelector(`[data-logbox="${x.dataset.log}"]`).classList.toggle("hide"));
    $$("[data-bdel]", body).forEach(x => x.onclick = async () => { const key = tab; const arr = [...(b.prefs[key] || [])]; arr.splice(+x.dataset.bdel, 1); await PATCH(`/store/kb/boards/${b.id}`, { prefs: { [key]: arr } }); await reloadBoard(true); draw(); });
    body.querySelector("[data-new]").onclick = () => ruleBuilder(m, show, tab, preset && preset.trigger, () => { preset = null; draw(); });
  };
  await draw();
  if (preset && preset.trigger) ruleBuilder(m, show, "rules", preset.trigger, () => { preset = null; draw(); });
}
function actWords(a) {
  const b = S.board; const L = id => (b.lists.find(l => l.id === +id) || {}).title || "?"; const LB = id => { const l = b.labels.find(x => x.id === +id); return l ? (l.name || l.color) : "?"; };
  const P = id => (person(+id) || {}).name || "?"; const B = id => (S.boards.find(x => x.id === +id) || {}).title || "another board";
  switch (a.type) {
    case "move": return `move the card to "${L(a.list_id)}"`; case "move_top": return `move the card to the top of "${L(a.list_id)}"`;
    case "add_label": return `add the "${LB(a.label_id)}" label`; case "remove_label": return `remove the "${LB(a.label_id)}" label`;
    case "add_member": return `add ${P(a.user_id)}`; case "remove_member": return `remove ${P(a.user_id)}`;
    case "set_due": return `set due ${a.days} day${a.days == 1 ? "" : "s"} from now at ${a.time || "17:00"}`; case "comment": return `post comment "${a.text}"`;
    case "add_checklist": return `add checklist "${a.title}" (${(a.items || []).length} items)`; case "set_cover": return `set the ${a.color} cover`;
    case "notify": return `notify members "${a.text}"`; case "sort_list": return `sort "${L(a.list_id)}" by ${a.by}`;
    case "move_board": return `move the card to ${B(a.board_id)} / list ${a.list_title || ""}`; case "copy_board": return `copy the card to ${B(a.board_id)} / ${a.list_title || ""}`;
    case "mirror_board": return `mirror the card on ${B(a.board_id)} / ${a.list_title || ""}`;
    default: return (ACT[a.type] || a.type).replace(/…$/, "").toLowerCase();
  }
}
async function ruleBuilder(m, show, tab, presetTrigger, back) {
  const b = S.board;
  await refreshBoards();
  const isBtn = tab === "card_buttons" || tab === "board_buttons";
  let trig = presetTrigger ? { ...presetTrigger } : tab === "schedule" ? { type: "schedule", every: "day", time: "09:00", cards: "all" } : tab === "due" ? { type: "due_in", days: 1 } : { type: "card_moved" };
  let acts = [], name = "", blist = "";
  const listOpts = (v) => b.lists.map(l => `<option value="${l.id}" ${+v === l.id ? "selected" : ""}>${esc(l.title)}</option>`).join("");
  const labelOpts = v => b.labels.map(l => `<option value="${l.id}" ${+v === l.id ? "selected" : ""}>${esc(l.name || l.color)}</option>`).join("");
  const memberOpts = v => b.members.map(p => `<option value="${p.id}" ${+v === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("");
  const boardsOpts = v => S.boards.filter(x => !x.closed).map(x => `<option value="${x.id}" ${+v === x.id ? "selected" : ""}>${esc(x.title)}${x.id === b.id ? " (this board)" : ""}</option>`).join("");
  const otherLists = {};
  const draw = async () => {
    for (const a of acts) if (["move_board", "copy_board", "mirror_board"].includes(a.type) && a.board_id && !otherLists[a.board_id]) otherLists[a.board_id] = (await boardListsFor(+a.board_id)).lists;
    const trigHtml = isBtn ? `<label class="fl">Button name ${tip("Shown on the button. Card buttons appear on every card; board buttons in the board header.")}</label><input class="t" data-name value="${esc(name)}" placeholder="e.g. Start work">
        ${tab === "board_buttons" ? `<label class="fl">Run on cards in ${tip("The button runs its actions on every card in this list (or the whole board).")}</label><select class="t" data-blist><option value="">every list</option>${listOpts(blist)}</select>` : ""}`
      : `<div class="rb-step"><b>When… ${tip("What starts the rule. Scheduled rules run at a set time; due-date rules run a set number of days before cards are due.")}</b><select class="t" data-tt>${Object.entries(TRIG).filter(([k]) => tab === "schedule" ? k === "schedule" : tab === "due" ? k === "due_in" : !["schedule", "due_in"].includes(k)).map(([k, v]) => `<option value="${k}" ${trig.type === k ? "selected" : ""}>${v}</option>`).join("")}</select>
        ${["card_added", "card_moved"].includes(trig.type) ? `<select class="t" data-tl>${listOpts(trig.list_id)}</select>` : ""}
        ${trig.type === "label_added" ? `<select class="t" data-tlab><option value="">any label</option>${labelOpts(trig.label_id)}</select>` : ""}
        ${trig.type === "member_added" ? `<select class="t" data-tmem><option value="">anyone</option>${memberOpts(trig.user_id)}</select>` : ""}
        ${trig.type === "schedule" ? `<div style="display:flex;gap:6px"><select class="t" data-ev>${[["day", "Every day"], ["weekday", "Every working day (Mon-Fri)"], ["week", "Every week on"], ["month", "Every month on day"]].map(([k, v]) => `<option value="${k}" ${trig.every === k ? "selected" : ""}>${v}</option>`).join("")}</select>
            ${trig.every === "week" ? `<select class="t" data-wd>${["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((d, i) => `<option value="${i}" ${+(trig.weekday || 0) === i ? "selected" : ""}>${d}</option>`).join("")}</select>` : ""}
            ${trig.every === "month" ? `<input class="t" type="number" min="1" max="28" data-md value="${trig.day || 1}" style="width:70px">` : ""}</div>
            <div style="display:flex;gap:6px"><span style="align-self:center">at</span><input class="t" type="time" data-tm value="${trig.time || "09:00"}"></div>
            <select class="t" data-scl><option value="">for cards in every list</option>${listOpts(trig.list_id)}</select>
            <select class="t" data-sc>${[["all", "all cards"], ["incomplete", "cards not complete"], ["complete", "completed cards"], ["overdue", "overdue cards"], ["none", "no cards (board actions only)"]].map(([k, v]) => `<option value="${k}" ${(trig.cards || "all") === k ? "selected" : ""}>${v}</option>`).join("")}</select>` : ""}
        ${trig.type === "due_in" ? `<div style="display:flex;gap:6px;align-items:center"><input class="t" type="number" data-dd value="${trig.days ?? 1}" style="width:80px"><span>days before the due date (use 0 for the day, -1 for a day after)</span></div>` : ""}</div>`;
    const actHtml = acts.map((a, i) => `<div class="rb-step"><div style="display:flex;justify-content:space-between;align-items:center"><b>${i ? "And then…" : "Then…"} ${esc((ACT[a.type] || "").replace(/…$/, ""))}</b><button class="x" data-arm="${i}">${ic("x", "s14")}</button></div>
        ${["move", "move_top"].includes(a.type) ? `<select class="t" data-af="list_id" data-ai="${i}">${listOpts(a.list_id)}</select>` : ""}
        ${a.type === "sort_list" ? `<select class="t" data-af="list_id" data-ai="${i}">${listOpts(a.list_id)}</select><select class="t" data-af="by" data-ai="${i}">${[["due", "due date"], ["name", "name"], ["created_new", "newest first"], ["created_old", "oldest first"], ["votes", "votes"]].map(([k, v]) => `<option value="${k}" ${a.by === k ? "selected" : ""}>by ${v}</option>`).join("")}</select>` : ""}
        ${["add_label", "remove_label"].includes(a.type) ? `<select class="t" data-af="label_id" data-ai="${i}">${labelOpts(a.label_id)}</select>` : ""}
        ${["add_member", "remove_member"].includes(a.type) ? `<select class="t" data-af="user_id" data-ai="${i}">${memberOpts(a.user_id)}</select>` : ""}
        ${a.type === "set_due" ? `<div style="display:flex;gap:6px"><input class="t" type="number" data-af="days" data-ai="${i}" value="${a.days ?? 1}" style="width:80px"><span style="align-self:center">days, at</span><input class="t" type="time" data-af="time" data-ai="${i}" value="${a.time || "17:00"}"></div>` : ""}
        ${["comment", "notify"].includes(a.type) ? `<input class="t" data-af="text" data-ai="${i}" value="${esc(a.text || "")}" placeholder="${a.type === "notify" ? "Message" : "Comment"}">` : ""}
        ${a.type === "set_cover" ? `<select class="t" data-af="color" data-ai="${i}">${COVER_COLORS.map(c => `<option ${a.color === c ? "selected" : ""}>${c}</option>`).join("")}</select>` : ""}
        ${a.type === "add_checklist" ? `<input class="t" data-af="title" data-ai="${i}" value="${esc(a.title || "Checklist")}"><textarea class="t" data-af="items" data-ai="${i}" rows="3" placeholder="One item per line">${esc((a.items || []).join("\n"))}</textarea>` : ""}
        ${["move_board", "copy_board", "mirror_board"].includes(a.type) ? `<select class="t" data-af="board_id" data-ai="${i}"><option value="">Choose a board…</option>${boardsOpts(a.board_id)}</select>${a.board_id ? `<select class="t" data-af="list_id" data-ai="${i}"><option value="">Choose a list…</option>${(otherLists[a.board_id] || []).map(l => `<option value="${l.id}" ${+a.list_id === l.id ? "selected" : ""}>${esc(l.title)}</option>`).join("")}</select><select class="t" data-af="where" data-ai="${i}"><option value="bottom">at the bottom</option><option value="top" ${a.where === "top" ? "selected" : ""}>at the top</option></select>` : ""}
          ${a.type === "mirror_board" ? '<p class="muted" style="margin:6px 0 0">The mirror is the same card: edit it on either board and both update.</p>' : ""}` : ""}</div>`).join("");
    const body = show(isBtn ? "Create button" : "Create rule", `${trigHtml}${actHtml}
      <div class="rb-step"><b>${acts.length ? "Add another action" : "Then…"}</b><select class="t" data-add><option value="">Choose an action…</option>${Object.entries(ACT).filter(([k]) => tab !== "card_buttons" || !["sort_list"].includes(k)).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
      <div style="display:flex;gap:8px;margin-top:12px"><button class="b pri" data-save>Save</button><button class="b sub" data-cancel>Cancel</button></div>`);
    m.querySelector("[data-back]").onclick = back;
    const sel = (s, fn) => { const e = body.querySelector(s); if (e) e.onchange = ev => { fn(ev.target.value); draw(); }; };
    sel("[data-tt]", v => { trig = { type: v }; if (v === "schedule") Object.assign(trig, { every: "day", time: "09:00", cards: "all" }); if (v === "due_in") trig.days = 1; if (["card_added", "card_moved"].includes(v)) trig.list_id = b.lists[0] && b.lists[0].id; });
    sel("[data-tl]", v => trig.list_id = +v); sel("[data-tlab]", v => trig.label_id = v ? +v : undefined); sel("[data-tmem]", v => trig.user_id = v ? +v : undefined);
    sel("[data-ev]", v => trig.every = v); sel("[data-wd]", v => trig.weekday = +v); sel("[data-md]", v => trig.day = +v); sel("[data-tm]", v => trig.time = v);
    sel("[data-scl]", v => trig.list_id = v ? +v : undefined); sel("[data-sc]", v => trig.cards = v); sel("[data-dd]", v => trig.days = +v);
    const nm = body.querySelector("[data-name]"); if (nm) nm.oninput = () => name = nm.value;
    sel("[data-blist]", v => blist = v);
    $$("[data-af]", body).forEach(e => e.onchange = () => {
      const a = acts[+e.dataset.ai], f = e.dataset.af;
      a[f] = f === "items" ? e.value.split("\n").map(x => x.trim()).filter(Boolean) : ["list_id", "label_id", "user_id", "board_id", "days"].includes(f) ? (e.value === "" ? "" : +e.value) : e.value;
      if (f === "board_id") { a.list_id = ""; }
      if (f === "list_id" && ["move_board", "copy_board", "mirror_board"].includes(a.type)) a.list_title = (e.options[e.selectedIndex] || {}).text || "";
      draw();
    });
    $$("[data-arm]", body).forEach(e => e.onclick = () => { acts.splice(+e.dataset.arm, 1); draw(); });
    body.querySelector("[data-add]").onchange = e => {
      const t = e.target.value; if (!t) return;
      const a = { type: t };
      if (["move", "move_top", "sort_list"].includes(t)) a.list_id = b.lists[0] && b.lists[0].id;
      if (t === "sort_list") a.by = "due";
      if (["add_label", "remove_label"].includes(t)) a.label_id = b.labels[0] && b.labels[0].id;
      if (["add_member", "remove_member"].includes(t)) a.user_id = b.members[0] && b.members[0].id;
      if (t === "set_due") { a.days = 1; a.time = "17:00"; } if (t === "set_cover") a.color = "green"; if (t === "add_checklist") { a.title = "Checklist"; a.items = []; }
      acts.push(a); draw();
    };
    body.querySelector("[data-cancel]").onclick = back;
    body.querySelector("[data-save]").onclick = async () => {
      if (!acts.length) { toast("Add at least one action", { err: true }); return; }
      try {
        if (isBtn) {
          if (!name.trim()) { toast("Give the button a name", { err: true }); return; }
          const arr = [...(b.prefs[tab] || []), { name: name.trim(), actions: acts, ...(blist ? { list_id: +blist } : {}) }];
          await PATCH(`/store/kb/boards/${b.id}`, { prefs: { [tab]: arr } });
        } else await POST(`/store/kb/boards/${b.id}/rules`, { trigger: trig, actions: acts });
        await reloadBoard(true); toast(isBtn ? "Button saved" : "Rule saved - it is on"); back();
      } catch (e) { fail(e); }
    };
  };
  draw();
}

/* Estimation > Trello - the card back (opened card): title, labels, members, dates, description, checklists,
   attachments, custom fields, power-ups, comments and activity. */
"use strict";
S.full = null;
let SHOW_DETAILS = false;
try { SHOW_DETAILS = localStorage.getItem("kb_details") === "1"; } catch (e) {}

async function openCardModal(cid) {
  S.openCard = cid;
  let ov = $("#cm-ov");
  if (!ov) {
    ov = h(`<div class="ov" id="cm-ov"><div class="cm"><div class="empty"><div class="spin dk" style="margin:40px auto"></div></div></div></div>`);
    ov.addEventListener("mousedown", e => { if (e.target === ov) go(`#/b/${S.board.id}`); });
    document.body.appendChild(ov);
  }
  await loadFullCard(cid);
}
function closeCardModal(fromRoute) {
  const ov = $("#cm-ov"); if (ov) ov.remove();
  S.openCard = null; S.full = null;
  if (S.board) document.title = `${S.board.title} | Trello`;
}
async function loadFullCard(cid, keep, quiet) {
  try {
    const c = await GET(`/store/kb/cards/${cid}`);
    if (c.board_id !== (S.board && S.board.id)) { if (!quiet) { go(`#/b/${c.board_id}/c/${cid}`); } return; }
    S.full = c;
    if (S.cards[cid]) Object.assign(S.cards[cid], { labels: c.labels, members: c.members, due: c.due, start: c.start, due_complete: c.due_complete, title: c.title });
    if (!quiet && S.openCard === cid) renderCardModal();
  } catch (e) { fail(e); if (!quiet) go(`#/b/${S.board.id}`); }
}

// ---------- markdown (Trello's description and comments) ----------
function md(src) {
  let s = esc(src || "");
  const blocks = [];
  s = s.replace(/```([\s\S]*?)```/g, (_, c) => { blocks.push(`<pre><code>${c.replace(/^\n/, "")}</code></pre>`); return `\u0000${blocks.length - 1}\u0000`; });
  const lines = s.split("\n"), out = []; let list = null;
  const inline = t => t.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>")
    .replace(/~~([^~]+)~~/g, "<s>$1</s>").replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
    .replace(/(^|\s)@([\w.\-]+)/g, '$1<span class="mention">@$2</span>');
  for (const ln of lines) {
    let m;
    if ((m = ln.match(/^(\s*)[-*] \[( |x)\] (.*)/))) { if (list !== "ul") { if (list) out.push(`</${list}>`); out.push("<ul style='list-style:none;padding-left:4px'>"); list = "ul"; } out.push(`<li>${m[2] === "x" ? "☑" : "☐"} ${inline(m[3])}</li>`); continue; }
    if ((m = ln.match(/^\s*[-*] (.*)/))) { if (list !== "ul") { if (list) out.push(`</${list}>`); out.push("<ul>"); list = "ul"; } out.push(`<li>${inline(m[1])}</li>`); continue; }
    if ((m = ln.match(/^\s*\d+[.)] (.*)/))) { if (list !== "ol") { if (list) out.push(`</${list}>`); out.push("<ol>"); list = "ol"; } out.push(`<li>${inline(m[1])}</li>`); continue; }
    if (list) { out.push(`</${list}>`); list = null; }
    if ((m = ln.match(/^(#{1,3}) (.*)/))) { out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`); continue; }
    if (/^(-{3,}|\*{3,})$/.test(ln.trim())) { out.push("<hr>"); continue; }
    if ((m = ln.match(/^&gt; ?(.*)/))) { out.push(`<blockquote>${inline(m[1])}</blockquote>`); continue; }
    if (!ln.trim()) { out.push(""); continue; }
    out.push(`<p>${inline(ln)}</p>`);
  }
  if (list) out.push(`</${list}>`);
  return out.join("\n").replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[+i]);
}
function editorHtml(id, val, ph) {
  return `<div class="edtools" data-for="${id}"><button data-md="**" title="Bold">B</button><button data-md="*" title="Italic"><i>I</i></button><button data-md="~~" title="Strikethrough"><s>S</s></button>
    <button data-mdl="# " title="Heading">H</button><button data-mdl="- " title="Bulleted list">•</button><button data-mdl="1. " title="Numbered list">1.</button><button data-mdl="- [ ] " title="Checklist">☐</button>
    <button data-mdl="> " title="Quote">❝</button><button data-md="\`" title="Code">&lt;/&gt;</button><button data-link title="Link">${ic("link", "s14")}</button><button data-at title="Mention">@</button></div>
    <textarea class="t" id="${id}" placeholder="${esc(ph || "")}">${esc(val || "")}</textarea>`;
}
function wireEditor(root, id) {
  const ta = root.querySelector("#" + id); if (!ta) return;
  $$(`.edtools[data-for="${id}"] button`, root).forEach(b => b.onmousedown = e => {
    e.preventDefault(); const s = ta.selectionStart, en = ta.selectionEnd, v = ta.value, sel = v.slice(s, en);
    if (b.dataset.md) { const m = b.dataset.md; ta.value = v.slice(0, s) + m + (sel || "text") + m + v.slice(en); ta.setSelectionRange(s + m.length, s + m.length + (sel || "text").length); }
    else if (b.dataset.mdl) { const ls = v.lastIndexOf("\n", s - 1) + 1; ta.value = v.slice(0, ls) + b.dataset.mdl + v.slice(ls); ta.setSelectionRange(s + b.dataset.mdl.length, en + b.dataset.mdl.length); }
    else if (b.hasAttribute("data-link")) { const u = prompt("Link address (https://...)"); if (u) { ta.value = v.slice(0, s) + `[${sel || "link"}](${u})` + v.slice(en); } }
    else if (b.hasAttribute("data-at")) { ta.value = v.slice(0, s) + "@" + v.slice(en); ta.setSelectionRange(s + 1, s + 1); mentionPop(ta); }
    ta.focus();
  });
  ta.addEventListener("input", () => { const v = ta.value.slice(0, ta.selectionStart); if (/(^|\s)@[\w.\-]*$/.test(v)) mentionPop(ta); else if ($(".pop.mention")) closePops(); });
  ta.addEventListener("blur", () => setTimeout(() => { if ($(".pop.mention") && !$(".pop.mention:hover")) closePops(); }, 150));
}
function mentionPop(ta) {
  const v = ta.value.slice(0, ta.selectionStart), q = (v.match(/@([\w.\-]*)$/) || [, ""])[1].toLowerCase();
  const ppl = S.board.people.filter(p => !q || p.username.toLowerCase().startsWith(q) || p.name.toLowerCase().includes(q)).slice(0, 8);
  if (!ppl.length) return;
  const p = pop(ta, "Mention", ppl.map(x => `<div class="memrow" data-u="${esc(x.username)}">${av(x)}<div class="nm">${esc(x.name)}<small>@${esc(x.username)}</small></div></div>`).join(""), { nofocus: true, above: true, cls: "mention" });
  p.setAttribute("data-keep-pop", "1");
  $$("[data-u]", p).forEach(r => r.onmousedown = e => { e.preventDefault(); const s = ta.selectionStart; const before = ta.value.slice(0, s).replace(/@([\w.\-]*)$/, "@" + r.dataset.u + " "); ta.value = before + ta.value.slice(s); ta.setSelectionRange(before.length, before.length); closePops(); ta.focus(); });
}

// ---------- the card back ----------
function renderCardModal() {
  const c = S.full, ov = $("#cm-ov"); if (!c || !ov) return;
  const ro = c.role === "observer";
  const sc = ov.scrollTop;
  const labels = c.labels.map(id => S.board.labels.find(l => l.id === id)).filter(Boolean);
  const mem = c.members.map(person).filter(Boolean);
  const ds = dueState(c);
  const cov = c.cover || {};
  const coverUrl = cov.att ? (c.attachments.find(a => a.id === cov.att) || {}).url : "";
  document.title = `${c.title} on ${S.board.title} | Trello`;
  const fieldsShown = S.board.fields.length && pu("fields");
  const prio = c.priority ? PRIORITIES.find(p => p[0] === c.priority) : null;
  const checklists = c.checklists.map(cl => {
    const done = cl.items.filter(i => i.done).length, n = cl.items.length, pc = n ? Math.round(done * 100 / n) : 0;
    return `<div class="sec" data-cl="${cl.id}"><div class="sec-h"><span class="ic">${ic("checksq", "s20")}</span><h3 data-clt>${esc(cl.title)}</h3>
        ${done ? `<button class="b" data-hide>${cl.hide_done ? `Show checked items (${done})` : "Hide checked items"}</button>` : ""}${ro ? "" : `<button class="b" data-cldel>Delete</button>`}</div>
      <div class="prog ${pc === 100 ? "full" : ""}"><span class="pc">${pc}%</span><span class="bar"><i style="width:${pc}%"></i></span></div>
      <div data-items>${cl.items.filter(i => !(cl.hide_done && i.done)).map(i => `<div class="citem ${i.done ? "done" : ""}" data-i="${i.id}"><input type="checkbox" ${i.done ? "checked" : ""} ${ro ? "disabled" : ""}><span class="ct" data-it>${md(i.text).replace(/^<p>|<\/p>$/g, "")}</span>
          <span class="ci-meta">${i.due ? `<span class="bdg">${ic("clock", "s12")} ${fmtDue(i.due, false)}</span>` : ""}${i.member && person(i.member) ? av(person(i.member)) : ""}</span>
          ${ro ? "" : `<span class="ci-tools"><button data-iu title="Assign">${ic("user", "s14")}</button><button data-id title="Due date">${ic("clock", "s14")}</button><button data-im title="Item actions">${ic("more", "s14")}</button></span>`}</div>`).join("")}</div>
      ${ro ? "" : `<div class="sec-b" style="margin-left:28px"><button class="b" data-additem>Add an item</button></div>`}</div>`;
  }).join("");
  const atts = c.attachments.length ? `<div class="sec"><div class="sec-h"><span class="ic">${ic("clip", "s20")}</span><h3>Attachments</h3>${ro ? "" : `<button class="b" data-k="attach">Add</button>`}</div><div class="sec-b">
      ${c.attachments.map(a => `<div class="att" data-a="${a.id}"><a class="th" href="${esc(a.url)}" target="_blank" rel="noopener" style="${a.thumb ? `background-image:url('${esc(a.thumb)}')` : ""}">${a.thumb ? "" : a.link ? ic("link", "s24") : esc((a.name.split(".").pop() || "file").slice(0, 4))}</a>
        <div class="inf"><div class="nm">${esc(a.name)}</div><div class="ln">Added ${ago(a.at)}${a.by ? " by " + esc(a.by) : ""}${cov.att === a.id ? ` <span class="cv-tag">${ic("img", "s12")} Cover</span>` : ""}</div>
        <div class="ln"><a href="${esc(a.url)}" target="_blank" rel="noopener">${a.link ? "Open" : "Download"}</a>${ro ? "" : `${a.image && !a.link ? `<a data-cov>${cov.att === a.id ? "Remove cover" : "Make cover"}</a>` : ""}<a data-ren>Edit</a><a data-adel>Delete</a>`}<a data-acopy>Copy link</a></div></div></div>`).join("")}</div></div>` : "";
  const timeSec = pu("time") && (c.estimate || c.time_entries.length) ? `<div class="sec"><div class="sec-h"><span class="ic">${ic("timer", "s20")}</span><h3>Time tracking</h3>${ro ? "" : `<button class="b" data-k="time">Log time</button>`}</div><div class="sec-b">
      <div style="display:flex;justify-content:space-between;font-size:13px"><span><b>${+(c.logged || 0).toFixed(2)}h</b> logged</span><span>${c.estimate ? `${Math.max(0, +(c.estimate - (c.logged || 0)).toFixed(2))}h remaining of ${c.estimate}h` : "No estimate"}</span></div>
      <div class="tbar"><i class="${c.estimate && c.logged > c.estimate ? "over" : ""}" style="width:${c.estimate ? Math.min(100, (c.logged || 0) * 100 / c.estimate) : 100}%"></i></div>
      ${c.time_entries.map(t => `<div class="time-row"><b style="width:52px">${t.hours}h</b><span style="flex:1">${esc(t.note || "")}<span class="muted"> · ${esc(t.who)} · ${fmtDue(t.day, false)}</span></span>${t.mine ? `<button class="x" data-tdel="${t.id}" title="Remove">${ic("x", "s14")}</button>` : ""}</div>`).join("")}</div></div>` : "";
  const linked = c.linked && c.linked.length ? `<div class="sec"><div class="sec-h"><span class="ic">${ic("link", "s20")}</span><h3>Linked cards</h3>${ro ? "" : `<button class="b" data-k="link">Add</button>`}</div><div class="sec-b mini-list">
      ${c.linked.map(l => `<div class="r" data-goc="${l.id}" data-gob="${l.board_id}">${ic(l.due_complete ? "checksq" : "board", "s14")}<div style="flex:1;min-width:0"><b style="font-weight:500">${esc(l.title)}</b><div class="muted">#${l.no} · ${esc(l.board)}: ${esc(l.list)}${l.closed ? " · archived" : ""}</div></div>${ro ? "" : `<button class="x" data-unlink="${l.id}">${ic("x", "s14")}</button>`}</div>`).join("")}</div></div>` : "";
  const mirrors = c.mirrors && c.mirrors.length ? `<div class="cm-banner blue" style="border-radius:0">${ic("mirror")} This card is mirrored on ${c.mirrors.length} other board${c.mirrors.length > 1 ? "s" : ""} - changes show everywhere.</div>` : "";
  const repeat = c.repeat ? `<div class="sec"><div class="sec-h"><span class="ic">${ic("repeat", "s20")}</span><h3>Repeats</h3><button class="b" data-k="repeat">Edit</button></div><div class="sec-b muted" style="font-size:13px">Every ${c.repeat.nth > 1 ? c.repeat.nth + " " : ""}${c.repeat.every}${c.repeat.nth > 1 ? "s" : ""} at ${c.repeat.time} · next copy ${fmtDue(c.repeat.next_on, false)} · ${c.repeat.made} made so far</div></div>` : "";

  const feed = [...c.comments.map(m => ({ t: m.at, html: `<div class="fe" data-m="${m.id}"><span class="av lg" style="background:${avColor(m.user_id || m.who.length)}">${esc(m.initials)}</span><div class="bd"><span class="who">${esc(m.who)}</span><a class="when" href="#/b/${S.board.id}/c/${c.id}">${ago(m.at)}${m.edited ? " (edited)" : ""}</a>
      <div class="bubble md">${md(m.text)}</div><div class="tools">${m.mine ? `<a data-cedit>Edit</a><a data-cdel>Delete</a>` : ""}</div></div></div>` })),
    ...(SHOW_DETAILS ? c.activity.map(a => ({ t: a.at, html: `<div class="fe act"><span class="av lg" style="background:${avColor(a.who.length)}">${esc(a.initials)}</span><div class="bd"><div class="line"><b>${esc(a.who)}</b> ${actText(a, true)}</div><a class="when">${ago(a.at)}</a></div></div>` })) : [])]
    .sort((x, y) => (y.t || "").localeCompare(x.t || "")).map(x => x.html).join("");

  const btn = (k, i, l) => `<button class="b" data-k="${k}">${ic(i)} ${l}</button>`;
  ov.querySelector(".cm").innerHTML = `
    ${c.closed ? `<div class="cm-banner">${ic("archive")} This card is archived.</div>` : ""}${c.is_template ? `<div class="cm-banner blue">${ic("tpl")} This is a template card.</div>` : ""}${mirrors}
    ${coverUrl || cov.color ? `<div class="cm-cover ${coverUrl ? "tall" : ""}" style="${coverUrl ? `background-image:url('${esc(coverUrl)}');background-color:${(c.attachments.find(a => a.id === cov.att) || {}).edge || "#DCDFE4"}` : `background:${labColor(cov.color)}`}">${ro ? "" : `<button class="b" data-k="cover">${ic("img")} Cover</button>`}</div>` : ""}
    <div class="cm-top"><button class="lpill" data-k="move" title="Move card">${esc(c.list_title)} ${ic("down", "s14")}</button>${S.board.prefs.card_numbers ? `<span class="muted" style="margin-left:6px">#${c.no}</span>` : ""}<span style="flex:1"></span>
      ${ro || coverUrl || cov.color ? "" : `<button class="x" data-k="cover" title="Cover">${ic("img")}</button>`}
      <button class="x" data-k="watch" title="${c.watching ? "Stop watching" : "Watch"}" style="${c.watching ? "color:var(--brand)" : ""}">${ic("eye")}</button>
      <button class="x" data-k="more" title="Actions">${ic("more")}</button><button class="x" data-close title="Close">${ic("x")}</button></div>
    <div class="cm-body"><div class="cm-main">
      <div class="ttl"><button class="done-c ${c.due_complete ? "on" : ""}" data-k="done" title="${c.due_complete ? "Mark incomplete" : "Mark complete"}" ${ro ? "disabled" : ""}>${c.due_complete ? ic("check", "s14") : ""}</button><textarea data-title rows="1" ${ro ? "readonly" : ""}>${esc(c.title)}</textarea></div>
      ${ro ? "" : `<div class="acts">${btn("add", "plus", "Add")}${btn("labels", "tag", "Labels")}${btn("dates", "clock", "Dates")}${btn("checklist", "checksq", "Checklist")}${btn("members", "user", "Members")}${btn("attach", "clip", "Attachment")}
        ${(S.board.prefs.card_buttons || []).map((x, i) => `<button class="b" data-cbtn="${i}" style="background:#E9F2FF;color:#0055CC;border-color:#CCE0FF">${ic("btn")} ${esc(x.name)}</button>`).join("")}</div>`}
      <div class="meta">
        ${mem.length ? `<div><h4>Members</h4><div class="row">${mem.map(m => av(m, "lg").replace('class="av', `data-mem="${m.id}" class="av`)).join("")}${ro ? "" : `<button class="b add-sq" data-k="members">${ic("plus")}</button>`}</div></div>` : ""}
        ${labels.length ? `<div><h4>Labels</h4><div class="row">${labels.map(l => labHtml(l).replace('class="lab', 'data-k="labels" class="lab')).join("")}${ro ? "" : `<button class="b add-sq" data-k="labels">${ic("plus")}</button>`}</div></div>` : ""}
        <div><h4>Notifications</h4><div class="row"><button class="b" data-k="watch">${ic("eye")} ${c.watching ? "Watching" : "Watch"}${c.watching ? ` <span style="background:#1F845A;color:#fff;border-radius:3px;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center">${ic("check", "s12")}</span>` : ""}</button></div></div>
        ${c.due || c.start ? `<div><h4>${c.start && c.due ? "Dates" : c.due ? "Due date" : "Start date"}</h4><div class="row"><span class="duebox" data-k="dates">${c.start ? fmtDue(c.start, false) + (c.due ? " - " : "") : ""}${c.due ? fmtDue(c.due) : ""} ${ds === "done" ? '<span class="st done">Complete</span>' : ds === "soon" ? '<span class="st soon">Due soon</span>' : ds === "over" || ds === "past" ? '<span class="st over">Overdue</span>' : ""} ${ic("down", "s14")}</span></div></div>` : ""}
        ${pu("priority") && prio ? `<div><h4>Priority</h4><div class="row"><span class="duebox" data-k="priority"><span class="bdg pr-${prio[0]}" style="margin:0;padding:0">${ic(prio[2])}</span>${prio[1]}</span></div></div>` : ""}
        ${pu("priority") && (c.points != null || c.estimate != null) ? `<div><h4>Story points</h4><div class="row"><span class="duebox" data-k="points">${c.points != null ? c.points + " pts" : "-"}${c.estimate != null ? ` · ${c.estimate}h est.` : ""}</span></div></div>` : ""}
        ${pu("voting") && c.votes.length ? `<div><h4>Votes</h4><div class="row"><button class="b ${c.votes.includes(S.me.id) ? "on" : ""}" data-k="vote">${ic("thumb")} ${c.votes.length}</button>${c.votes.map(person).filter(Boolean).slice(0, 6).map(p => av(p)).join("")}</div></div>` : ""}
        ${c.location ? `<div><h4>Location</h4><div class="row"><a class="duebox" href="https://maps.google.com/?q=${encodeURIComponent(c.location)}" target="_blank" rel="noopener">${ic("pin")} ${esc(c.location)}</a></div></div>` : ""}
      </div>
      ${fieldsShown ? `<div class="sec"><div class="sec-h"><span class="ic">${ic("field", "s20")}</span><h3>Custom Fields</h3></div><div class="sec-b" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:4px 12px" data-fields>${S.board.fields.map(f => `<div><label class="fl" style="margin-top:4px">${esc(f.name)}</label>${ro ? `<div>${esc(String((c.fields || {})[String(f.id)] ?? "-"))}</div>` : fieldInput(f, (c.fields || {})[String(f.id)])}</div>`).join("")}</div></div>` : ""}
      <div class="sec"><div class="sec-h"><span class="ic">${ic("desc", "s20")}</span><h3>Description</h3>${c.desc && !ro ? `<button class="b" data-dedit>Edit</button>` : ""}</div>
        <div class="sec-b" data-desc>${c.desc ? `<div class="desc-view md">${md(c.desc)}</div>` : ro ? '<div class="muted">No description.</div>' : `<div class="desc-empty" data-dedit>Add a more detailed description…</div>`}</div></div>
      ${repeat}${linked}${atts}${timeSec}${checklists}
    </div>
    <aside class="cm-side">
      <div class="side-h"><h3>${ic("cmt")} Comments and activity</h3><button class="b" data-details>${SHOW_DETAILS ? "Hide details" : "Show details"}</button></div>
      <div class="cmt-new">${av(S.me, "lg")}<div class="box" data-cbox><button class="fake" data-cfake>Write a comment…</button></div></div>
      <div class="feed">${feed || '<p class="muted" style="text-align:center">No comments yet.</p>'}</div>
    </aside></div>`;
  ov.scrollTop = sc;
  wireCardModal(ov.querySelector(".cm"), c);
}
function actText(a, onCard) {
  const d = a.data || {}, card = onCard ? "this card" : `<a data-goc="${a.card_id}">${esc(d.title || "a card")}</a>`;
  const T = {
    card_added: `added ${card}${d.list ? ` to ${esc(d.list)}` : ""}${d.from_item ? ` (from a checklist item on ${esc(d.from_item)})` : ""}`,
    card_moved: `moved ${card} from ${esc(d.frm)} to ${esc(d.to)}`, card_moved_board: `moved ${card} ${d.to ? "to the board " + esc(d.to) : "from " + esc(d.frm || "another board")}`,
    card_renamed: `renamed ${onCard ? "this card" : esc(d.old)} to ${esc(d.new)}`, card_desc: `changed the description of ${card}`,
    card_due: d.due ? `set ${card} to be due ${fmtDue(d.due)}` : `removed the due date from ${card}`,
    card_complete: `marked ${card} as complete`, card_incomplete: `marked ${card} as incomplete`,
    card_archived: `archived ${card}`, card_restored: `sent ${card} to the board`, card_deleted: `deleted card #${d.no} ${esc(d.title)}`,
    card_copied: `copied ${card} from ${esc(d.source)}${d.frm ? " on " + esc(d.frm) : ""}`, card_mirrored: `mirrored ${card} from ${esc(d.frm || "")}`,
    card_repeated: `made ${card} (repeat of ${esc(d.source)})`,
    card_member_added: `added ${esc(d.who)} to ${card}`, card_member_removed: `removed ${esc(d.who)} from ${card}`,
    checklist_added: `added ${esc(d.title)} to ${card}`, checklist_removed: `removed ${esc(d.title)} from ${card}`,
    item_done: `completed ${esc(d.text)} on ${card}`, item_undone: `marked ${esc(d.text)} incomplete on ${card}`,
    attached: `attached ${esc(d.name)} to ${card}`, detached: `deleted the ${esc(d.name)} attachment from ${card}`,
    time_logged: `logged ${d.hours}h on ${card}${d.note ? ": " + esc(d.note) : ""}`, repeat_set: `set ${card} to repeat every ${esc(d.every)}`,
    rule: `ran a rule on ${card}: ${esc(d.title || "")}`, button: `pressed the ${esc(d.name)} button on ${card}`,
    board_button: `pressed the board button ${esc(d.name)} (${d.n} cards)`,
    list_added: `added list ${esc(d.title)}`, list_renamed: `renamed list ${esc(d.old)} to ${esc(d.new)}`, list_archived: `archived list ${esc(d.title)}`, list_restored: `restored list ${esc(d.title)}`,
    list_copied: `copied list ${esc(d.title)}`, list_moved_all: `moved all cards from ${esc(d.frm)} to ${esc(d.to)}`, list_archived_cards: `archived ${d.n} cards in ${esc(d.title)}`,
    board_created: `created this board`, board_renamed: `renamed this board to ${esc(d.new)}`, board_copied: `copied this board from ${esc(d.source)}`,
    board_imported: `imported this board from Trello (${d.cards} cards)`, board_closed: "closed this board", board_reopened: "reopened this board",
    member_added: `added ${esc(d.who)} to this board`, member_removed: `removed ${esc(d.who)} from this board`, member_left: `left this board`,
    comment: `on ${card}: <span class="md">${esc((d.text || "").slice(0, 200))}</span>`,
  };
  return T[a.kind] || esc(a.kind.replace(/_/g, " "));
}
function wireCardModal(m, c) {
  const cid = c.id;
  const k = (sel, fn) => $$(`[data-k="${sel}"]`, m).forEach(b => b.onclick = e => { e.stopPropagation(); fn(e.currentTarget); });
  m.querySelector("[data-close]").onclick = () => go(`#/b/${S.board.id}`);
  const ta = m.querySelector("[data-title]");
  const fit = () => { ta.style.height = "36px"; ta.style.height = ta.scrollHeight + "px"; }; fit(); ta.oninput = fit;
  ta.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); ta.blur(); } if (e.key === "Escape") { ta.value = c.title; ta.blur(); } };
  ta.onblur = () => { const v = ta.value.trim(); if (v && v !== c.title) saveCard(cid, { title: v }); else ta.value = c.title; };
  k("done", () => saveCard(cid, { due_complete: !c.due_complete }));
  k("labels", b => labelsPop(b, cid)); k("members", b => membersPop(b, cid)); k("dates", b => datesPop(b, cid));
  k("checklist", b => checklistPop(b, cid)); k("attach", b => attachPop(b, cid)); k("cover", b => coverPop(b, cid));
  k("move", b => moveCopyPop(b, cid, "move")); k("watch", () => saveCard(cid, { watch: !c.watching }));
  k("priority", b => priorityPop(b, cid)); k("points", b => pointsPop(b, cid)); k("time", b => timePop(b, cid));
  k("vote", () => saveCard(cid, { vote: !c.votes.includes(S.me.id) })); k("repeat", b => repeatPop(b, cid)); k("link", b => linkCardPop(b, cid));
  k("add", b => addMenuPop(b, cid)); k("more", b => cardMorePop(b, cid));
  $$("[data-mem]", m).forEach(a => a.onclick = e => memberCardPop(e.currentTarget, +a.dataset.mem));
  $$("[data-cbtn]", m).forEach(b => b.onclick = async () => { try { await POST(`/store/kb/cards/${cid}/button`, { index: +b.dataset.cbtn }); toast("Done"); await reloadBoard(true); loadFullCard(cid, true); } catch (e) { fail(e); } });
  const fl = m.querySelector("[data-fields]"); if (fl) wireFieldInputs(fl, cid);
  // description
  const editDesc = () => {
    const box = m.querySelector("[data-desc]");
    box.innerHTML = editorHtml("desc-ed", c.desc, "Add a more detailed description… Use @ to mention someone.") + `<div style="display:flex;gap:8px;margin-top:8px"><button class="b pri" data-dsave>Save</button><button class="b sub" data-dcancel>Cancel</button><span class="muted" style="margin-left:auto;align-self:center">Formatting help: **bold**, *italic*, - list, # heading</span></div>`;
    wireEditor(box, "desc-ed"); const t = box.querySelector("#desc-ed"); t.focus(); t.setSelectionRange(t.value.length, t.value.length);
    box.querySelector("[data-dsave]").onclick = () => saveCard(cid, { desc: t.value });
    box.querySelector("[data-dcancel]").onclick = () => renderCardModal();
    t.onkeydown = e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") saveCard(cid, { desc: t.value }); if (e.key === "Escape") renderCardModal(); };
  };
  if (c.role !== "observer") { $$("[data-dedit]", m).forEach(b => b.onclick = editDesc); const dv = m.querySelector(".desc-view"); if (dv) dv.onclick = e => { if (!e.target.closest("a")) editDesc(); }; }
  // checklists
  $$("[data-cl]", m).forEach(sec => {
    const clid = +sec.dataset.cl, cl = c.checklists.find(x => x.id === clid);
    const hide = sec.querySelector("[data-hide]"); if (hide) hide.onclick = async () => { cl.hide_done = !cl.hide_done; renderCardModal(); try { await PATCH(`/store/kb/checklists/${clid}`, { hide_done: cl.hide_done }); } catch (e) { fail(e); } };
    const del = sec.querySelector("[data-cldel]"); if (del) del.onclick = () => confirmPop(del, `Delete ${cl.title}?`, "Deleting a checklist is permanent and there is no way to get it back.", "Delete checklist", async () => { try { await DEL(`/store/kb/checklists/${clid}`); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } });
    const t = sec.querySelector("[data-clt]");
    if (c.role !== "observer") t.onclick = () => { const inp = h(`<input class="t" style="font-weight:600">`); inp.value = cl.title; t.replaceWith(inp); inp.focus(); inp.select();
      const done = async () => { const v = inp.value.trim(); if (v && v !== cl.title) { try { await PATCH(`/store/kb/checklists/${clid}`, { title: v }); } catch (e) { fail(e); } } loadFullCard(cid, true); };
      inp.onkeydown = e => { if (e.key === "Enter") inp.blur(); if (e.key === "Escape") { inp.value = cl.title; inp.blur(); } }; inp.onblur = done; };
    $$("[data-i]", sec).forEach(row => {
      const iid = +row.dataset.i, it = cl.items.find(x => x.id === iid);
      row.querySelector("input").onchange = async e => {
        it.done = e.target.checked; row.classList.toggle("done", it.done);
        const n = cl.items.filter(x => x.done).length, pc = Math.round(n * 100 / cl.items.length);
        sec.querySelector(".prog .bar i").style.width = pc + "%"; sec.querySelector(".prog .pc").textContent = pc + "%"; sec.querySelector(".prog").classList.toggle("full", pc === 100);
        try { await PATCH(`/store/kb/items/${iid}`, { done: it.done }); await reloadBoard(true); loadFullCard(cid, true, true).then(() => renderCardModal()); } catch (er) { fail(er); }
      };
      const tx = row.querySelector("[data-it]");
      if (c.role !== "observer") tx.onclick = e => { if (e.target.closest("a")) return; editItem(row, cid, it); };
      const iu = row.querySelector("[data-iu]"); if (iu) iu.onclick = () => { const p = pop(iu, "Assign", `<div class="memrow" data-u="">${ic("x")}<div class="nm">Remove member</div></div>` + S.board.members.map(x => `<div class="memrow" data-u="${x.id}">${av(x, "lg")}<div class="nm">${esc(x.name)}</div>${it.member === x.id ? `<span class="ck">${ic("check")}</span>` : ""}</div>`).join(""));
        $$("[data-u]", p).forEach(r => r.onclick = async () => { closePops(); try { await PATCH(`/store/kb/items/${iid}`, { member: r.dataset.u ? +r.dataset.u : null }); loadFullCard(cid, true); } catch (e) { fail(e); } }); };
      const idd = row.querySelector("[data-id]"); if (idd) idd.onclick = () => { const p = pop(idd, "Change due date", `<input class="t" type="date" data-d value="${it.due || ""}"><div style="display:flex;gap:8px;margin-top:12px"><button class="b pri" data-s>Save</button><button class="b" data-r>Remove</button></div>`);
        p.querySelector("[data-s]").onclick = async () => { closePops(); await PATCH(`/store/kb/items/${iid}`, { due: p.querySelector("[data-d]").value }); loadFullCard(cid, true); };
        p.querySelector("[data-r]").onclick = async () => { closePops(); await PATCH(`/store/kb/items/${iid}`, { due: "" }); loadFullCard(cid, true); }; };
      const im = row.querySelector("[data-im]"); if (im) im.onclick = () => { const p = pop(im, "Item actions", `<button class="mi" data-a="card">Convert to card</button><button class="mi" data-a="copy">Copy text</button><button class="mi dng" data-a="del">Delete</button>`);
        p.querySelector('[data-a="card"]').onclick = async () => { closePops(); try { await POST(`/store/kb/items/${iid}/to-card`); await reloadBoard(true); loadFullCard(cid, true); toast("Converted to a card"); } catch (e) { fail(e); } };
        p.querySelector('[data-a="copy"]').onclick = () => { closePops(); copyText(it.text, "Item copied"); };
        p.querySelector('[data-a="del"]').onclick = async () => { closePops(); try { await DEL(`/store/kb/items/${iid}`); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } }; };
    });
    const add = sec.querySelector("[data-additem]");
    if (add) add.onclick = () => {
      const box = h(`<div style="margin:4px 0 0 28px"><textarea class="t" rows="2" placeholder="Add an item (paste several lines to add many)"></textarea><div style="display:flex;gap:8px;margin-top:8px;align-items:center"><button class="b pri" data-go>Add</button><button class="b sub" data-x>Cancel</button><span style="flex:1"></span><button class="b sub" data-asg>${ic("user", "s14")} Assign</button><button class="b sub" data-due>${ic("clock", "s14")} Due date</button></div></div>`);
      add.parentElement.replaceWith(box); const t = box.querySelector("textarea"); t.focus();
      let member = null, due = "";
      box.querySelector("[data-asg]").onclick = e => { const p = pop(e.currentTarget, "Assign", S.board.members.map(x => `<div class="memrow" data-u="${x.id}">${av(x, "lg")}<div class="nm">${esc(x.name)}</div></div>`).join("")); $$("[data-u]", p).forEach(r => r.onclick = () => { member = +r.dataset.u; closePops(); box.querySelector("[data-asg]").innerHTML = av(person(member)) + " " + esc(person(member).name); }); };
      box.querySelector("[data-due]").onclick = e => { const p = pop(e.currentTarget, "Due date", `<input class="t" type="date" data-d><button class="b pri" style="margin-top:8px" data-s>Save</button>`); p.querySelector("[data-s]").onclick = () => { due = p.querySelector("[data-d]").value; closePops(); box.querySelector("[data-due]").innerHTML = ic("clock", "s14") + " " + fmtDue(due, false); }; };
      const go2 = async () => { const lines = t.value.split("\n").map(x => x.trim()).filter(Boolean); if (!lines.length) { t.focus(); return; }
        try { await POST(`/store/kb/checklists/${clid}/items`, { texts: lines, member, due }); t.value = ""; await loadFullCard(cid, true, true); renderCardModal(); reloadBoard(true); const again = $(`[data-cl="${clid}"] [data-additem]`); if (again) again.click(); } catch (e) { fail(e); } };
      box.querySelector("[data-go]").onclick = go2; box.querySelector("[data-x]").onclick = () => renderCardModal();
      t.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go2(); } if (e.key === "Escape") renderCardModal(); };
    };
  });
  // attachments
  $$("[data-a]", m).forEach(row => {
    const aid = +row.dataset.a, a = c.attachments.find(x => x.id === aid);
    const cv = row.querySelector("[data-cov]"); if (cv) cv.onclick = () => saveCard(cid, { cover: (c.cover || {}).att === aid ? {} : { att: aid, size: (c.cover || {}).size || "normal" } });
    const rn = row.querySelector("[data-ren]"); if (rn) rn.onclick = () => { const p = pop(rn, "Edit attachment", `${a.link ? `<label class="fl" style="margin-top:0">Link</label><input class="t" data-u value="${esc(a.url)}">` : ""}<label class="fl">Link name</label><input class="t" data-n value="${esc(a.name)}"><button class="b pri" style="margin-top:12px" data-s>Update</button>`);
      p.querySelector("[data-s]").onclick = async () => { closePops(); const body = { name: p.querySelector("[data-n]").value }; const u = p.querySelector("[data-u]"); if (u) body.url = u.value; await PATCH(`/store/kb/attachments/${aid}`, body); loadFullCard(cid, true); }; };
    const dl = row.querySelector("[data-adel]"); if (dl) dl.onclick = () => confirmPop(dl, "Delete attachment?", "Deleting an attachment is permanent. There is no undo.", "Delete", async () => { try { await DEL(`/store/kb/attachments/${aid}`); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } });
    row.querySelector("[data-acopy]").onclick = () => copyText(a.link ? a.url : location.origin + a.url, "Link copied");
  });
  $$("[data-tdel]", m).forEach(b => b.onclick = async () => { try { await DEL(`/store/kb/time/${b.dataset.tdel}`); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } });
  $$("[data-unlink]", m).forEach(b => b.onclick = e => { e.stopPropagation(); saveCard(cid, { links: c.links.filter(x => x !== +b.dataset.unlink) }); });
  $$("[data-goc]", m).forEach(r => r.onclick = () => go(`#/b/${r.dataset.gob || S.board.id}/c/${r.dataset.goc}`));
  // comments
  m.querySelector("[data-details]").onclick = () => { SHOW_DETAILS = !SHOW_DETAILS; try { localStorage.setItem("kb_details", SHOW_DETAILS ? "1" : ""); } catch (e) {} renderCardModal(); };
  const fake = m.querySelector("[data-cfake]");
  fake.onclick = () => {
    const box = m.querySelector("[data-cbox]");
    box.innerHTML = editorHtml("cmt-ed", "", "Write a comment… use @ to mention someone") + `<div style="display:flex;gap:8px;margin-top:8px"><button class="b pri" data-csave>Save</button><button class="b sub" data-ccancel>Cancel</button></div>`;
    wireEditor(box, "cmt-ed"); const t = box.querySelector("#cmt-ed"); t.focus();
    const send = async () => { const v = t.value.trim(); if (!v) return; try { await POST(`/store/kb/cards/${cid}/comments`, { text: v }); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } };
    box.querySelector("[data-csave]").onclick = send; box.querySelector("[data-ccancel]").onclick = () => renderCardModal();
    t.onkeydown = e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") send(); if (e.key === "Escape") renderCardModal(); };
  };
  $$("[data-m]", m).forEach(fe => {
    const mid = +fe.dataset.m, cm = c.comments.find(x => x.id === mid);
    const ed = fe.querySelector("[data-cedit]"); if (ed) ed.onclick = () => {
      const bub = fe.querySelector(".bubble"); bub.outerHTML = `<div data-ebox>${editorHtml("ce-" + mid, cm.text)}<div style="display:flex;gap:8px;margin-top:8px"><button class="b pri" data-s>Save</button><button class="b sub" data-x>Discard changes</button></div></div>`;
      wireEditor(fe, "ce-" + mid); const t = fe.querySelector("#ce-" + mid); t.focus();
      fe.querySelector("[data-s]").onclick = async () => { try { await PATCH(`/store/kb/comments/${mid}`, { text: t.value }); loadFullCard(cid, true); } catch (e) { fail(e); } };
      fe.querySelector("[data-x]").onclick = () => renderCardModal();
    };
    const dl = fe.querySelector("[data-cdel]"); if (dl) dl.onclick = () => confirmPop(dl, "Delete comment?", "Deleting a comment is forever. There is no undo.", "Delete comment", async () => { try { await DEL(`/store/kb/comments/${mid}`); await loadFullCard(cid, true); reloadBoard(true); } catch (e) { fail(e); } });
  });
  // drop files on the open card
  m.ondragover = e => { if ([...e.dataTransfer.types].includes("Files")) e.preventDefault(); };
  m.ondrop = e => { if (e.dataTransfer.files.length) { e.preventDefault(); uploadFiles(cid, [...e.dataTransfer.files]); } };
  m.onpaste = e => { const f = [...(e.clipboardData || {}).files || []]; if (f.length && !e.target.closest("textarea,input")) uploadFiles(cid, f); };
}
function editItem(row, cid, it) {
  const box = h(`<div style="flex:1"><textarea class="t" rows="2"></textarea><div style="display:flex;gap:8px;margin-top:6px"><button class="b pri" data-s>Save</button><button class="b sub" data-x>Cancel</button></div></div>`);
  const tx = row.querySelector("[data-it]"); tx.replaceWith(box); row.querySelector(".ci-tools") && (row.querySelector(".ci-tools").style.display = "none");
  const t = box.querySelector("textarea"); t.value = it.text; t.focus(); t.select();
  const save = async () => { const v = t.value.trim(); if (v && v !== it.text) { try { await PATCH(`/store/kb/items/${it.id}`, { text: v }); } catch (e) { fail(e); } } loadFullCard(cid, true); };
  box.querySelector("[data-s]").onclick = save; box.querySelector("[data-x]").onclick = () => renderCardModal();
  t.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } if (e.key === "Escape") renderCardModal(); };
}
function addMenuPop(anchor, cid) {
  const c = S.full;
  const items = [["labels", "tag", "Labels", "Organize, categorize, and prioritize"], ["dates", "clock", "Dates", "Start dates, due dates, and reminders"],
    ["checklist", "checksq", "Checklist", "Add subtasks"], ["members", "user", "Members", "Assign members"], ["attach", "clip", "Attachment", "Add links, pages, work items, and more"],
    ["cover", "img", "Cover", "Colour or picture on top of the card"],
    ...(pu("fields") ? [["fields", "field", "Custom Fields", "Create your own fields"]] : []),
    ...(pu("priority") ? [["priority", "flag", "Priority", "Highest to lowest, like Jira"], ["points", "points", "Story points & estimate", "Size the work"]] : []),
    ...(pu("time") ? [["time", "timer", "Time tracking", "Log hours spent"]] : []),
    ...(pu("voting") ? [["vote", "thumb", c && c.votes.includes(S.me.id) ? "Remove vote" : "Vote", "Show support for this card"]] : []),
    ...(pu("repeater") ? [["repeat", "repeat", "Card Repeater", "Make a copy every day, week or month"]] : []),
    ["link", "link", "Linked cards", "Connect related cards on any board"], ["location", "pin", "Location", "Add the site address"]];
  const p = pop(anchor, "Add to card", items.map(([k, i, l, d]) => `<button class="mi" data-a="${k}">${ic(i)}<div><b style="font-weight:500">${l}</b><small>${d}</small></div></button>`).join(""));
  $$("[data-a]", p).forEach(b => b.onclick = () => {
    const k = b.dataset.a, a = anchor;
    ({ labels: () => labelsPop(a, cid), dates: () => datesPop(a, cid), checklist: () => checklistPop(a, cid), members: () => membersPop(a, cid), attach: () => attachPop(a, cid),
       cover: () => coverPop(a, cid), fields: () => fieldsPop(a, cid), priority: () => priorityPop(a, cid), points: () => pointsPop(a, cid), time: () => timePop(a, cid),
       vote: () => { closePops(); saveCard(cid, { vote: !c.votes.includes(S.me.id) }); }, repeat: () => repeatPop(a, cid), link: () => linkCardPop(a, cid),
       location: () => { const q = pop(a, "Location", `<input class="t" data-l value="${esc(c.location || "")}" placeholder="e.g. Villa 920, Sobha Hartland"><button class="b pri" style="margin-top:12px" data-s>Save</button>`); q.querySelector("[data-s]").onclick = () => { closePops(); saveCard(cid, { location: q.querySelector("[data-l]").value.trim() }); }; } })[k]();
  });
}
function cardMorePop(anchor, cid) {
  const c = S.full;
  const p = pop(anchor, "Actions", `<button class="mi" data-a="join">${ic("user")} ${c.members.includes(S.me.id) ? "Leave" : "Join"}</button>
    <button class="mi" data-a="move">${ic("move")} Move</button><button class="mi" data-a="copy">${ic("copy")} Copy</button><button class="mi" data-a="mirror">${ic("mirror")} Mirror</button>
    <button class="mi" data-a="tpl">${ic("tpl")} ${c.is_template ? "Undo make template" : "Make template"}</button>
    <button class="mi" data-a="watch">${ic("eye")} ${c.watching ? "Stop watching" : "Watch"}</button>
    <hr><button class="mi" data-a="link">${ic("link")} Copy link to card</button><button class="mi" data-a="applink">${ic("link")} Copy link (inside the Infinia app)</button>
    <button class="mi" data-a="md">${ic("copy")} Copy card as text</button><button class="mi" data-a="print">${ic("print")} Print card</button>
    <hr>${c.closed ? `<button class="mi" data-a="restore">${ic("board")} Send to board</button><button class="mi dng" data-a="delete">${ic("trash")} Delete</button>` : `<button class="mi" data-a="archive">${ic("archive")} Archive</button>`}
    <p class="muted" style="margin:8px 0 0">Card #${c.no} · added ${ago(c.created)}${c.created_by ? " by " + esc(c.created_by) : ""}</p>`);
  const a = (k, fn) => { const b = p.querySelector(`[data-a="${k}"]`); if (b) b.onclick = () => fn(b); };
  a("join", () => { closePops(); toggleJoin(cid); }); a("move", () => moveCopyPop(anchor, cid, "move")); a("copy", () => moveCopyPop(anchor, cid, "copy")); a("mirror", () => moveCopyPop(anchor, cid, "mirror"));
  a("tpl", () => { closePops(); saveCard(cid, { is_template: !c.is_template }); }); a("watch", () => { closePops(); saveCard(cid, { watch: !c.watching }); });
  a("link", () => { closePops(); copyText(cardUrl(S.board.id, cid), "Link copied"); }); a("applink", () => { closePops(); copyText(appLink(S.board.id, cid), "Link copied"); });
  a("md", () => { closePops(); const lab = c.labels.map(id => (S.board.labels.find(l => l.id === id) || {}).name).filter(Boolean);
    copyText([`#${c.no} ${c.title}`, `List: ${c.list_title} (${S.board.title})`, lab.length ? `Labels: ${lab.join(", ")}` : "", c.due ? `Due: ${fmtDue(c.due)}${c.due_complete ? " (complete)" : ""}` : "", c.desc ? "\n" + c.desc : "",
      ...c.checklists.map(cl => `\n${cl.title}\n` + cl.items.map(i => `${i.done ? "[x]" : "[ ]"} ${i.text}`).join("\n")), cardUrl(S.board.id, cid)].filter(Boolean).join("\n"), "Card copied"); });
  a("print", () => { closePops(); printCard(c); });
  a("archive", () => { closePops(); archiveCard(cid); }); a("restore", () => { closePops(); saveCard(cid, { closed: false }); });
  a("delete", b => confirmPop(b, "Delete card?", "All actions will be removed from the activity feed and you won't be able to re-open the card. There is no undo.", "Delete", async () => { try { await DEL(`/store/kb/cards/${cid}`); go(`#/b/${S.board.id}`); reloadBoard(true); } catch (e) { fail(e); } }));
}
function printCard(c) {
  const w = window.open("", "_blank"); if (!w) return;
  const lab = c.labels.map(id => S.board.labels.find(l => l.id === id)).filter(Boolean);
  w.document.write(`<html><head><title>${esc(c.title)}</title><style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#172B4D;margin:32px;font-size:14px}h1{font-size:22px;margin:0 0 4px}.m{color:#626F86;margin-bottom:16px}.lab{display:inline-block;padding:2px 8px;border-radius:3px;margin-right:4px;font-size:12px}h3{margin:20px 0 6px;font-size:15px}.it{margin:2px 0}.c{border-top:1px solid #ddd;padding:8px 0}</style></head><body>
    <h1>${esc(c.title)}</h1><div class="m">#${c.no} · ${esc(S.board.title)} / ${esc(c.list_title)}${c.due ? " · Due " + fmtDue(c.due) : ""}</div>
    ${lab.map(l => `<span class="lab" style="background:${getComputedStyle(document.body).getPropertyValue("--l-" + l.color) || "#ddd"}">${esc(l.name || l.color)}</span>`).join("")}
    ${c.desc ? `<h3>Description</h3>${md(c.desc)}` : ""}${c.checklists.map(cl => `<h3>${esc(cl.title)}</h3>${cl.items.map(i => `<div class="it">${i.done ? "☑" : "☐"} ${esc(i.text)}</div>`).join("")}`).join("")}
    ${c.comments.length ? `<h3>Comments</h3>${c.comments.map(m => `<div class="c"><b>${esc(m.who)}</b> <span class="m">${ago(m.at)}</span><div>${md(m.text)}</div></div>`).join("")}` : ""}
    <script>setTimeout(()=>print(),300)<\/script></body></html>`);
  w.document.close();
}

// Full click-sweep: every action on every screen in a real DOM, with
// page errors captured. A syntax-valid page can still throw on click -
// this is what catches that. Run: npm install jsdom && node tests/sweep_frontend.js

const { JSDOM, VirtualConsole } = require("jsdom"); const fs = require("fs");
const REQS = [
 {id:9,ref:"MR-0009",site:"904",status:"approved",needed_by:"2026-09-05",expected_on:null,supplier:null,requested_by:"Febiyan",requested_on:"2026-08-31",notes:"",office_remark:"",urgency:"normal",lines:[
  {id:1,item_id:1,item_code:"ITM1",item_name:"Cement",qty_requested:10,qty_received:0,unit:"bag",status:"approved",supplier:null,purpose:"slab"},
  {id:2,item_id:2,item_code:"ITM2",item_name:"Rebar",qty_requested:5,qty_received:0,unit:"pcs",status:"pending",supplier:null,purpose:""},
  {id:3,item_id:3,item_code:"ITM3",item_name:"Cushion",qty_requested:2,qty_received:0,unit:"pcs",status:"rejected",reject_reason:"No",supplier:null,purpose:""}]},
 {id:10,ref:"MR-0010",site:"902",status:"ordered",needed_by:"2026-08-20",expected_on:"2026-09-02",supplier:null,requested_by:"Amal",requested_on:"2026-08-28",notes:"",office_remark:"",urgency:"urgent",lines:[
  {id:4,item_id:1,item_code:"ITM1",item_name:"Cement",qty_requested:20,qty_received:5,unit:"bag",status:"approved",supplier:{id:3,name:"Al Raha",contact_person:"Bijuam",phone:"050"},purpose:""},
  {id:5,item_id:2,item_code:"ITM2",item_name:"Rebar",qty_requested:8,qty_received:0,unit:"pcs",status:"approved",supplier:{id:7,name:"Gateway",contact_person:"Monce",phone:"045"},purpose:""}]},
 {id:11,ref:"MR-0011",site:"903",status:"pending",needed_by:"2026-09-10",supplier:null,requested_by:"Raj",requested_on:"2026-08-31",notes:"",office_remark:"",urgency:"normal",lines:[
  {id:6,item_id:1,item_code:"ITM1",item_name:"Cement",qty_requested:3,qty_received:0,unit:"bag",status:"pending",supplier:null,purpose:""}]},
];
const errs = []; let fail = 0;
const vc = new VirtualConsole(); vc.on("jsdomError", e => errs.push((e.detail && e.detail.message) || e.message));
const dom = new JSDOM(fs.readFileSync("app.html","utf8"), { runScripts:"dangerously", url:"http://localhost/", virtualConsole: vc,
  beforeParse(w){
    w.fetch = async (u,o) => ({ ok:true, status:200, json: async () => {
      const s=String(u), m=(o&&o.method)||"GET";
      if (s.includes("/decision")) return REQS[0];
      if (s.includes("/status")) {
        // Approving in the app must be reflected here, or the row can
        // never reach the ordering step.
        // Mirrors the server: approving settles every waiting material.
        if (m === "POST") { REQS[0].status = "approved"; REQS[0].lines.forEach(l => { if (l.status === "pending") l.status = "approved"; }); }
        return {ok:true,status:"approved"};
      }
      if (s.includes("/receive-bulk")) return {ok:true,status:"partial"};
      if (s.includes("/store/requests") && m==="POST") return {id:99,ref:"MR-TEST",lines:[{id:1,item_id:1}],new_items:[]};
      if (s.includes("/store/requests") && m==="DELETE") return {ok:true};
      if (s.includes("/store/requests")) return REQS;
      if (s.includes("/store/suppliers")) return [{id:3,name:"Al Raha",contact_person:"Bijuam",phone:"050"},{id:7,name:"Gateway",contact_person:"Monce",phone:"045"}];
      if (s.includes("/store/items")) return [{id:1,code:"ITM1",name:"Cement",unit:"bag",item_type:"consumable"},{id:2,code:"ITM2",name:"Rebar",unit:"pcs",item_type:"consumable"},{id:3,code:"ITM3",name:"Cushion",unit:"pcs",item_type:"consumable"}];
      if (s.includes("/store/stock")) return [];
      if (s.includes("/notifications")) return {notifications:[{id:"n1",kind:"request",title:"New material request MR-0011",detail:"x",screen:"approvals",target:"MR-0011",when:"2026-08-31",level:"info"}],count:1};
      return [];
    }});
    w.confirm=()=>true; w.prompt=()=>"reason"; w.alert=m=>errs.push("ALERT "+m); w.scrollTo=()=>{}; w.HTMLElement.prototype.scrollIntoView=()=>{};
  }});
const w=dom.window, d=dom.window.document;
const ok = (label, cond) => { console.log((cond?"PASS ":"FAIL ")+label); if(!cond) fail++; };
const wait = ms => new Promise(r=>setTimeout(r,ms));
const click = el => el.dispatchEvent(new w.MouseEvent("click",{bubbles:true,cancelable:true}));
const errsSince = n => errs.slice(n);

setTimeout(async()=>{
  w.eval('MY_SCREENS=["store","requests","approvals"]; storeItems=[{id:1,code:"ITM1",name:"Cement",unit:"bag",item_type:"consumable"},{id:2,code:"ITM2",name:"Rebar",unit:"pcs"},{id:3,code:"ITM3",name:"Cushion",unit:"pcs"}]; storeStockCache=[]; suppliers=[{id:3,name:"Al Raha",contact_person:"Bijuam",phone:"050"},{id:7,name:"Gateway",contact_person:"Monce",phone:"045"}];');

  // ---- APPROVALS ----
  w.switchScreen("approvals"); await wait(400);
  let n = errs.length;
  ok("approvals renders 3 rows", d.querySelectorAll("#mreq-list tbody tr[onclick]").length===3);
  const find = (txt) => [...d.querySelectorAll("#mreq-list button")].find(b=>b.textContent.trim()===txt);
  // Approve the pending materials first - ordering is only offered once
  // something is approved, which is the real workflow.
  const approveBtn = find("Approve all") || find("Approve");
  ok("pending request offers Approve first", !!approveBtn);
  click(approveBtn); await wait(300);
  d.getElementById("mreq-filter").value = "all"; await w.loadRequests(); await wait(200);
  // Only the row for MR-0009, not buttons from other rows or the bulk bar.
  const row9 = [...d.querySelectorAll("#mreq-list tbody tr[onclick]")]
    .find(tr => tr.textContent.includes("MR-0009"));
  const orderBtn = [...row9.querySelectorAll("button")]
    .find(b => b.textContent.trim().startsWith("Mark as ordered"));
  ok("approved request offers Mark as ordered", !!orderBtn, row9.textContent.replace(/\s+/g, " ").slice(0, 60));
  click(orderBtn); await wait(300);
  ok("Mark as ordered opens modal", d.getElementById("order-modal-overlay").style.display==="flex" && errsSince(n).length===0);
  ok("picker shows 3 lines, rejected one unticked & unclickable", d.querySelectorAll("#order-lines tr").length===3 && d.querySelectorAll("#order-lines .ol-pick").length===2);
  d.getElementById("order-supplier").value="Al Raha"; await w.saveOrderModal(); await wait(300);
  ok("order saved with message", /ordered from Al Raha/.test(d.getElementById("appr-status").textContent) && errsSince(n).length===0);
  // Approve / Reject request-level (reset filter: saving an order moves it to Ordered)
  d.getElementById("mreq-filter").value="all"; await w.loadRequests(); await wait(200);
  n=errs.length; click(find("Approve")); await wait(200); ok("Approve click no error", errsSince(n).length===0);
  const rowBtnCount = [...d.querySelectorAll("#mreq-list tbody tr[onclick]")].map(tr=>tr.querySelectorAll("button").length);
  ok("every row offers exactly one action", rowBtnCount.every(c=>c===1), rowBtnCount.join(","));
  // Expand a row, per-line decisions
  n=errs.length; click(d.querySelector("#mreq-list tbody tr[onclick]")); await wait(100);
  const lineBtns=[...d.querySelectorAll('[id^="mr-detail-"] button')].map(b=>b.textContent.trim());
  ok("detail shows per-line Approve/Reject/Undo/Print/Delete", ["Approve","Reject","Undo","Print","Delete"].every(t=>lineBtns.includes(t)));
  const lb=[...d.querySelectorAll('[id^="mr-detail-"] button')].find(b=>b.textContent.trim()==="Approve");
  click(lb); await wait(300); ok("per-line Approve runs without error", errsSince(n).length===0);
  const rb=[...d.querySelectorAll('[id^="mr-detail-"] button')].find(b=>b.textContent.trim()==="Reject");
  if (rb) { click(rb); await wait(300); } ok("per-line Reject runs without error", errsSince(n).length===0);
  // Per-supplier delivery buttons on split request
  d.getElementById("mreq-filter").value="all"; await w.loadRequests(); await wait(200);
  n=errs.length;
  const recvBtn=[...d.querySelectorAll("#mreq-list button")].find(b=>b.textContent.trim()==="Record delivery");
  ok("ordered request offers Record delivery", !!recvBtn);
  click(recvBtn); await wait(300);
  const qtyBoxes=[...d.querySelectorAll("#recv-lines .recv-qty")];
  ok("delivery opens with blank quantities", d.getElementById("recv-modal-overlay").style.display==="flex" && qtyBoxes.length>0 && qtyBoxes.every(b=>!b.value) && errsSince(n).length===0);
  ok("each material shows where it comes from", d.querySelectorAll("#recv-lines tr td:last-child").length===qtyBoxes.length);
  // Fill covers the chosen trader's materials and leaves other
  // suppliers' lines blank - a delivery is one truck.
  w.fillAllDue();
  const who = (d.getElementById("recv-supplier").value || "").trim().toLowerCase();
  const rows = [...d.querySelectorAll("#recv-lines tr")].filter(tr => tr.querySelector(".recv-qty"));
  const mine = rows.filter(tr => { const s = (tr.dataset.sup || "").toLowerCase(); return !who || !s || s === who; });
  const others = rows.filter(tr => !mine.includes(tr));
  ok("Fill covers the chosen supplier's materials", mine.length > 0 && mine.every(tr => tr.querySelector(".recv-qty").value));
  ok("other suppliers' materials stay blank", others.every(tr => !tr.querySelector(".recv-qty").value), others.length + " other rows");
  qtyBoxes[qtyBoxes.length-1].value="";   // one material did not turn up
  await w.saveReceive(); await wait(300); ok("Save Delivery runs without error", errsSince(n).length===0);
  // Bulk bar
  n=errs.length; const all=d.getElementById("mr-check-all"); if(all){ all.checked=true; w.toggleAllOrderChecks(all); }
  ok("select-all shows bulk bar", d.getElementById("mr-order-bar") && d.getElementById("mr-order-bar").style.display==="flex");
  w.openOrderModal(w.pickedOrderIds()); await wait(100); ok("bulk order modal opens", d.getElementById("order-modal-overlay").style.display==="flex" && errsSince(n).length===0);
  w.closeOrderModal();
  await w.deletePicked(); await wait(200); ok("Delete selected runs without error", errsSince(n).length===0);

  // ---- FOLLOW-UP ----
  n=errs.length; w.switchScreen("followup"); await wait(400);
  ok("follow-up renders rows + pills", d.querySelectorAll("#fu-list tbody tr").length>=1 && d.getElementById("fu-pills").textContent.includes("late") && errsSince(n).length===0);
  const arr=[...d.querySelectorAll("#fu-list button")].find(b=>b.textContent.trim()==="It arrived");
  if(arr){ click(arr); await wait(300); } ok("It arrived opens delivery", d.getElementById("recv-modal-overlay").style.display==="flex" && errsSince(n).length===0);
  w.closeReceive();

  // ---- NOTIFICATIONS ----
  n=errs.length; await w.loadNotifications(); await wait(100);
  const note=d.querySelector("#bell-list [onclick]"); click(note); await wait(500);
  ok("notification click lands on approvals filtered to MR-0011", d.getElementById("screen-approvals").classList.contains("active") && d.getElementById("mreq-search").value==="MR-0011" && errsSince(n).length===0);

  // ---- REQUESTS (raise) ----
  n=errs.length; w.switchScreen("requests"); await wait(400);
  w.eval(`document.getElementById("mr-site").innerHTML='<option value="704" selected>704</option>'; document.getElementById("mr-by").innerHTML='<option value="Amal" selected>Amal</option>'; document.getElementById("mr-needed").value="2099-01-01";
    if(!document.querySelectorAll("#mr-lines tr").length) addMrLine(); const r=document.querySelector("#mr-lines tr"); r.querySelector(".mr-item-txt").value="ITM1 - Cement"; onMaterialTyped(r.querySelector(".mr-item-txt")); r.querySelector(".mr-qty").value="4"; r.querySelector(".mr-purpose").value="x";`);
  await w.submitMaterialRequest(); await wait(200);
  ok("Send request confirms", /MR-TEST/.test(d.getElementById("mreq-status").textContent) && errsSince(n).length===0);
  n=errs.length; w.toggleDirectPurchase(); await wait(100); ok("Direct purchase opens", d.getElementById("direct-purchase").style.display!=="none" && errsSince(n).length===0);

  // ---- STORE ----
  n=errs.length; w.switchScreen("store"); await wait(400);
  for (const p of ["give","arrive","items","other","reports","suppliers","home"]) { w.storeGo(p); await wait(250); }
  ok("every store panel opens without error", errsSince(n).length===0);
  w.storeGo("other"); w.setMvKind("adjust"); w.setMvKind("transfer"); w.setMvKind("return"); w.setMvKind("lost"); await wait(100);
  ok("all four correction cases render", errsSince(n).length===0);
  w.storeGo("reports"); await wait(300);
  for (const k of ["stock","by_site","usage","assets","lost","hired","mr_open","mr_history"]) { w.pickReport(k,true); await wait(150); }
  ok("every report tile opens without error", errsSince(n).length===0);

  console.log(errs.length ? "\nPAGE ERRORS:\n - "+errs.join("\n - ") : "\nno page errors");
  console.log(fail ? `\n${fail} FAILURE(S)` : "\nSWEEP CLEAN");
  process.exit(fail?1:0);
}, 800);

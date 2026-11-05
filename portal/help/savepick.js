/* Infinia - every download asks where to save it, starting in the folder last used; every share offers the WhatsApp
   app or WhatsApp Web (5 Nov 2026, raised by Arun - purchase, for the whole app).

   Added to every page by the server (one place), so no download or share button in the app can be missed:
   - a download (a link with "download", an export link or window.open of a PDF / Excel / CSV / zip, a file made on
     the page) opens the browser's own "Save as" window. Chrome and Edge open it in the folder last saved to from the
     app ("id" below); the person can go anywhere from there. Browsers without the Save-as window (Firefox, Safari,
     phones) download as before.
   - Share (the system share, wa.me links) first asks: WhatsApp app / WhatsApp Web / Save the file.
*/
(function () {
  if (window.__infSavePick) return;
  window.__infSavePick = true;
  var PICK = typeof window.showSaveFilePicker === "function" && window.isSecureContext !== false;
  var FILE_RX = /[?&]format=(pdf|excel|xlsx|xls|csv|zip|docx|word)\b|\.(pdf|xlsx|xls|csv|zip|docx)(\?|#|$)/i;
  var NOT_FILE_RX = /[?&]format=(view|preview|rows|json|html)\b/i;
  var TYPES = {
    pdf: ["PDF document", "application/pdf"], xlsx: ["Excel workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    xls: ["Excel workbook", "application/vnd.ms-excel"], csv: ["CSV file", "text/csv"], zip: ["Zip folder", "application/zip"],
    docx: ["Word document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    png: ["Image", "image/png"], jpg: ["Image", "image/jpeg"], jpeg: ["Image", "image/jpeg"], txt: ["Text", "text/plain"]
  };
  var origOpen = window.open.bind(window);
  var origClick = HTMLAnchorElement.prototype.click;
  var origShare = navigator.share ? navigator.share.bind(navigator) : null;
  var origCanShare = navigator.canShare ? navigator.canShare.bind(navigator) : null;

  function css() {
    if (document.getElementById("isp-css")) return;
    var s = document.createElement("style"); s.id = "isp-css";
    s.textContent = ".isp-ov{position:fixed;inset:0;background:rgba(23,26,31,.28);z-index:2147483000;display:flex;align-items:center;justify-content:center;font-family:inherit}" +
      ".isp-box{background:#fff;border-radius:14px;box-shadow:0 18px 50px rgba(0,0,0,.28);padding:18px 18px 14px;width:min(360px,92vw);font-size:14px;color:#2B2622}" +
      ".isp-box h4{margin:0 0 4px;font-size:15px}.isp-box p{margin:0 0 12px;color:#6B7075;font-size:12.5px;word-break:break-word}" +
      ".isp-b{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:1px solid #E3E5E8;background:#fff;border-radius:10px;padding:10px 12px;margin:0 0 8px;cursor:pointer;font:inherit;color:inherit}" +
      ".isp-b:hover{border-color:#C0392B;background:#FDF6F5}.isp-b small{display:block;color:#8A8F94;font-size:11.5px}.isp-b i{font-style:normal;font-size:18px;width:22px;text-align:center}" +
      ".isp-x{display:block;margin:2px auto 0;border:0;background:none;color:#8A8F94;cursor:pointer;font:inherit;font-size:12.5px}" +
      ".isp-toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:#2B2622;color:#fff;border-radius:12px;padding:10px 12px 10px 16px;z-index:2147483001;display:flex;gap:12px;align-items:center;font-size:13.5px;box-shadow:0 10px 30px rgba(0,0,0,.3)}" +
      ".isp-toast button{border:0;border-radius:8px;padding:7px 12px;cursor:pointer;font:inherit;font-weight:600}.isp-toast .go{background:#C0392B;color:#fff}.isp-toast .no{background:transparent;color:#C7CDD6}";
    (document.head || document.documentElement).appendChild(s);
  }
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function nameFrom(res, url, fallback) {
    var cd = res && res.headers && res.headers.get("content-disposition") || "";
    var m = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(cd) || /filename\s*=\s*"?([^";]+)"?/i.exec(cd);
    if (m) { try { return decodeURIComponent(m[1].trim().replace(/^"|"$/g, "")); } catch (e) { return m[1].trim(); } }
    if (fallback) return fallback;
    try {
      var u = new URL(url, location.href), last = decodeURIComponent(u.pathname.split("/").pop() || "download");
      var f = (u.searchParams.get("format") || "").toLowerCase();
      var ext = f === "excel" ? "xlsx" : f === "word" ? "docx" : f;
      return ext && !/\.[a-z0-9]{2,4}$/i.test(last) ? last + "." + ext : last;
    } catch (e) { return "download"; }
  }
  function typesFor(name, blob) {
    var ext = (/\.([a-z0-9]{2,4})$/i.exec(name || "") || [])[1];
    ext = ext ? ext.toLowerCase() : "";
    var t = TYPES[ext] || (blob && blob.type ? ["File", blob.type.split(";")[0]] : null);
    if (!t || !ext) return undefined;
    var acc = {}; acc[t[1]] = ["." + ext];
    return [{ description: t[0], accept: acc }];
  }
  function plainDownload(blob, name) {
    var a = document.createElement("a"), u = URL.createObjectURL(blob);
    a.href = u; a.download = name || "download"; a.__isp = true;
    document.body.appendChild(a); origClick.call(a); a.remove();
    setTimeout(function () { URL.revokeObjectURL(u); }, 60000);
  }
  // The browser's Save-as window, opened in the folder last used from the app ("id"), and the file written there.
  function saveBlob(blob, name) {
    if (!PICK) { plainDownload(blob, name); return Promise.resolve(true); }
    var opts = { suggestedName: name || "download", id: "infinia-files", types: typesFor(name, blob) };
    if (!opts.types) delete opts.types;
    return window.showSaveFilePicker(opts).then(function (h) {
      return h.createWritable().then(function (w) { return w.write(blob).then(function () { return w.close(); }); });
    }).then(function () { toast("Saved " + (name || "the file") + "."); return true; }, function (e) {
      if (e && e.name === "AbortError") return false;                       // the person closed the Save-as window
      // too long after the click for the browser to allow the window - one more tap and it opens
      readyToast(blob, name);
      return false;
    });
  }
  var toastEl = null, toastT = null;
  function toast(msg) {
    css(); if (toastEl) toastEl.remove();
    toastEl = document.createElement("div"); toastEl.className = "isp-toast"; toastEl.innerHTML = "<span>" + esc(msg) + "</span>";
    document.body.appendChild(toastEl); clearTimeout(toastT); toastT = setTimeout(function () { if (toastEl) { toastEl.remove(); toastEl = null; } }, 2600);
  }
  function readyToast(blob, name) {
    css(); if (toastEl) toastEl.remove(); clearTimeout(toastT);
    toastEl = document.createElement("div"); toastEl.className = "isp-toast";
    toastEl.innerHTML = "<span>" + esc(name || "Your file") + " is ready</span><button class='go'>Save</button><button class='no'>Close</button>";
    toastEl.querySelector(".go").onclick = function () { var t = toastEl; t.remove(); toastEl = null; saveBlob(blob, name); };
    toastEl.querySelector(".no").onclick = function () { toastEl.remove(); toastEl = null; };
    document.body.appendChild(toastEl);
  }
  // A file link: fetched here, then either saved through the Save-as window (a download) or, when the server sends
  // it to be looked at (a PDF shown in the browser), opened in a tab exactly as before.
  function fetchAndSave(url, fallbackName, asTab) {
    toast("Preparing the file...");
    return fetch(url, { credentials: "same-origin" }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      var cd = (res.headers.get("content-disposition") || "").toLowerCase();
      if (asTab && !/attachment/.test(cd) && !fallbackName) {
        if (toastEl) { toastEl.remove(); toastEl = null; }
        if (!origOpen(url, "_blank")) openToast(url);
        return;
      }
      var name = nameFrom(res, url, fallbackName);
      return res.blob().then(function (b) { return saveBlob(b, name); });
    }).catch(function () { if (toastEl) { toastEl.remove(); toastEl = null; } if (!origOpen(url, "_blank")) openToast(url); });   // as before
  }
  // after a save: one tap to open WhatsApp (the browser lets an app open only from a tap)
  function goToast(label, url, app) {
    css(); if (toastEl) toastEl.remove(); clearTimeout(toastT);
    toastEl = document.createElement("div"); toastEl.className = "isp-toast";
    toastEl.innerHTML = "<span>Saved</span><button class='go'>" + esc(label) + "</button><button class='no'>Close</button>";
    toastEl.querySelector(".go").onclick = function () { toastEl.remove(); toastEl = null; if (app) location.href = url; else origOpen(url, "_blank"); };
    toastEl.querySelector(".no").onclick = function () { toastEl.remove(); toastEl = null; };
    document.body.appendChild(toastEl);
  }
  function openToast(url) {
    css(); if (toastEl) toastEl.remove(); clearTimeout(toastT);
    toastEl = document.createElement("div"); toastEl.className = "isp-toast";
    toastEl.innerHTML = "<span>Your file is ready</span><button class='go'>Open</button><button class='no'>Close</button>";
    toastEl.querySelector(".go").onclick = function () { toastEl.remove(); toastEl = null; origOpen(url, "_blank"); };
    toastEl.querySelector(".no").onclick = function () { toastEl.remove(); toastEl = null; };
    document.body.appendChild(toastEl);
  }
  var WA_RX = /^(https?:)?\/\/(wa\.me|api\.whatsapp\.com)\//i;
  function sameOrigin(u) { try { return new URL(u, location.href).origin === location.origin; } catch (e) { return false; } }
  function isFileUrl(u) {
    if (!u || typeof u !== "string" || /^(mailto|tel|javascript|whatsapp):/i.test(u)) return false;
    try { var x = new URL(u, location.href); if (x.origin !== location.origin) return false; } catch (e) { return false; }
    return FILE_RX.test(u) && !NOT_FILE_RX.test(u) && !/[?&]inline=(1|true)\b/i.test(u);
  }

  // 1. links: <a download>, export / file links, WhatsApp links. Heard last (on the window, after the page's own
  //    handlers): a page that handles the click itself (its own share button) is left to do so.
  window.addEventListener("click", function (ev) {
    if (ev.defaultPrevented || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
    var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
    if (!a || a.__isp) return;
    var href = a.getAttribute("href") || "";
    if (WA_RX.test(a.href)) { ev.preventDefault(); waChoose(a.href); return; }
    if (!PICK) return;
    if (a.hasAttribute("download") && /^(blob|data):/i.test(a.href)) {
      ev.preventDefault();
      fetch(a.href).then(function (r) { return r.blob(); }).then(function (b) { saveBlob(b, a.getAttribute("download") || "download"); });
      return;
    }
    if (isFileUrl(a.href) || (a.hasAttribute("download") && sameOrigin(a.href))) {
      ev.preventDefault();
      fetchAndSave(a.href, a.getAttribute("download") || "", !a.hasAttribute("download"));
    }
  }, false);
  // 2. files made on the page and clicked by code (a.click() with a blob / data link)
  HTMLAnchorElement.prototype.click = function () {
    if (PICK && !this.__isp && this.hasAttribute("download") && /^(blob|data):/i.test(this.href || "")) {
      var a = this; fetch(a.href).then(function (r) { return r.blob(); }).then(function (b) { saveBlob(b, a.getAttribute("download") || "download"); },
        function () { origClick.call(a); });
      return;
    }
    if (PICK && !this.__isp && this.hasAttribute("download") && sameOrigin(this.href) && !/^(blob|data):/i.test(this.href || "")) { fetchAndSave(this.href, this.getAttribute("download") || ""); return; }
    return origClick.call(this);
  };
  // 3. window.open of a file, and of WhatsApp
  window.open = function (url, target, features) {
    var u = typeof url === "string" ? url : (url && url.href) || "";
    if (WA_RX.test(u)) { waChoose(u); return null; }
    if (PICK && isFileUrl(u)) { fetchAndSave(u, "", true); return null; }
    return origOpen(url, target, features);
  };

  // ---- WhatsApp: the app or WhatsApp Web --------------------------------------------------------------------
  function menu(title, sub, items) {
    css();
    var ov = document.createElement("div"); ov.className = "isp-ov";
    ov.innerHTML = "<div class='isp-box' role='dialog'><h4>" + esc(title) + "</h4>" + (sub ? "<p>" + esc(sub) + "</p>" : "") +
      items.map(function (it, i) { return "<button class='isp-b' data-i='" + i + "'><i>" + it[0] + "</i><span>" + esc(it[1]) + "<small>" + esc(it[2] || "") + "</small></span></button>"; }).join("") +
      "<button class='isp-x'>Cancel</button></div>";
    ov.addEventListener("click", function (e) {
      if (e.target === ov || e.target.closest(".isp-x")) { ov.remove(); return; }
      var b = e.target.closest(".isp-b"); if (!b) return;
      ov.remove(); items[+b.dataset.i][3]();
    });
    document.body.appendChild(ov);
    return ov;
  }
  function waParts(u) {
    try {
      var x = new URL(u, location.href), phone = "", text = x.searchParams.get("text") || "";
      if (/wa\.me$/i.test(x.hostname)) phone = x.pathname.replace(/\D/g, ""); else phone = (x.searchParams.get("phone") || "").replace(/\D/g, "");
      return { phone: phone, text: text };
    } catch (e) { return { phone: "", text: "" }; }
  }
  function waLinks(phone, text) {
    var q = (phone ? "phone=" + phone + "&" : "") + "text=" + encodeURIComponent(text || "");
    return { app: "whatsapp://send?" + q, web: "https://web.whatsapp.com/send?" + q };
  }
  function waChoose(u) {
    var p = waParts(u), L = waLinks(p.phone, p.text);
    menu("Send by WhatsApp", p.phone ? "To +" + p.phone : "", [
      ["\u{1F4F1}", "WhatsApp app", "Opens WhatsApp on this computer or phone", function () { location.href = L.app; }],
      ["\u{1F310}", "WhatsApp Web", "Opens web.whatsapp.com in a new tab", function () { origOpen(L.web, "_blank"); }]
    ]);
  }
  // The share button (the system share): WhatsApp app (the system share - pick WhatsApp in it), WhatsApp Web, or save
  if (origShare || PICK) {
    var share = function (data) {
      data = data || {};
      var files = data.files || [], f = files[0];
      var text = [data.title && !f ? data.title : "", data.text || "", data.url || ""].filter(Boolean).join("\n");
      return new Promise(function (resolve, reject) {
        var items = [];
        // a phone: its share window, WhatsApp in it. A computer: the file saved where they choose, then WhatsApp opened
        var phone = origShare && !PICK;
        items.push(["\u{1F4F1}", "WhatsApp app", phone ? "Pick WhatsApp in the share window" : f ? "Save the file, then WhatsApp opens - attach it there" : "Opens WhatsApp on this computer", function () {
          if (phone) { origShare(data).then(resolve, reject); return; }
          if (!f) { location.href = waLinks("", text).app; resolve(); return; }
          saveBlob(f, f.name).then(function (ok) { if (ok) goToast("Open WhatsApp", waLinks("", text).app, true); resolve(); });
        }]);
        items.push(["\u{1F310}", "WhatsApp Web", f ? "Opens WhatsApp Web - save the file, then attach it there" : "Opens web.whatsapp.com in a new tab", function () {
          origOpen(f ? "https://web.whatsapp.com/" : waLinks("", text).web, "_blank");
          if (f) readyToast(f, f.name);
          resolve();
        }]);
        if (f) items.push(["\u{1F4BE}", "Save the file", "Choose the folder - it opens where you saved last", function () { saveBlob(f, f.name).then(resolve); }]);
        if (origShare) items.push(["\u{2197}", "Other apps", "Email, Teams and the rest - the share window", function () { origShare(data).then(resolve, reject); }]);
        var ov = menu("Share" + (f ? " " + f.name : ""), "", items);
        ov.querySelector(".isp-x").addEventListener("click", function () { reject(new DOMException("Share cancelled", "AbortError")); });
        ov.addEventListener("click", function (e) { if (e.target === ov) reject(new DOMException("Share cancelled", "AbortError")); });
      });
    };
    try { Object.defineProperty(navigator, "share", { value: share, configurable: true, writable: true }); } catch (e) { navigator.share = share; }
    // pages ask "can this share a file?" before sharing - with the choice above it always can
    var can = function (d) { return true; };
    try { Object.defineProperty(navigator, "canShare", { value: can, configurable: true, writable: true }); } catch (e) { navigator.canShare = can; }
  }
  window.infSaveBlob = saveBlob;
  window.infWaChoose = waChoose;
})();

// Frontend smoke test: boots app.html in a real DOM and clicks through
// the request flow. Exists because a syntax-valid page can still call a
// function that was never defined - `node --check` passes, the API
// suite passes, and the Send button is dead. This catches that class.
//
// Run:  npm install jsdom && node tests/smoke_frontend.js
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "..", "app.html"), "utf8");
let failures = 0;
const check = (label, ok, extra) => {
  console.log((ok ? "PASS " : "FAIL ") + label + (ok || !extra ? "" : `  [${extra}]`));
  if (!ok) failures++;
};

const dom = new JSDOM(html, {
  runScripts: "dangerously", url: "http://localhost/",
  beforeParse(window) {
    window.fetch = async (url, opts) => ({ ok: true, status: 200, json: async () => {
      const u = String(url);
      if (u.includes("/store/requests") && opts && opts.method === "POST")
        return { id: 99, ref: "MR-TEST", lines: [{ id: 1, item_id: 1 }], new_items: [] };
      return [];
    }});
    window.confirm = () => true;
    window.alert = () => {};
    window.scrollTo = () => {};
    window.HTMLElement.prototype.scrollIntoView = () => {};
  },
});

const w = dom.window, d = w.document;
const pageErrors = [];
w.addEventListener("error", e => pageErrors.push(e.message));

setTimeout(() => {
  check("page scripts loaded without errors", pageErrors.length === 0, pageErrors[0]);

  // Every onclick in the markup must reference a function that exists -
  // the exact class of bug that shipped a dead Send button.
  const missing = new Set();
  d.querySelectorAll("[onclick]").forEach(el => {
    const m = (el.getAttribute("onclick") || "").match(/^\s*(\w+)\s*\(/);
    if (m && typeof w[m[1]] !== "function") missing.add(m[1]);
  });
  check("every onclick handler is a real function", missing.size === 0, [...missing].join(", "));

  // Click through: fill the raise form and send it.
  w.eval(`
    storeItems = [{id:1, code:"ITM1", name:"Cement", unit:"bag", item_type:"consumable"}];
    document.getElementById("mr-site").innerHTML = '<option value="704" selected>704</option>';
    document.getElementById("mr-by").innerHTML = '<option value="Amal" selected>Amal</option>';
    document.getElementById("mr-needed").value = "2099-01-01";
    if (!document.querySelectorAll("#mr-lines tr").length) addMrLine();
    const row = document.querySelector("#mr-lines tr");
    row.querySelector(".mr-item-txt").value = "ITM1 - Cement";
    onMaterialTyped(row.querySelector(".mr-item-txt"));
    row.querySelector(".mr-qty").value = "10";
    row.querySelector(".mr-purpose").value = "smoke test";
  `);

  // Validation first: an empty date must warn, not throw.
  w.eval(`document.getElementById("mr-needed").value = "";`);
  Promise.resolve(w.eval("submitMaterialRequest()")).then(() => {
    const warn = d.getElementById("mreq-status").textContent || "";
    check("validation message renders", warn.includes("date"), warn.slice(0, 60));

    // Then the happy path.
    w.eval(`document.getElementById("mr-needed").value = "2099-01-01";`);
    return Promise.resolve(w.eval("submitMaterialRequest()"));
  }).then(() => setTimeout(() => {
    const t = d.getElementById("mreq-status").textContent || "";
    check("send confirms with the MR ref", t.includes("MR-TEST"), t.slice(0, 60));
    console.log(failures ? `\n${failures} FAILURE(S)` : "\nALL PASSED");
    process.exit(failures ? 1 : 0);
  }, 100)).catch(e => {
    check("request flow ran", false, e.message);
    process.exit(1);
  });
}, 500);

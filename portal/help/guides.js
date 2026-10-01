/* Help guides - what the search box, the "?" button and "Show me" use.

   ONE GUIDE = one everyday job, in plain words, one action per step.

     id     short name, also the screenshot file names (img/<id>-<n>.jpg)
     title  "How to ..." as a person would ask it
     words  other words people type for the same job (typos are handled)
     go     where it happens: page / tab / sub, as in the address
            (/?p=store#store:give  ->  {page:"store", tab:"store", sub:"give"})
            the right needed is taken from that tab, so a login only
            finds guides for pages it can open
     steps  [{say, el, run}]
            say  one short sentence - what to do
            el   the button or box to circle (CSS selector); leave out
                 to show the step without a circle
            run  optional code to open the right part first (a form)
     tip    optional "good to know" line under the steps

   WHEN THE APP CHANGES: edit the guide here, then run
       node tests/help_screens.js
   It opens every guide in a browser, retakes every screenshot and
   STOPS naming any guide whose button or box is no longer there - so a
   guide can never quietly go out of date.

   HELP_TIPS: the small (i) beside a confusing box, selector -> text.
*/
window.HELP_GUIDES = [
  // ---------------- Attendance ----------------
  { id: "att-mark", area: "Attendance", title: "How to mark today's attendance",
    words: "attendance present absent mark day daily fill enter register workers",
    go: { page: "attendance", tab: "attendance" },
    steps: [
      { say: "Pick the day here. Today is chosen already.", el: "#date-picker" },
      { say: "Tick the box at the top to choose all workers (or tick them one by one).", el: "#header-check" },
      { say: "Choose Present for morning (A.M) and afternoon (P.M), and the site.", el: "#bulk-am" },
      { say: "Press 'Apply to Ticked'. Every ticked worker is filled in.", el: "button[onclick='applyBulk()']" },
      { say: "Change anyone who was different (absent, sick) in his own row." },
      { say: "Press Save. Nothing is kept until you save.", el: "#floating-save-btn" }],
    tip: "The 'Unfilled Emp' button shows who has no attendance yet for the day." },
  { id: "att-holiday", area: "Attendance", title: "How to mark a Sunday or public holiday",
    words: "sunday holiday eid off day public holiday weekend friday",
    go: { page: "attendance", tab: "attendance" },
    steps: [
      { say: "Pick the Sunday or holiday date.", el: "#date-picker" },
      { say: "Tick the box at the top to choose all workers.", el: "#header-check" },
      { say: "Choose Sunday (or Holiday) for A.M and P.M.", el: "#bulk-am" },
      { say: "Press 'Apply to Ticked'.", el: "button[onclick='applyBulk()']" },
      { say: "Workers who worked that day: change their row to Present.", el: "#search-box" },
      { say: "Press Save.", el: "#floating-save-btn" }] },
  { id: "att-fix", area: "Attendance", title: "How to correct a past day's attendance",
    words: "correct change edit wrong mistake yesterday past day fix attendance",
    go: { page: "attendance", tab: "attendance" },
    steps: [
      { say: "Pick the day that is wrong.", el: "#date-picker" },
      { say: "Type the worker's number or name to find him.", el: "#search-box" },
      { say: "Change his A.M / P.M, site or overtime in his row." },
      { say: "Press Save. His salary card updates by itself.", el: "#floating-save-btn" }] },
  { id: "att-livecard", area: "Attendance", title: "How to see one worker's card for the month",
    words: "live card worker card month days attendance summary one worker salary card view",
    go: { page: "attendance", tab: "livecard" },
    steps: [
      { say: "Choose the cycle (month).", el: "#livecard-cycle" },
      { say: "Type the worker's number or name, then click him in the list.", el: "#livecard-search" },
      { say: "His days and salary show on the right. Print it with PDF.", el: "button[onclick=\"exportLiveCard('pdf')\"]" }] },

  // ---------------- Workers ----------------
  { id: "worker-add", area: "Workers", title: "How to add a new labourer",
    words: "add new labour labourer worker join joiner employee hire recruit master data",
    go: { page: "attendance", tab: "masterdata" },
    steps: [
      { say: "Type his employee number.", el: "#md-emp-no" },
      { say: "Type his name and trade.", el: "#md-emp-name" },
      { say: "Choose the company and Daily wage or Fixed monthly.", el: "#md-emp-paytype" },
      { say: "Type his total salary and basic salary.", el: "#md-emp-total" },
      { say: "Put the day he joined.", el: "#md-emp-joined" },
      { say: "Press Save Employee. He now shows on attendance.", el: "button[onclick='saveEmployee()']" }] },
  { id: "worker-increment", area: "Workers", title: "How to give a labourer a salary increase",
    words: "increment increase raise salary change rate pay rise hike labour",
    go: { page: "attendance", tab: "masterdata" },
    steps: [
      { say: "Find the worker in the list below and press Edit.", el: "#screen-masterdata button[onclick^='editEmployee']" },
      { say: "Type the new total salary (and basic).", el: "#md-emp-total" },
      { say: "Choose from which cycle the new salary starts. Older months stay as they were.", el: "#md-rate-from" },
      { say: "Press Save Employee.", el: "button[onclick='saveEmployee()']" }] },
  { id: "worker-leaves", area: "Workers", title: "How to remove a labourer who left (terminated, resigned)",
    words: "remove terminate terminated fired resign resigned left leaving quit absconded cancel visa exit labour worker",
    go: { page: "attendance", tab: "masterdata" },
    steps: [
      { say: "Find the worker in the list below and press Edit.", el: "#screen-masterdata button[onclick^='editEmployee']" },
      { say: "Put his last working day here.", el: "#md-emp-terminated" },
      { say: "Press Save Employee.", el: "button[onclick='saveEmployee()']" },
      { say: "He is paid up to that day and drops off from the next cycle by himself." }],
    tip: "Do not use Remove for a worker who worked with us - his past cards would go. Use the last working day." },
  { id: "staff-leaves", area: "Workers", title: "How to do a final settlement for office staff",
    words: "final settlement gratuity end of service eosb resign resignation terminate leaving office staff dues",
    go: { page: "payroll", tab: "hrpayroll", sub: "gratuity" },
    steps: [
      { say: "Choose the staff member.", el: "label:has(#hr-grat-emp)" },
      { say: "Scroll to Final settlement and put his last working day.", el: "#fs-last" },
      { say: "Choose the reason (resignation, termination...).", el: "#fs-reason" },
      { say: "Check leave days, loan and anything to add or take off. The total updates as you type.", el: "#fs-leave" },
      { say: "Print it from Print / Export.", el: "#hr-fs-card .hr-menu-btn" }] },
  { id: "staff-add", area: "Workers", title: "How to add new office staff",
    words: "add new office staff employee join joiner hire staff register local staff",
    go: { page: "payroll", tab: "hrpayroll", sub: "staff" },
    steps: [
      { say: "Press '+ New staff'.", el: "button[onclick='hrNewStaff()']" },
      { say: "Fill in the name, company, salary and join date, then save." }] },

  // ---------------- Store ----------------
  { id: "stock-check", area: "Store", title: "How to see how much stock we have",
    words: "stock on hand balance quantity how much inventory available store check material",
    go: { page: "store", tab: "store", sub: "home" },
    steps: [
      { say: "Type the material name or code.", el: "#home-stock-search" },
      { say: "The list shows what is in the store and at each site." }] },
  { id: "stock-add", area: "Store", title: "How to add stock to the store",
    words: "add stock opening stock put in store receive quantity count materials",
    go: { page: "store", tab: "store", sub: "items" },
    steps: [
      { say: "Start typing the material in the first line and pick it.", el: "#opening-lines" },
      { say: "Type how many, and where it is (store or a site).", el: "#opening-lines" },
      { say: "More materials? Press '+ Add another material'.", el: "button[onclick='addOpeningLine()']" },
      { say: "Press Add stock.", el: "#op-save-btn" }],
    tip: "For a delivery from a supplier use 'Material arrived' instead - it keeps the order and cost matched." },
  { id: "item-new", area: "Store", title: "How to add a new material to the list",
    words: "new item material add create catalogue product unit code",
    go: { page: "store", tab: "store", sub: "items" },
    steps: [
      { say: "Type the item name.", el: "#it-name" },
      { say: "Choose its category and unit (bag, piece, metre...).", el: "#it-unit" },
      { say: "Choose Consumable (used up) or Asset (tool that comes back).", el: "#it-type" },
      { say: "Press Save Item.", el: "button[onclick='saveStoreItem()']" }] },
  { id: "arrived", area: "Store", title: "How to record material that arrived",
    words: "arrived delivery received receive goods grn delivery note supplier came",
    go: { page: "store", tab: "store", sub: "arrive" },
    steps: [
      { say: "Find the order in this list and press its button. The quantities are filled in.", el: "#arrive-list" },
      { say: "Check the quantities against the delivery note and save." },
      { say: "Bought without an order? Press 'Record a direct purchase'.", el: "button[onclick='goDirectPurchase()']" }] },
  { id: "move", area: "Store", title: "How to move material to a site (or site to site)",
    words: "move give issue send transfer material site to site shift deliver tools assets",
    go: { page: "store", tab: "store", sub: "give" },
    steps: [
      { say: "Type who is taking it.", el: "#out-person" },
      { say: "Choose where it is coming from - the store or a site.", el: "#out-from" },
      { say: "Choose where it is going.", el: "#out-site" },
      { say: "Type the material and how many.", el: "#out-lines" },
      { say: "Press the button to save the move.", el: "#out-save-btn" }] },
  { id: "return-store", area: "Store", title: "How to return material from a site to the store",
    words: "return back to store site return tools bring back come back",
    go: { page: "store", tab: "store", sub: "give" },
    steps: [
      { say: "Choose the site it is coming from.", el: "#out-from" },
      { say: "Choose Central store as where it is going.", el: "#out-site" },
      { say: "Type the material and how many.", el: "#out-lines" },
      { say: "Press the button to save.", el: "#out-save-btn" }] },
  { id: "lost", area: "Store", title: "How to write off lost or damaged material",
    words: "lost damaged broken stolen write off missing scrap waste",
    go: { page: "store", tab: "store", sub: "other" },
    steps: [
      { say: "Press 'Lost or damaged'.", el: ".rep-tile[onclick=\"setMvKind('lost')\"]" },
      { say: "Type the material.", el: "#mv-item-txt", run: "setMvKind('lost')" },
      { say: "Type how many, and where it was.", el: "#mv-qty" },
      { say: "Press Save.", el: "#mv-form button[onclick='saveMovement()']" }] },
  { id: "count-fix", area: "Store", title: "How to fix a wrong stock number after counting",
    words: "correct wrong stock count adjust adjustment stock take physical count difference",
    go: { page: "store", tab: "store", sub: "other" },
    steps: [
      { say: "Press 'Fix a wrong number'.", el: ".rep-tile[onclick=\"setMvKind('adjust')\"]" },
      { say: "Type the material and the correct quantity.", el: "#mv-item-txt", run: "setMvKind('adjust')" },
      { say: "Press Save.", el: "#mv-form button[onclick='saveMovement()']" }] },
  { id: "rent-in", area: "Store", title: "How to book in rented equipment",
    words: "rent rental hire hired scaffolding equipment on rent trader",
    go: { page: "store", tab: "rentals", sub: "hire" },
    steps: [
      { say: "Type the trader's name.", el: "#hin-supplier" },
      { say: "Choose where it is, and their delivery note number.", el: "#hin-location" },
      { say: "Add the items and quantities.", el: "button[onclick='addHireInLine()']" },
      { say: "Press 'Book in as rented'.", el: "button[onclick='saveHireIn()']" }] },

  // ---------------- Purchasing ----------------
  { id: "request", area: "Purchasing", title: "How to ask the office for material (material request)",
    words: "material request mr ask need order site request requisition indent",
    go: { page: "store", tab: "requests", sub: "requests" },
    steps: [
      { say: "Choose the site.", el: "#mr-site" },
      { say: "Choose who is asking and when it is needed.", el: "#mr-needed" },
      { say: "Type the material, quantity and what it is for.", el: "#mr-lines" },
      { say: "Press 'Send Request to Office'.", el: "#mr-send-btn" }] },
  { id: "approve", area: "Purchasing", title: "How to approve a material request",
    words: "approve approval reject request accept pending decide",
    go: { page: "store", tab: "requests", sub: "approvals" },
    steps: [
      { say: "Waiting requests are listed here. Change the filter to see others.", el: "#mreq-filter" },
      { say: "Press Approve (or Reject) on each line.", el: "#mreq-list" }] },
  { id: "lpo", area: "Purchasing", title: "How to make an LPO (purchase order)",
    words: "lpo purchase order po buy order supplier generate local purchase order",
    go: { page: "store", tab: "purchasing", sub: "purchase" },
    steps: [
      { say: "Approved requests wait here. Tick the lines going to one supplier.", el: "#lpo-pending-card" },
      { say: "Press 'Generate LPO from ticked'. The order is filled in.", el: "button[onclick='lpoFromTicked()']" },
      { say: "No request? Press 'New Purchase Order' to start an empty one.", el: "button[onclick='newLpo()']" },
      { say: "Pick the supplier, check prices, and press Save & Generate.", el: "#lpo-save-btn", run: "newLpo()" }] },
  { id: "lpo-find", area: "Purchasing", title: "How to find an old LPO or last price paid",
    words: "lpo register old order price paid last price history find search purchase",
    go: { page: "store", tab: "purchasing", sub: "lporegister" },
    steps: [
      { say: "Type a material to see what we paid for it.", el: "#price-q" },
      { say: "Or narrow the list by supplier, site or dates.", el: "#lpr-supplier" },
      { say: "Print or export with these buttons.", el: "button[onclick=\"exportLpoReport('pdf')\"]" }] },
  { id: "supplier", area: "Purchasing", title: "How to add a supplier",
    words: "supplier vendor add new trader company trn contact",
    go: { page: "store", tab: "purchasing", sub: "suppliers" },
    steps: [
      { say: "Type the supplier name, contact person and phone.", el: "#sup-name" },
      { say: "Type the TRN, email and payment terms.", el: "#sup-trn" },
      { say: "Press Save supplier.", el: "button[onclick='saveSupplier()']" }] },
  { id: "petty", area: "Purchasing", title: "How to enter petty cash (bill paid or cash received)",
    words: "petty cash bill receipt expense cash paid received balance amal register pro office site",
    go: { page: "store", tab: "petty" },
    steps: [
      { say: "Pick your cash box: Site, PRO or Office. You only see the boxes you are allowed.", el: ".pg-sub" },
      { say: "Choose 'Bill paid' or 'Cash received'.", el: ".pc-kind" },
      { say: "Put the date and what it was for.", el: "#pc-desc" },
      { say: "Type the shop / supplier and the site.", el: "#pc-sup" },
      { say: "Type the amount and press Add. The balance updates.", el: "#pc-save" },
      { say: "Print the month from Print / Export.", el: "#screen-pettycash .hr-menu-btn" }] },

  // ---------------- Labour payroll ----------------
  { id: "check-pay", area: "Payroll", title: "How to check attendance before paying salaries",
    words: "check before pay error missing unfilled attendance errors verify payroll",
    go: { page: "payroll", tab: "labourpay", sub: "errorcheck" },
    steps: [
      { say: "Choose the cycle.", el: "#errcheck-cycle" },
      { say: "Press Run Check. It lists missing or odd days.", el: "button[onclick='loadErrorCheck()']" },
      { say: "Fix each one in Attendance, then run the check again." }] },
  { id: "labour-add-ded", area: "Payroll", title: "How to add a bonus or deduction to a labourer's salary",
    words: "addition deduction bonus fine advance allowance add take cut labour salary adjust",
    go: { page: "payroll", tab: "labourpay", sub: "adjust" },
    steps: [
      { say: "Choose the cycle.", el: "#adj-cycle" },
      { say: "Find the worker and click his row.", el: "#adj-search-box" },
      { say: "Type what it is for and the amount.", el: "#adj-desc" },
      { say: "Choose Addition or Deduction.", el: "#adj-type" },
      { say: "Press Add.", el: "button[onclick='addAdjustmentRow()']" }] },
  { id: "labour-cards", area: "Payroll", title: "How to print labour salary cards",
    words: "salary cards print payslip pay slip labour cards pdf excel wages",
    go: { page: "payroll", tab: "labourpay", sub: "combine" },
    steps: [
      { say: "Choose the cycle.", el: "#combine-cycle" },
      { say: "Press 'Combine to PDF' for all cards in one file.", el: "button[onclick=\"exportCombineCards('pdf')\"]" },
      { say: "For one worker only, type his name under One Worker.", el: "#combine-emp" }] },
  { id: "labour-full", area: "Payroll", title: "How to pay labour full salary early",
    words: "pay full salary now early advance before end of cycle full month labour",
    go: { page: "payroll", tab: "labourpay", sub: "combine" },
    steps: [
      { say: "Choose the cycle.", el: "#combine-cycle" },
      { say: "Press 'Pay full salary now'. The cards show the full cycle salary.", el: "#lab-full-btn" }] },
  { id: "office-pay", area: "Payroll", title: "How to run office staff salary",
    words: "office payroll salary run staff monthly approve lock statement wps office salary",
    go: { page: "payroll", tab: "hrpayroll", sub: "cycle" },
    steps: [
      { say: "Choose the company and month.", el: "#hr-run-month" },
      { say: "Choose Office staff or Local staff.", el: "button[onclick=\"hrPickGroup('staff')\"]" },
      { say: "Check the figures. Print the statement from Print / Export.", el: "#screen-hrpayroll .hr-menu-btn" },
      { say: "When correct, press 'Approve & lock'.", el: "#screen-hrpayroll button[onclick*='approvePayrollRun']" }] },
  { id: "office-full", area: "Payroll", title: "How to pay office staff the full month early",
    words: "pay full month now early advance office local staff 27th 28th holiday",
    go: { page: "payroll", tab: "hrpayroll", sub: "cycle" },
    steps: [
      { say: "Choose the month.", el: "#hr-run-month" },
      { say: "Press 'Pay full month now'.", el: "button[onclick='hrFullMonth()']" }] },
  { id: "office-absence", area: "Payroll", title: "How to record leave or absence for office staff",
    words: "leave absence absent sick annual leave vacation unpaid office staff",
    go: { page: "payroll", tab: "hrpayroll", sub: "leave" },
    steps: [
      { say: "Choose the staff member.", el: "label:has(#hr-leave-emp)" },
      { say: "Choose the kind of leave.", el: "#hr-leave-kind" },
      { say: "Put the from and to dates.", el: "#hr-leave-from" },
      { say: "Press Record.", el: "#hr-leave-save" }] },
  { id: "office-add-ded", area: "Payroll", title: "How to add or deduct from office staff salary",
    words: "addition deduction office staff taxi fee ticket fine iloe advance",
    go: { page: "payroll", tab: "hrpayroll", sub: "items" },
    steps: [
      { say: "Choose the staff member.", el: "label:has(#hr-item-emp)" },
      { say: "Choose Addition or Deduction and what it is for.", el: "label:has(#hr-item-dir)" },
      { say: "Type the amount.", el: "#hr-item-amount" },
      { say: "Press Add.", el: "#hr-item-save" }] },
  { id: "office-loan", area: "Payroll", title: "How to record a staff loan",
    words: "loan advance borrow instalment emi staff loan",
    go: { page: "payroll", tab: "hrpayroll", sub: "loans" },
    steps: [
      { say: "Choose the staff member.", el: "label:has(#hr-loan-emp)" },
      { say: "Type the amount and date.", el: "#hr-loan-amount" },
      { say: "Type the monthly instalment taken from salary.", el: "#hr-loan-instalment" },
      { say: "Press Record loan.", el: "#hr-loan-save" }] },
  { id: "office-increment", area: "Payroll", title: "How to give office staff an increment",
    words: "increment increase raise office staff salary change",
    go: { page: "payroll", tab: "hrpayroll", sub: "increments" },
    steps: [
      { say: "Choose the staff member.", el: "label:has(#hr-inc-emp)" },
      { say: "Put the date it starts and the amount.", el: "#hr-inc-amount" },
      { say: "Press Record increment.", el: "button[onclick='addIncrement()']" }] },

  // ---------------- Expiry ----------------
  { id: "expiry-check", area: "Expiry", title: "How to see what is expiring",
    words: "expiry expired expiring due visa emirates id passport renew renewal reminder",
    go: { page: "expiry", tab: "expiry", sub: "people" },
    steps: [
      { say: "These boxes show what is expired, due in 7 days, due in 30 days, and missing. Click one to see the list.", el: "#exp-cards" },
      { say: "Red means renew now. Every morning the bell lists them once." }] },
  { id: "expiry-person", area: "Expiry", title: "How to add a visa, Emirates ID or passport date",
    words: "add document visa emirates id eid passport labour card expiry date person",
    go: { page: "expiry", tab: "expiry", sub: "people" },
    steps: [
      { say: "Choose the person.", el: "#hr-doc-emp" },
      { say: "Choose the document.", el: "#hr-doc-kind" },
      { say: "Put the expiry date.", el: "#hr-doc-expires" },
      { say: "Press Save document.", el: "button[onclick='addDocument()']" }] },
  { id: "expiry-company", area: "Expiry", title: "How to add a vehicle, NOC or permit expiry",
    words: "vehicle mulkiya insurance noc permit licence trade license company document expiry",
    go: { page: "expiry", tab: "expiry", sub: "company" },
    steps: [
      { say: "Type the kind (Vehicle, NOC, Permit...).", el: "#hr-exp-cat" },
      { say: "Type what it is for (the vehicle, the villa...).", el: "#hr-exp-item" },
      { say: "Type the document name and its expiry date.", el: "#hr-exp-expires" },
      { say: "Press Save.", el: "button[onclick='saveExpiry()']" }] },

  { id: "pdc-add", area: "Expiry", title: "How to add a post-dated cheque (PDC)",
    words: "pdc post dated cheque check payment supplier rent instalment due bank tracker accountant",
    go: { page: "expiry", tab: "expiry", sub: "pdc" },
    steps: [
      { say: "Type who the cheque is for.", el: "#pdc-payee" },
      { say: "Type the cheque number, bank and the cheque date.", el: "#pdc-date" },
      { say: "Type the amount, and what it is for.", el: "#pdc-amt" },
      { say: "Rent or instalments? Pick how many months - the cheque numbers count up by themselves.", el: "#pdc-repeat" },
      { say: "Press Add. It shows in the monthly tracker below.", el: "#pdc-save" }],
    tip: "Only admin and the chief accountant can see PDCs. Reminders come 14 and 7 days before the cheque date." },
  { id: "pdc-clear", area: "Expiry", title: "How to mark a cheque cleared",
    words: "pdc cheque cleared paid presented bounced cancel cancelled",
    go: { page: "expiry", tab: "expiry", sub: "pdc" },
    steps: [
      { say: "Open the Cheque list.", el: "#pdc-view button[data-v='list']", run: "pdcView('grid')" },
      { say: "Press Cleared on the cheque's line. To cancel a cheque, click its line and set Status to Cancelled.", el: "#pdc-lbody", run: "pdcView('list')" }] },
  // ---------------- Reports ----------------
  { id: "report-cycle", area: "Reports", title: "How to get a labour salary report",
    words: "report salary report cycle report total cost summary labour export excel pdf",
    go: { page: "reports", tab: "labour", sub: "builder" },
    steps: [
      { say: "Choose the cycle and company.", el: "#report-cycle" },
      { say: "Press Run.", el: "button[onclick='loadReports()']" },
      { say: "Export to Excel or PDF.", el: "button[onclick=\"exportReportTable('excel')\"]" }] },
  { id: "report-stock", area: "Reports", title: "How to print a stock report",
    words: "stock report current stock print export materials at site consumption",
    go: { page: "reports", tab: "storerep", sub: "stock" },
    steps: [
      { say: "Pick the report on the tabs above (current stock, at sites, consumption...)." },
      { say: "Export to PDF or Excel.", el: "button[onclick=\"exportStore('pdf')\"]" }] },

  // ---------------- Settings ----------------
  { id: "login-new", area: "Settings", title: "How to give someone a login",
    words: "login user account password new user access give permission",
    go: { page: "settings", tab: "logins" },
    steps: [
      { say: "Logins are listed here. Add a new one with a username and password.", el: "#screen-pglogins" },
      { say: "Then open the Access tab and tick the pages he may open." }] },
  { id: "petty-access", area: "Settings", title: "How to choose who sees PRO or Office petty cash",
    words: "petty cash access permission pro office site chief accountant who can see",
    go: { page: "settings", tab: "access" },
    steps: [
      { say: "Open the person's role here. Under Petty cash, tick only the boxes he may see: Site, PRO or Office.", el: "#screen-pgaccess" },
      { say: "Save. He sees only those boxes; the others are hidden and locked." }] },
  { id: "password", area: "Settings", title: "How to change my password",
    words: "change password forgot reset my password",
    go: { page: "settings", tab: "general" },
    steps: [
      { say: "Type your current password.", el: "#pw-current" },
      { say: "Type the new password.", el: "#pw-new" },
      { say: "Press Change Password.", el: "button[onclick='changePassword()']" }] },
  { id: "backup", area: "Settings", title: "How to take a backup",
    words: "backup back up restore download save data copy",
    go: { page: "settings", tab: "general" },
    steps: [{ say: "Press 'Take Backup Now'. It appears in the list to download.", el: "button[onclick='takeBackupNow()']" }] },
];

// Words people use that mean the same thing. Left side -> added to the search.
window.HELP_SAME = {
  fired: "terminate", sack: "terminate", sacked: "terminate", quit: "resign", resigned: "resign",
  left: "leaving", exit: "leaving", cancel: "leaving", absconded: "leaving", abscond: "leaving",
  buy: "lpo purchase", order: "lpo purchase", po: "lpo", vendor: "supplier", shop: "supplier",
  wage: "salary", wages: "salary", pay: "salary", payslip: "cards", slip: "cards",
  raise: "increment", hike: "increment", increase: "increment",
  holiday: "holiday", eid: "holiday", off: "holiday",
  visa: "expiry", passport: "expiry", mulkiya: "vehicle", car: "vehicle",
  transfer: "move", shift: "move", issue: "move", send: "move",
  broken: "damaged", stolen: "lost", missing: "lost",
  inventory: "stock", balance: "stock", qty: "stock",
  new: "add", create: "add", enter: "add", joiner: "add",
  bonus: "addition", fine: "deduction", cut: "deduction",
};

window.HELP_TIPS = {
  "#md-emp-paytype": "Daily wage: paid for each day worked. Fixed monthly: the full month's salary, less a day for each absence.",
  "#md-emp-basic": "Basic salary is used for gratuity and leave pay. Total salary is what he earns in a month.",
  "#md-rate-from": "Only matters when you change the salary. The new salary starts from the cycle you pick; older months keep the old salary.",
  "#md-emp-terminated": "Only for someone who has left. He is paid up to this day and comes off the list from the next cycle.",
  "#it-type": "Consumable: used up (cement, paint). Asset: a tool or machine that comes back to the store.",
  "#it-reorder": "The app warns you when stock goes under this number.",
  "#hr-loan-instalment": "The amount taken from his salary every month. 0 means it is not taken from salary.",
  "#fs-nreq": "Days of notice his contract asks for. If he served less, the difference is taken off.",
  "#hr-doc-within": "Show only documents expiring within this many days.",
  "#out-from": "Central store, or a site if the material is moving site to site.",
  "#mr-urgency": "Urgent requests show first for the office.",
};

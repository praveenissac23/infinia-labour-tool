// Written by tests/help_screens.js - one guide for every screen, its buttons numbered. Do not edit by hand.
window.HELP_AUTO = [
 {
  "id": "scr-dashboard-dashboard",
  "area": "Every screen",
  "title": "Dashboard",
  "auto": true,
  "words": "dashboard     screen buttons what is",
  "go": {
   "page": "dashboard",
   "tab": "dashboard"
  },
  "steps": [
   {
    "say": "This is Dashboard. The numbers on the picture match the list below."
   },
   {
    "say": "1. ◀.",
    "el": "button[onclick=\"shiftCalendarCycle('dash', -1)\"]"
   },
   {
    "say": "2. ▶.",
    "el": "button[onclick=\"shiftCalendarCycle('dash', 1)\"]"
   }
  ]
 },
 {
  "id": "scr-attendance-attendance",
  "area": "Every screen",
  "title": "Attendance > Daily attendance",
  "auto": true,
  "words": "attendance   daily attendance apply to ticked select all select none unfilled emp  71  clear day daily report     screen buttons what is",
  "go": {
   "page": "attendance",
   "tab": "attendance"
  },
  "steps": [
   {
    "say": "This is Attendance > Daily attendance. The numbers on the picture match the list below."
   },
   {
    "say": "1. Apply to Ticked.",
    "el": "button[onclick=\"applyBulk()\"]"
   },
   {
    "say": "2. Select All.",
    "el": "button[onclick=\"selectAll()\"]"
   },
   {
    "say": "3. Select None.",
    "el": "button[onclick=\"selectNone()\"]"
   },
   {
    "say": "4. Unfilled Emp (71).",
    "el": "#unfilled-btn"
   },
   {
    "say": "5. Clear Day.",
    "el": "button[onclick=\"openClearDayModal()\"]"
   },
   {
    "say": "6. Daily report: Present, absent, sick, site-wise numbers or names for the date above.",
    "el": "#daily-report-btn"
   },
   {
    "say": "7. ◀.",
    "el": "button[onclick=\"shiftCalendarCycle('attendance', -1)\"]"
   },
   {
    "say": "8. ▶.",
    "el": "button[onclick=\"shiftCalendarCycle('attendance', 1)\"]"
   }
  ]
 },
 {
  "id": "scr-attendance-livecard",
  "area": "Every screen",
  "title": "Attendance > Live card",
  "auto": true,
  "words": "attendance   live card preview export pdf export excel screen buttons what is",
  "go": {
   "page": "attendance",
   "tab": "livecard"
  },
  "steps": [
   {
    "say": "This is Attendance > Live card. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportLiveCard('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportLiveCard('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportLiveCard('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-attendance-masterdata",
  "area": "Every screen",
  "title": "Attendance > Labour master data",
  "auto": true,
  "words": "attendance   labour master data save employee clear generate template import data preview export master data edit remove screen buttons what is",
  "go": {
   "page": "attendance",
   "tab": "masterdata"
  },
  "steps": [
   {
    "say": "This is Attendance > Labour master data. The numbers on the picture match the list below."
   },
   {
    "say": "1. Save Employee: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"saveEmployee()\"]"
   },
   {
    "say": "2. Clear.",
    "el": "button[onclick=\"document.getElementById('md-emp-terminated').value=''\"]"
   },
   {
    "say": "3. Generate Template.",
    "el": "button[onclick=\"downloadEmployeeTemplate()\"]"
   },
   {
    "say": "4. Import Data."
   },
   {
    "say": "5. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewWorkforce()\"]"
   },
   {
    "say": "6. Export Master Data.",
    "el": "button[onclick=\"exportEmployeeData()\"]"
   },
   {
    "say": "7. Edit: change what is there.",
    "el": "button[onclick=\"editEmployee('D-01')\"]"
   },
   {
    "say": "8. Remove: removes it (it asks first).",
    "el": "button[onclick=\"removeEmployee('D-01', 'MOHAMED SALIM')\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-labourpay-combine",
  "area": "Every screen",
  "title": "Payroll > Labour payroll > Salary cards",
  "auto": true,
  "words": "payroll   labour payroll   salary cards pay full salary now preview combine to excel combine to pdf separate excel files separate pdf files export pdf export excel screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "labourpay",
   "sub": "combine"
  },
  "steps": [
   {
    "say": "This is Payroll > Labour payroll > Salary cards. The numbers on the picture match the list below."
   },
   {
    "say": "1. Pay full salary now.",
    "el": "#lab-full-btn"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportCombineCards('view')\"]"
   },
   {
    "say": "3. Combine to Excel.",
    "el": "button[onclick=\"exportCombineCards('excel')\"]"
   },
   {
    "say": "4. Combine to PDF.",
    "el": "button[onclick=\"exportCombineCards('pdf')\"]"
   },
   {
    "say": "5. Separate Excel Files.",
    "el": "button[onclick=\"exportCombineCards('excel-separate')\"]"
   },
   {
    "say": "6. Separate PDF Files.",
    "el": "button[onclick=\"exportCombineCards('pdf-separate')\"]"
   },
   {
    "say": "7. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportOneWorker('pdf')\"]"
   },
   {
    "say": "8. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportOneWorker('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-labourpay-adjust",
  "area": "Every screen",
  "title": "Payroll > Labour payroll > Additions & deductions",
  "auto": true,
  "words": "payroll   labour payroll   additions   deductions load screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "labourpay",
   "sub": "adjust"
  },
  "steps": [
   {
    "say": "This is Payroll > Labour payroll > Additions & deductions. The numbers on the picture match the list below."
   },
   {
    "say": "1. Load.",
    "el": "button[onclick=\"loadAdjustmentsList()\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-labourpay-errorcheck",
  "area": "Every screen",
  "title": "Payroll > Labour payroll > Check before you pay",
  "auto": true,
  "words": "payroll   labour payroll   check before you pay run check tick all unfilled untick all preview reminder pdf reminder excel screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "labourpay",
   "sub": "errorcheck"
  },
  "steps": [
   {
    "say": "This is Payroll > Labour payroll > Check before you pay. The numbers on the picture match the list below."
   },
   {
    "say": "1. Run Check.",
    "el": "button[onclick=\"loadErrorCheck()\"]"
   },
   {
    "say": "2. Tick all unfilled.",
    "el": "button[onclick=\"tickAllUnfilled(true)\"]"
   },
   {
    "say": "3. Untick all.",
    "el": "button[onclick=\"tickAllUnfilled(false)\"]"
   },
   {
    "say": "4. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"sendAttendanceNeeded('view')\"]"
   },
   {
    "say": "5. Reminder PDF.",
    "el": "button[onclick=\"sendAttendanceNeeded('pdf')\"]"
   },
   {
    "say": "6. Reminder Excel.",
    "el": "button[onclick=\"sendAttendanceNeeded('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-cycle",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Salary cycle & statements",
  "auto": true,
  "words": "payroll   office payroll   salary cycle   statements office staff local staff pay full month now preview export pdf export excel consolidated statement  office   local  approve   lock screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "hrpayroll",
   "sub": "cycle"
  },
  "steps": [
   {
    "say": "This is Payroll > Office payroll > Salary cycle & statements. The numbers on the picture match the list below."
   },
   {
    "say": "1. Office staff.",
    "el": "button[onclick=\"hrPickGroup('staff')\"]"
   },
   {
    "say": "2. Local staff.",
    "el": "button[onclick=\"hrPickGroup('local')\"]"
   },
   {
    "say": "3. Pay full month now.",
    "el": "button[onclick=\"hrFullMonth()\"]"
   },
   {
    "say": "4. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewConsolidated()\"]"
   },
   {
    "say": "5. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadConsolidated('pdf')\"]"
   },
   {
    "say": "6. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadConsolidated('excel')\"]"
   },
   {
    "say": "7. Consolidated statement (office + local).",
    "el": "button[onclick=\"previewConsolidated(true)\"]"
   },
   {
    "say": "8. Approve & lock: approves it.",
    "el": "button[onclick=\"hrAllUse(3); approvePayrollRun()\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-leave",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Absence",
  "auto": true,
  "words": "payroll   office payroll   absence record preview export pdf export excel screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "hrpayroll",
   "sub": "leave"
  },
  "steps": [
   {
    "say": "This is Payroll > Office payroll > Absence. The numbers on the picture match the list below."
   },
   {
    "say": "1. Record.",
    "el": "#hr-leave-save"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('leave')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('leave','pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('leave','excel')\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-items",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Additions & deductions",
  "auto": true,
  "words": "payroll   office payroll   additions   deductions addition   deduction   add preview export pdf export excel screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "hrpayroll",
   "sub": "items"
  },
  "steps": [
   {
    "say": "This is Payroll > Office payroll > Additions & deductions. The numbers on the picture match the list below."
   },
   {
    "say": "1. Addition (+)."
   },
   {
    "say": "2. Deduction (-)."
   },
   {
    "say": "3. Add.",
    "el": "#hr-item-save"
   },
   {
    "say": "4. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('items')\"]"
   },
   {
    "say": "5. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('items','pdf')\"]"
   },
   {
    "say": "6. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('items','excel')\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-loans",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Loans",
  "auto": true,
  "words": "payroll   office payroll   loans record loan preview export pdf export excel history edit screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "hrpayroll",
   "sub": "loans"
  },
  "steps": [
   {
    "say": "This is Payroll > Office payroll > Loans. The numbers on the picture match the list below."
   },
   {
    "say": "1. Record loan.",
    "el": "#hr-loan-save"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('loans')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('loans','pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('loans','excel')\"]"
   },
   {
    "say": "5. History.",
    "el": "button[onclick=\"hrLoanToggle(1)\"]"
   },
   {
    "say": "6. Edit: change what is there.",
    "el": "button[onclick=\"hrLoanEdit(1)\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-staff",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Staff register",
  "auto": true,
  "words": "payroll   office payroll   staff register all companies infinia prime infinia preview export pdf export excel   new staff screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "hrpayroll",
   "sub": "staff"
  },
  "steps": [
   {
    "say": "This is Payroll > Office payroll > Staff register. The numbers on the picture match the list below."
   },
   {
    "say": "1. All companies."
   },
   {
    "say": "2. Infinia."
   },
   {
    "say": "3. Prime Infinia."
   },
   {
    "say": "4. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('staff')\"]"
   },
   {
    "say": "5. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('staff','pdf')\"]"
   },
   {
    "say": "6. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('staff','excel')\"]"
   },
   {
    "say": "7. + New staff: adds a new staff.",
    "el": "button[onclick=\"hrNewStaff()\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-increments",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Increments",
  "auto": true,
  "words": "payroll   office payroll   increments record increment preview export pdf export excel edit screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "hrpayroll",
   "sub": "increments"
  },
  "steps": [
   {
    "say": "This is Payroll > Office payroll > Increments. The numbers on the picture match the list below."
   },
   {
    "say": "1. Record increment.",
    "el": "button[onclick=\"addIncrement()\"]"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('increments')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('increments','pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('increments','excel')\"]"
   },
   {
    "say": "5. Edit: change what is there.",
    "el": "button[onclick=\"hrIncEdit(1)\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-gratuity",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Gratuity",
  "auto": true,
  "words": "payroll   office payroll   gratuity preview export pdf export excel screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "hrpayroll",
   "sub": "gratuity"
  },
  "steps": [
   {
    "say": "This is Payroll > Office payroll > Gratuity. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('gratuity')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('gratuity','pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('gratuity','excel')\"]"
   }
  ]
 },
 {
  "id": "scr-expiry-expiry-people",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > People",
  "auto": true,
  "words": "expiry reminder   expiry reminder   people 1expiredpeople   renew now 4due in 7 dayspeople   start renewal 1due in 8 to 30 dayspeople   plan ahead save document preview export pdf export excel screen buttons what is",
  "go": {
   "page": "expiry",
   "tab": "expiry",
   "sub": "people"
  },
  "steps": [
   {
    "say": "This is Expiry Reminder > Expiry reminder > People. The numbers on the picture match the list below."
   },
   {
    "say": "1. 1Expiredpeople - renew now.",
    "el": "button[onclick=\"expCard('expired')\"]"
   },
   {
    "say": "2. 4Due in 7 dayspeople - start renewal.",
    "el": "button[onclick=\"expCard('week')\"]"
   },
   {
    "say": "3. 1Due in 8 to 30 dayspeople - plan ahead.",
    "el": "button[onclick=\"expCard('month')\"]"
   },
   {
    "say": "4. Save document: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"addDocument()\"]"
   },
   {
    "say": "5. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('documents')\"]"
   },
   {
    "say": "6. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('documents','pdf')\"]"
   },
   {
    "say": "7. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('documents','excel')\"]"
   }
  ]
 },
 {
  "id": "scr-expiry-expiry-company",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > Company & other documents",
  "auto": true,
  "words": "expiry reminder   expiry reminder   company   other documents 3expireddocuments   renew now 1due in 7 daysdocuments   start renewal save preview export pdf export excel screen buttons what is",
  "go": {
   "page": "expiry",
   "tab": "expiry",
   "sub": "company"
  },
  "steps": [
   {
    "say": "This is Expiry Reminder > Expiry reminder > Company & other documents. The numbers on the picture match the list below."
   },
   {
    "say": "1. 3Expireddocuments - renew now.",
    "el": "button[onclick=\"expCard('expired')\"]"
   },
   {
    "say": "2. 1Due in 7 daysdocuments - start renewal.",
    "el": "button[onclick=\"expCard('week')\"]"
   },
   {
    "say": "3. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"saveExpiry()\"]"
   },
   {
    "say": "4. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"hrExpExport('view')\"]"
   },
   {
    "say": "5. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"hrExpExport('pdf')\"]"
   },
   {
    "say": "6. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"hrExpExport('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-expiry-expiry-pdc",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > PDCs",
  "auto": true,
  "words": "expiry reminder   expiry reminder   pdcs 0overduenothing overdue 0due in 7 daysnothing this week 1due in 8 to 14 daysaed 48 596 10 21all to be paidaed 2 189 468 73 18date to fillaed 1 800 282 63 add monthly tracker cheque list preview export pdf export excel screen buttons what is",
  "go": {
   "page": "expiry",
   "tab": "expiry",
   "sub": "pdc"
  },
  "steps": [
   {
    "say": "This is Expiry Reminder > Expiry reminder > PDCs. The numbers on the picture match the list below."
   },
   {
    "say": "1. 0Overduenothing overdue.",
    "el": "button[onclick=\"pdcCard('overdue')\"]"
   },
   {
    "say": "2. 0Due in 7 daysnothing this week.",
    "el": "button[onclick=\"pdcCard('week')\"]"
   },
   {
    "say": "3. 1Due in 8 to 14 daysAED 48,596.10.",
    "el": "button[onclick=\"pdcCard('fortnight')\"]"
   },
   {
    "say": "4. 21All to be paidAED 2,189,468.73.",
    "el": "button[onclick=\"pdcCard('pending')\"]"
   },
   {
    "say": "5. 18Date to fillAED 1,800,282.63.",
    "el": "button[onclick=\"pdcCard('nodate')\"]"
   },
   {
    "say": "6. Add.",
    "el": "#pdc-save"
   },
   {
    "say": "7. Monthly tracker.",
    "el": "button[onclick=\"pdcView('grid')\"]"
   },
   {
    "say": "8. Cheque list.",
    "el": "button[onclick=\"pdcView('list')\"]"
   },
   {
    "say": "9. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pdcExport('view')\"]"
   },
   {
    "say": "10. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pdcExport('pdf')\"]"
   },
   {
    "say": "11. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pdcExport('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-taxinv",
  "area": "Every screen",
  "title": "Accounts > Tax Invoice",
  "auto": true,
  "words": "accounts   tax invoice   add line save   open pdf save clear screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "taxinv"
  },
  "steps": [
   {
    "say": "This is Accounts > Tax Invoice. The numbers on the picture match the list below."
   },
   {
    "say": "1. + Add line: adds a new add line.",
    "el": "button[onclick=\"invAddLine()\"]"
   },
   {
    "say": "2. Save & open PDF: keeps what you entered - nothing is kept until you press it.",
    "el": "#inv-save-pdf"
   },
   {
    "say": "3. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "#inv-save"
   },
   {
    "say": "4. Clear.",
    "el": "#inv-clear"
   }
  ]
 },
 {
  "id": "scr-accounts-proforma",
  "area": "Every screen",
  "title": "Accounts > Proforma Invoice",
  "auto": true,
  "words": "accounts   proforma invoice   add line save   open pdf save clear screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "proforma"
  },
  "steps": [
   {
    "say": "This is Accounts > Proforma Invoice. The numbers on the picture match the list below."
   },
   {
    "say": "1. + Add line: adds a new add line.",
    "el": "button[onclick=\"invAddLine()\"]"
   },
   {
    "say": "2. Save & open PDF: keeps what you entered - nothing is kept until you press it.",
    "el": "#inv-save-pdf"
   },
   {
    "say": "3. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "#inv-save"
   },
   {
    "say": "4. Clear.",
    "el": "#inv-clear"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-site",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Site",
  "auto": true,
  "words": "accounts   petty cash   site preview export pdf export excel bill paid cash received add edit remove screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "petty",
   "sub": "site"
  },
  "steps": [
   {
    "say": "This is Accounts > Petty cash > Site. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pcExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pcExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pcExport('excel')\"]"
   },
   {
    "say": "4. Bill paid.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "5. Cash received.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "6. Add.",
    "el": "#pc-save"
   },
   {
    "say": "7. Edit: change what is there.",
    "el": "button[onclick=\"pcEdit(1)\"]"
   },
   {
    "say": "8. Remove: removes it (it asks first).",
    "el": "button[onclick=\"pcDelete(1)\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-pro",
  "area": "Every screen",
  "title": "Accounts > Petty cash > PRO",
  "auto": true,
  "words": "accounts   petty cash   pro preview export pdf export excel bill paid cash received add edit remove screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "petty",
   "sub": "pro"
  },
  "steps": [
   {
    "say": "This is Accounts > Petty cash > PRO. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pcExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pcExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pcExport('excel')\"]"
   },
   {
    "say": "4. Bill paid.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "5. Cash received.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "6. Add.",
    "el": "#pc-save"
   },
   {
    "say": "7. Edit: change what is there.",
    "el": "button[onclick=\"pcEdit(4)\"]"
   },
   {
    "say": "8. Remove: removes it (it asks first).",
    "el": "button[onclick=\"pcDelete(4)\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-office",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Office",
  "auto": true,
  "words": "accounts   petty cash   office preview export pdf export excel bill paid cash received add edit remove screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "petty",
   "sub": "office"
  },
  "steps": [
   {
    "say": "This is Accounts > Petty cash > Office. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pcExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pcExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pcExport('excel')\"]"
   },
   {
    "say": "4. Bill paid.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "5. Cash received.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "6. Add.",
    "el": "#pc-save"
   },
   {
    "say": "7. Edit: change what is there.",
    "el": "button[onclick=\"pcEdit(6)\"]"
   },
   {
    "say": "8. Remove: removes it (it asks first).",
    "el": "button[onclick=\"pcDelete(6)\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-naveen",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Naveen",
  "auto": true,
  "words": "accounts   petty cash   naveen preview export pdf export excel paid by naveen repaid to naveen add screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "petty",
   "sub": "naveen"
  },
  "steps": [
   {
    "say": "This is Accounts > Petty cash > Naveen. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pcExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pcExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pcExport('excel')\"]"
   },
   {
    "say": "4. Paid by Naveen.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "5. Repaid to Naveen.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "6. Add.",
    "el": "#pc-save"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-praveen",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Praveen",
  "auto": true,
  "words": "accounts   petty cash   praveen preview export pdf export excel paid by praveen repaid to praveen add screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "petty",
   "sub": "praveen"
  },
  "steps": [
   {
    "say": "This is Accounts > Petty cash > Praveen. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pcExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pcExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pcExport('excel')\"]"
   },
   {
    "say": "4. Paid by Praveen.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "5. Repaid to Praveen.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "6. Add.",
    "el": "#pc-save"
   }
  ]
 },
 {
  "id": "scr-accounts-projects",
  "area": "Every screen",
  "title": "Accounts > Project payments",
  "auto": true,
  "words": "accounts   project payments preview export pdf export excel   add scope screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "projects"
  },
  "steps": [
   {
    "say": "This is Accounts > Project payments. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"ppExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"ppExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"ppExport('excel')\"]"
   },
   {
    "say": "4. + Add scope: adds a new add scope.",
    "el": "button[onclick=\"ppNew()\"]"
   }
  ]
 },
 {
  "id": "scr-store-store-home",
  "area": "Every screen",
  "title": "Store & Purchasing > Stock > Stock on hand",
  "auto": true,
  "words": "store   purchasing   stock   stock on hand  screen buttons what is",
  "go": {
   "page": "store",
   "tab": "store",
   "sub": "home"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Stock > Stock on hand. The numbers on the picture match the list below."
   }
  ]
 },
 {
  "id": "scr-store-store-give",
  "area": "Every screen",
  "title": "Store & Purchasing > Stock > Move material",
  "auto": true,
  "words": "store   purchasing   stock   move material remove   add another material give out to a site screen buttons what is",
  "go": {
   "page": "store",
   "tab": "store",
   "sub": "give"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Stock > Move material. The numbers on the picture match the list below."
   },
   {
    "say": "1. Remove: removes it (it asks first).",
    "el": "button[onclick=\"removeEntryRow(this,'out-lines')\"]"
   },
   {
    "say": "2. + Add another material: adds a new add another material.",
    "el": "button[onclick=\"addOutLine()\"]"
   },
   {
    "say": "3. Give out to a site.",
    "el": "#out-save-btn"
   }
  ]
 },
 {
  "id": "scr-store-store-arrive",
  "area": "Every screen",
  "title": "Store & Purchasing > Stock > Material arrived",
  "auto": true,
  "words": "store   purchasing   stock   material arrived record delivery record a direct purchase screen buttons what is",
  "go": {
   "page": "store",
   "tab": "store",
   "sub": "arrive"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Stock > Material arrived. The numbers on the picture match the list below."
   },
   {
    "say": "1. Record delivery.",
    "el": "button[onclick=\"event.stopPropagation(); openReceive(1)\"]"
   },
   {
    "say": "2. Record a direct purchase.",
    "el": "button[onclick=\"goDirectPurchase()\"]"
   }
  ]
 },
 {
  "id": "scr-store-store-other",
  "area": "Every screen",
  "title": "Store & Purchasing > Stock > Returns, lost & corrections",
  "auto": true,
  "words": "store   purchasing   stock   returns  lost   corrections  screen buttons what is",
  "go": {
   "page": "store",
   "tab": "store",
   "sub": "other"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Stock > Returns, lost & corrections. The numbers on the picture match the list below."
   }
  ]
 },
 {
  "id": "scr-store-store-items",
  "area": "Every screen",
  "title": "Store & Purchasing > Stock > Material list",
  "auto": true,
  "words": "store   purchasing   stock   material list check all materials remove   add another material add stock screen buttons what is",
  "go": {
   "page": "store",
   "tab": "store",
   "sub": "items"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Stock > Material list. The numbers on the picture match the list below."
   },
   {
    "say": "1. Check all materials.",
    "el": "button[onclick=\"loadUnitSuggestions()\"]"
   },
   {
    "say": "2. Remove: removes it (it asks first).",
    "el": "button[onclick=\"removeEntryRow(this,'opening-lines')\"]"
   },
   {
    "say": "3. + Add another material: adds a new add another material.",
    "el": "button[onclick=\"addOpeningLine()\"]"
   },
   {
    "say": "4. Add stock.",
    "el": "#op-save-btn"
   }
  ]
 },
 {
  "id": "scr-store-rentals-hire",
  "area": "Every screen",
  "title": "Store & Purchasing > Rentals > On rent",
  "auto": true,
  "words": "store   purchasing   rentals   on rent   add line book in as rented preview export pdf export excel screen buttons what is",
  "go": {
   "page": "store",
   "tab": "rentals",
   "sub": "hire"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Rentals > On rent. The numbers on the picture match the list below."
   },
   {
    "say": "1. ×.",
    "el": "button[onclick=\"removeEntryRow(this,'hin-lines')\"]"
   },
   {
    "say": "2. Add line.",
    "el": "button[onclick=\"addHireInLine()\"]"
   },
   {
    "say": "3. Book in as rented.",
    "el": "button[onclick=\"saveHireIn()\"]"
   },
   {
    "say": "4. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportRental('view')\"]"
   },
   {
    "say": "5. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportRental('pdf')\"]"
   },
   {
    "say": "6. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportRental('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-store-rentals-returns",
  "area": "Every screen",
  "title": "Store & Purchasing > Rentals > Return notes",
  "auto": true,
  "words": "store   purchasing   rentals   return notes new return note screen buttons what is",
  "go": {
   "page": "store",
   "tab": "rentals",
   "sub": "returns"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Rentals > Return notes. The numbers on the picture match the list below."
   },
   {
    "say": "1. New return note.",
    "el": "button[onclick=\"newReturnNote()\"]"
   }
  ]
 },
 {
  "id": "scr-store-requests-requests",
  "area": "Every screen",
  "title": "Store & Purchasing > Requests > Material requests",
  "auto": true,
  "words": "store   purchasing   requests   material requests direct purchase  no request  remove   add another material send request to office screen buttons what is",
  "go": {
   "page": "store",
   "tab": "requests",
   "sub": "requests"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Requests > Material requests. The numbers on the picture match the list below."
   },
   {
    "say": "1. Direct purchase (no request).",
    "el": "button[onclick=\"toggleDirectPurchase()\"]"
   },
   {
    "say": "2. Remove: removes it (it asks first).",
    "el": "button[onclick=\"removeEntryRow(this,'mr-lines')\"]"
   },
   {
    "say": "3. + Add another material: adds a new add another material.",
    "el": "button[onclick=\"addMrLine()\"]"
   },
   {
    "say": "4. Send Request to Office.",
    "el": "#mr-send-btn"
   }
  ]
 },
 {
  "id": "scr-store-requests-approvals",
  "area": "Every screen",
  "title": "Store & Purchasing > Requests > Approvals",
  "auto": true,
  "words": "store   purchasing   requests   approvals refresh preview export pdf export excel approve raise lpo screen buttons what is",
  "go": {
   "page": "store",
   "tab": "requests",
   "sub": "approvals"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Requests > Approvals. The numbers on the picture match the list below."
   },
   {
    "say": "1. Refresh: loads the latest figures.",
    "el": "button[onclick=\"loadRequests()\"]"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportRequests('view')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportRequests('pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportRequests('excel')\"]"
   },
   {
    "say": "5. Approve: approves it.",
    "el": "button[onclick=\"event.stopPropagation(); setRequestStatus(2,'approved')\"]"
   },
   {
    "say": "6. Raise LPO: Raise the LPO - this material is waiting there.",
    "el": "button[onclick=\"event.stopPropagation(); switchScreen('purchase')\"]"
   }
  ]
 },
 {
  "id": "scr-store-requests-followup",
  "area": "Every screen",
  "title": "Store & Purchasing > Requests > Order follow-up",
  "auto": true,
  "words": "store   purchasing   requests   order follow up refresh screen buttons what is",
  "go": {
   "page": "store",
   "tab": "requests",
   "sub": "followup"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Requests > Order follow-up. The numbers on the picture match the list below."
   },
   {
    "say": "1. Refresh: loads the latest figures.",
    "el": "button[onclick=\"loadFollowUp()\"]"
   }
  ]
 },
 {
  "id": "scr-store-purchasing-purchase",
  "area": "Every screen",
  "title": "Store & Purchasing > Purchasing > Purchase orders",
  "auto": true,
  "words": "store   purchasing   purchasing   purchase orders new purchase order generate lpo from ticked screen buttons what is",
  "go": {
   "page": "store",
   "tab": "purchasing",
   "sub": "purchase"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Purchasing > Purchase orders. The numbers on the picture match the list below."
   },
   {
    "say": "1. New Purchase Order.",
    "el": "button[onclick=\"newLpo()\"]"
   },
   {
    "say": "2. Generate LPO from ticked.",
    "el": "button[onclick=\"lpoFromTicked()\"]"
   }
  ]
 },
 {
  "id": "scr-store-purchasing-lporegister",
  "area": "Every screen",
  "title": "Store & Purchasing > Purchasing > LPO register",
  "auto": true,
  "words": "store   purchasing   purchasing   lpo register preview export pdf export excel screen buttons what is",
  "go": {
   "page": "store",
   "tab": "purchasing",
   "sub": "lporegister"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Purchasing > LPO register. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportLpoReport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportLpoReport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportLpoReport('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-store-purchasing-suppliers",
  "area": "Every screen",
  "title": "Store & Purchasing > Purchasing > Suppliers",
  "auto": true,
  "words": "store   purchasing   purchasing   suppliers preview export excel template import save screen buttons what is",
  "go": {
   "page": "store",
   "tab": "purchasing",
   "sub": "suppliers"
  },
  "steps": [
   {
    "say": "This is Store & Purchasing > Purchasing > Suppliers. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewSuppliers()\"]"
   },
   {
    "say": "2. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportSuppliers()\"]"
   },
   {
    "say": "3. Template.",
    "el": "button[onclick=\"supplierTemplate()\"]"
   },
   {
    "say": "4. Import.",
    "el": "button[onclick=\"importSuppliers()\"]"
   },
   {
    "say": "5. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"saveSupplier()\"]"
   }
  ]
 },
 {
  "id": "scr-reports-labour-builder",
  "area": "Every screen",
  "title": "Reports > Labour > Cycle report builder",
  "auto": true,
  "words": "reports   labour   cycle report builder run preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "labour",
   "sub": "builder"
  },
  "steps": [
   {
    "say": "This is Reports > Labour > Cycle report builder. The numbers on the picture match the list below."
   },
   {
    "say": "1. Run.",
    "el": "button[onclick=\"loadReports()\"]"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportReportTable('view')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportReportTable('pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportReportTable('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-labour-monthly",
  "area": "Every screen",
  "title": "Reports > Labour > Monthly report",
  "auto": true,
  "words": "reports   labour   monthly report save notes preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "labour",
   "sub": "monthly"
  },
  "steps": [
   {
    "say": "This is Reports > Labour > Monthly report. The numbers on the picture match the list below."
   },
   {
    "say": "1. Save notes: keeps what you entered - nothing is kept until you press it - Notes also save on their own as you leave each box.",
    "el": "button[onclick=\"saveAllMonthlyNotes()\"]"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportReportTable('view')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportReportTable('pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportReportTable('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-labour-cards",
  "area": "Every screen",
  "title": "Reports > Labour > Salary cards",
  "auto": true,
  "words": "reports   labour   salary cards pay full salary now preview combine to excel combine to pdf separate excel files separate pdf files export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "labour",
   "sub": "cards"
  },
  "steps": [
   {
    "say": "This is Reports > Labour > Salary cards. The numbers on the picture match the list below."
   },
   {
    "say": "1. Pay full salary now.",
    "el": "#lab-full-btn"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportCombineCards('view')\"]"
   },
   {
    "say": "3. Combine to Excel.",
    "el": "button[onclick=\"exportCombineCards('excel')\"]"
   },
   {
    "say": "4. Combine to PDF.",
    "el": "button[onclick=\"exportCombineCards('pdf')\"]"
   },
   {
    "say": "5. Separate Excel Files.",
    "el": "button[onclick=\"exportCombineCards('excel-separate')\"]"
   },
   {
    "say": "6. Separate PDF Files.",
    "el": "button[onclick=\"exportCombineCards('pdf-separate')\"]"
   },
   {
    "say": "7. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportOneWorker('pdf')\"]"
   },
   {
    "say": "8. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportOneWorker('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-labour-leavereport",
  "area": "Every screen",
  "title": "Reports > Labour > Leave report",
  "auto": true,
  "words": "reports   labour   leave report labour office local preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "labour",
   "sub": "leavereport"
  },
  "steps": [
   {
    "say": "This is Reports > Labour > Leave report. The numbers on the picture match the list below."
   },
   {
    "say": "1. Labour."
   },
   {
    "say": "2. Office."
   },
   {
    "say": "3. Local."
   },
   {
    "say": "4. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pgRepOpen()\"]"
   },
   {
    "say": "5. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pgRepDownload('pdf')\"]"
   },
   {
    "say": "6. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pgRepDownload('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-stock",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > Current stock",
  "auto": true,
  "words": "reports   store   purchasing   current stock preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "stock"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > Current stock. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-by_site",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > At sites",
  "auto": true,
  "words": "reports   store   purchasing   at sites preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "by_site"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > At sites. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-usage",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > Issued to sites",
  "auto": true,
  "words": "reports   store   purchasing   issued to sites preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "usage"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > Issued to sites. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-site_cost",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > Site costs",
  "auto": true,
  "words": "reports   store   purchasing   site costs preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "site_cost"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > Site costs. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-assets",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > Assets",
  "auto": true,
  "words": "reports   store   purchasing   assets preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "assets"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > Assets. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-issues",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > Tools & equipment out",
  "auto": true,
  "words": "reports   store   purchasing   tools   equipment out preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "issues"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > Tools & equipment out. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-lost",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > Lost / damaged",
  "auto": true,
  "words": "reports   store   purchasing   lost   damaged preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "lost"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > Lost / damaged. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-hired",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > On rent",
  "auto": true,
  "words": "reports   store   purchasing   on rent preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "hired"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > On rent. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-reports-storerep-mr_history",
  "area": "Every screen",
  "title": "Reports > Store & purchasing > Requests",
  "auto": true,
  "words": "reports   store   purchasing   requests preview export pdf export excel screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "storerep",
   "sub": "mr_history"
  },
  "steps": [
   {
    "say": "This is Reports > Store & purchasing > Requests. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"exportStore('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"exportStore('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"exportStore('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-settings-general",
  "area": "Every screen",
  "title": "Settings > General",
  "auto": true,
  "words": "settings   general change password save upload screen buttons what is",
  "go": {
   "page": "settings",
   "tab": "general"
  },
  "steps": [
   {
    "say": "This is Settings > General. The numbers on the picture match the list below."
   },
   {
    "say": "1. Change Password.",
    "el": "button[onclick=\"changePassword()\"]"
   },
   {
    "say": "2. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"saveCompanySettings()\"]"
   },
   {
    "say": "3. Upload.",
    "el": "button[onclick=\"uploadSignature('lpo')\"]"
   }
  ]
 },
 {
  "id": "scr-settings-companies",
  "area": "Every screen",
  "title": "Settings > Companies & sites",
  "auto": true,
  "words": "settings   companies   sites   add company edit   add site remove   add engineer screen buttons what is",
  "go": {
   "page": "settings",
   "tab": "companies"
  },
  "steps": [
   {
    "say": "This is Settings > Companies & sites. The numbers on the picture match the list below."
   },
   {
    "say": "1. + Add company: adds a new add company.",
    "el": "button[onclick=\"coOpen()\"]"
   },
   {
    "say": "2. Edit: change what is there.",
    "el": "button[onclick=\"coEdit(1)\"]"
   },
   {
    "say": "3. + Add site: adds a new add site.",
    "el": "button[onclick=\"mdSiteForm(true)\"]"
   },
   {
    "say": "4. Remove: removes it (it asks first).",
    "el": "button[onclick=\"removeSite(5, '901')\"]"
   },
   {
    "say": "5. + Add engineer: adds a new add engineer.",
    "el": "button[onclick=\"mdEngForm(true)\"]"
   }
  ]
 },
 {
  "id": "scr-settings-logins",
  "area": "Every screen",
  "title": "Settings > Logins",
  "auto": true,
  "words": "settings   logins   new login reset password change role delete screen buttons what is",
  "go": {
   "page": "settings",
   "tab": "logins"
  },
  "steps": [
   {
    "say": "This is Settings > Logins. The numbers on the picture match the list below."
   },
   {
    "say": "1. + New login: adds a new login."
   },
   {
    "say": "2. Reset password."
   },
   {
    "say": "3. Change role."
   },
   {
    "say": "4. Delete: removes it (it asks first)."
   }
  ]
 },
 {
  "id": "scr-settings-access",
  "area": "Every screen",
  "title": "Settings > Access",
  "auto": true,
  "words": "settings   access  screen buttons what is",
  "go": {
   "page": "settings",
   "tab": "access"
  },
  "steps": [
   {
    "say": "This is Settings > Access. The numbers on the picture match the list below."
   }
  ]
 },
 {
  "id": "scr-settings-activity",
  "area": "Every screen",
  "title": "Settings > Activity monitor",
  "auto": true,
  "words": "settings   activity monitor today 7 days 30 days all refresh everything sign ins attendance labour   salary office payroll people store screen buttons what is",
  "go": {
   "page": "settings",
   "tab": "activity"
  },
  "steps": [
   {
    "say": "This is Settings > Activity monitor. The numbers on the picture match the list below."
   },
   {
    "say": "1. Today.",
    "el": "button[onclick=\"actSet('days','1')\"]"
   },
   {
    "say": "2. 7 days.",
    "el": "button[onclick=\"actSet('days','7')\"]"
   },
   {
    "say": "3. 30 days.",
    "el": "button[onclick=\"actSet('days','30')\"]"
   },
   {
    "say": "4. All.",
    "el": "button[onclick=\"actSet('days','0')\"]"
   },
   {
    "say": "5. Refresh: loads the latest figures.",
    "el": "button[onclick=\"loadActivityLog()\"]"
   },
   {
    "say": "6. Everything.",
    "el": "button[onclick=\"actSet('group','')\"]"
   },
   {
    "say": "7. Sign-ins.",
    "el": "button[onclick=\"actSet('group','signin')\"]"
   },
   {
    "say": "8. Attendance.",
    "el": "button[onclick=\"actSet('group','attendance')\"]"
   },
   {
    "say": "9. Labour & salary.",
    "el": "button[onclick=\"actSet('group','labour')\"]"
   },
   {
    "say": "10. Office payroll.",
    "el": "button[onclick=\"actSet('group','office')\"]"
   },
   {
    "say": "11. People.",
    "el": "button[onclick=\"actSet('group','people')\"]"
   },
   {
    "say": "12. Store.",
    "el": "button[onclick=\"actSet('group','store')\"]"
   }
  ]
 },
 {
  "id": "scr-people-register",
  "area": "Every screen",
  "title": "Staff > Register",
  "auto": true,
  "words": "staff   register active all preview export pdf export excel   new person print file edit identity employment pay documents screen buttons what is",
  "go": {
   "page": "people",
   "tab": "people"
  },
  "steps": [
   {
    "say": "This is Staff > Register. The numbers on the picture match the list below.",
    "run": "var f=document.getElementById('pg-staff-frame'); if (f && f.contentWindow.showView) f.contentWindow.showView('register');"
   },
   {
    "say": "1. Active."
   },
   {
    "say": "2. All."
   },
   {
    "say": "3. Preview: opens it on screen to read or print."
   },
   {
    "say": "4. Export PDF: downloads it as a PDF."
   },
   {
    "say": "5. Export Excel: downloads it as an Excel sheet."
   },
   {
    "say": "6. + New person: adds a new person."
   },
   {
    "say": "7. Print file: prints it."
   },
   {
    "say": "8. Edit: change what is there."
   },
   {
    "say": "9. Identity."
   },
   {
    "say": "10. Employment."
   },
   {
    "say": "11. Pay."
   },
   {
    "say": "12. Documents."
   }
  ]
 },
 {
  "id": "scr-people-due",
  "area": "Every screen",
  "title": "Staff > Documents due",
  "auto": true,
  "words": "staff   documents due 30 days 90 days 180 days all registers labour office local preview export pdf export excel open screen buttons what is",
  "go": {
   "page": "people",
   "tab": "people"
  },
  "steps": [
   {
    "say": "This is Staff > Documents due. The numbers on the picture match the list below.",
    "run": "var f=document.getElementById('pg-staff-frame'); if (f && f.contentWindow.showView) f.contentWindow.showView('due');"
   },
   {
    "say": "1. 30 days."
   },
   {
    "say": "2. 90 days."
   },
   {
    "say": "3. 180 days."
   },
   {
    "say": "4. All registers."
   },
   {
    "say": "5. Labour."
   },
   {
    "say": "6. Office."
   },
   {
    "say": "7. Local."
   },
   {
    "say": "8. Preview: opens it on screen to read or print."
   },
   {
    "say": "9. Export PDF: downloads it as a PDF."
   },
   {
    "say": "10. Export Excel: downloads it as an Excel sheet."
   },
   {
    "say": "11. Open."
   }
  ]
 },
 {
  "id": "scr-people-vacation",
  "area": "Every screen",
  "title": "Staff > Leave",
  "auto": true,
  "words": "staff   leave labour office local all on leave pending approved returned   add leave preview export pdf export excel screen buttons what is",
  "go": {
   "page": "people",
   "tab": "people"
  },
  "steps": [
   {
    "say": "This is Staff > Leave. The numbers on the picture match the list below.",
    "run": "var f=document.getElementById('pg-staff-frame'); if (f && f.contentWindow.showView) f.contentWindow.showView('vacation');"
   },
   {
    "say": "1. Labour."
   },
   {
    "say": "2. Office."
   },
   {
    "say": "3. Local."
   },
   {
    "say": "4. All."
   },
   {
    "say": "5. On leave."
   },
   {
    "say": "6. Pending."
   },
   {
    "say": "7. Approved: approves it."
   },
   {
    "say": "8. Returned."
   },
   {
    "say": "9. + Add leave: adds a new add leave."
   },
   {
    "say": "10. Preview: opens it on screen to read or print."
   },
   {
    "say": "11. Export PDF: downloads it as a PDF."
   },
   {
    "say": "12. Export Excel: downloads it as an Excel sheet."
   }
  ]
 },
 {
  "id": "scr-people-bday",
  "area": "Every screen",
  "title": "Staff > Birthdays",
  "auto": true,
  "words": "staff   birthdays all registers labour office local clients   client birthday preview export pdf export excel open edit screen buttons what is",
  "go": {
   "page": "people",
   "tab": "people"
  },
  "steps": [
   {
    "say": "This is Staff > Birthdays. The numbers on the picture match the list below.",
    "run": "var f=document.getElementById('pg-staff-frame'); if (f && f.contentWindow.showView) f.contentWindow.showView('bday');"
   },
   {
    "say": "1. All registers."
   },
   {
    "say": "2. Labour."
   },
   {
    "say": "3. Office."
   },
   {
    "say": "4. Local."
   },
   {
    "say": "5. Clients."
   },
   {
    "say": "6. + Client birthday: adds a new client birthday."
   },
   {
    "say": "7. Preview: opens it on screen to read or print."
   },
   {
    "say": "8. Export PDF: downloads it as a PDF."
   },
   {
    "say": "9. Export Excel: downloads it as an Excel sheet."
   },
   {
    "say": "10. Open."
   },
   {
    "say": "11. Edit: change what is there."
   }
  ]
 }
];

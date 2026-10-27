// Written by tests/help_screens.js - one guide for every screen, its buttons numbered. Do not edit by hand.
window.HELP_AUTO = [
 {
  "id": "scr-dashboard-dashboard",
  "area": "Every screen",
  "title": "Dashboard",
  "auto": true,
  "words": "dashboard     daily attendancemark today s attendance salary cardslabour pay for the cycle office salarycycle and salary statements approvalsapprove and order requests purchase ordersraise an lpo expiry remindervisas  ids  permits due pdcspost dated cheques due tax invoiceraise and list tax invoices send to zoholines waiting for zoho activity monitorwho did what  and when screen buttons what is",
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
   },
   {
    "say": "3. Daily attendanceMark today's attendance.",
    "el": "button[onclick=\"dqGo('att')\"]"
   },
   {
    "say": "4. Salary cardsLabour pay for the cycle.",
    "el": "button[onclick=\"dqGo('cards')\"]"
   },
   {
    "say": "5. Office salaryCycle and salary statements.",
    "el": "button[onclick=\"dqGo('ocycle')\"]"
   },
   {
    "say": "6. ApprovalsApprove and order requests.",
    "el": "button[onclick=\"dqGo('appr')\"]"
   },
   {
    "say": "7. Purchase ordersRaise an LPO.",
    "el": "button[onclick=\"dqGo('lpo')\"]"
   },
   {
    "say": "8. Expiry reminderVisas, IDs, permits due.",
    "el": "button[onclick=\"dqGo('expiry')\"]"
   },
   {
    "say": "9. PDCsPost-dated cheques due.",
    "el": "button[onclick=\"dqGo('pdc')\"]"
   },
   {
    "say": "10. Tax invoiceRaise and list tax invoices.",
    "el": "button[onclick=\"dqGo('taxinv')\"]"
   },
   {
    "say": "11. Send to ZohoLines waiting for Zoho.",
    "el": "button[onclick=\"dqGo('zoho')\"]"
   },
   {
    "say": "12. Activity monitorWho did what, and when.",
    "el": "button[onclick=\"dqGo('activity')\"]"
   }
  ]
 },
 {
  "id": "scr-attendance-attendance",
  "area": "Every screen",
  "title": "Attendance > Daily attendance",
  "auto": true,
  "words": "attendance   daily attendance apply to ticked select all select none unfilled emp  74  daily report clear day     screen buttons what is",
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
    "say": "4. Unfilled Emp (74).",
    "el": "#unfilled-btn"
   },
   {
    "say": "5. Daily report: Present, absent, sick, site-wise numbers or names for the date above.",
    "el": "#daily-report-btn"
   },
   {
    "say": "6. Clear Day.",
    "el": "button[onclick=\"openClearDayModal()\"]"
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
  "id": "scr-payroll-labourpay-monthly",
  "area": "Every screen",
  "title": "Payroll > Labour payroll > Monthly report",
  "auto": true,
  "words": "payroll   labour payroll   monthly report save notes preview export pdf export excel screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "labourpay",
   "sub": "monthly"
  },
  "steps": [
   {
    "say": "This is Payroll > Labour payroll > Monthly report. The numbers on the picture match the list below."
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
  "id": "scr-payroll-labourpay-increments",
  "area": "Every screen",
  "title": "Payroll > Labour payroll > Increments",
  "auto": true,
  "words": "payroll   labour payroll   increments record increment preview export pdf export excel edit screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "labourpay",
   "sub": "increments"
  },
  "steps": [
   {
    "say": "This is Payroll > Labour payroll > Increments. The numbers on the picture match the list below."
   },
   {
    "say": "1. Record increment.",
    "el": "button[onclick=\"labIncAdd()\"]"
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"labIncOut('view')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"labIncOut('pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"labIncOut('excel')\"]"
   },
   {
    "say": "5. Edit: change what is there - No change on file yet - his rate is edited on Master Data.",
    "el": "button[onclick=\"xlGo(\\\"attendance\\\", \\\"masterdata\\\", null, () => xlOn(\\\"masterdata\\\"), () => editEmployee(\\\"D-01\\\"))\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-labourpay-gratuity",
  "area": "Every screen",
  "title": "Payroll > Labour payroll > Gratuity",
  "auto": true,
  "words": "payroll   labour payroll   gratuity   preview export pdf export excel screen buttons what is",
  "go": {
   "page": "payroll",
   "tab": "labourpay",
   "sub": "gratuity"
  },
  "steps": [
   {
    "say": "This is Payroll > Labour payroll > Gratuity. The numbers on the picture match the list below."
   },
   {
    "say": "1. ×: Clear."
   },
   {
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"labGratOut('view')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"labGratOut('pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"labGratOut('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-cycle",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Salary cycle & statements",
  "auto": true,
  "words": "payroll   office payroll   salary cycle   statements office staff local staff screen buttons what is",
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
  "words": "payroll   office payroll   loans record loan preview export pdf export excel screen buttons what is",
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
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-staff",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Staff register",
  "auto": true,
  "words": "payroll   office payroll   staff register all companies preview export pdf export excel   new staff screen buttons what is",
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
    "say": "2. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('staff')\"]"
   },
   {
    "say": "3. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('staff','pdf')\"]"
   },
   {
    "say": "4. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('staff','excel')\"]"
   },
   {
    "say": "5. + New staff: adds a new staff.",
    "el": "button[onclick=\"hrNewStaff()\"]"
   }
  ]
 },
 {
  "id": "scr-payroll-hrpayroll-increments",
  "area": "Every screen",
  "title": "Payroll > Office payroll > Increments",
  "auto": true,
  "words": "payroll   office payroll   increments record increment preview export pdf export excel screen buttons what is",
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
  "id": "scr-expiry-expiry-all",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > All together",
  "auto": true,
  "words": "expiry reminder   expiry reminder   all together 0expireddocuments   renew now 0due in 7 daysdocuments   start renewal screen buttons what is",
  "go": {
   "page": "expiry",
   "tab": "expiry",
   "sub": "all"
  },
  "steps": [
   {
    "say": "This is Expiry Reminder > Expiry reminder > All together. The numbers on the picture match the list below."
   },
   {
    "say": "1. 0Expireddocuments - renew now.",
    "el": "button[onclick=\"expCard('expired')\"]"
   },
   {
    "say": "2. 0Due in 7 daysdocuments - start renewal.",
    "el": "button[onclick=\"expCard('week')\"]"
   }
  ]
 },
 {
  "id": "scr-expiry-expiry-people",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > People",
  "auto": true,
  "words": "expiry reminder   expiry reminder   people 0expiredpeople   renew now 0due in 7 dayspeople   start renewal 0due in 8 to 30 dayspeople   plan ahead   read from document save document preview export pdf export excel screen buttons what is",
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
    "say": "1. 0Expiredpeople - renew now.",
    "el": "button[onclick=\"expCard('expired')\"]"
   },
   {
    "say": "2. 0Due in 7 dayspeople - start renewal.",
    "el": "button[onclick=\"expCard('week')\"]"
   },
   {
    "say": "3. 0Due in 8 to 30 dayspeople - plan ahead.",
    "el": "button[onclick=\"expCard('month')\"]"
   },
   {
    "say": "4. 📄 Read from document."
   },
   {
    "say": "5. Save document: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"addDocument()\"]"
   },
   {
    "say": "6. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"previewHr('documents')\"]"
   },
   {
    "say": "7. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"downloadHr('documents','pdf')\"]"
   },
   {
    "say": "8. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"downloadHr('documents','excel')\"]"
   }
  ]
 },
 {
  "id": "scr-expiry-expiry-company",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > Company & other documents",
  "auto": true,
  "words": "expiry reminder   expiry reminder   company   other documents 0expireddocuments   renew now 0due in 7 daysdocuments   start renewal 0all company documentseverything on file save preview export pdf export excel screen buttons what is",
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
    "say": "1. 0Expireddocuments - renew now.",
    "el": "button[onclick=\"expCard('expired')\"]"
   },
   {
    "say": "2. 0Due in 7 daysdocuments - start renewal.",
    "el": "button[onclick=\"expCard('week')\"]"
   },
   {
    "say": "3. 0All company documentseverything on file.",
    "el": "button[onclick=\"expCard('all')\"]"
   },
   {
    "say": "4. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"saveExpiry()\"]"
   },
   {
    "say": "5. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"hrExpExport('view')\"]"
   },
   {
    "say": "6. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"hrExpExport('pdf')\"]"
   },
   {
    "say": "7. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"hrExpExport('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-expiry-expiry-pdc",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > PDCs",
  "auto": true,
  "words": "expiry reminder   expiry reminder   pdcs 0overduenothing overdue 0due in 7 daysnothing this week 0due in 8 to 14 daysnothing next week 0all to be paidno cheques pending   read from cheque add monthly tracker cheque list preview export pdf export excel screen buttons what is",
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
    "say": "3. 0Due in 8 to 14 daysnothing next week.",
    "el": "button[onclick=\"pdcCard('fortnight')\"]"
   },
   {
    "say": "4. 0All to be paidno cheques pending.",
    "el": "button[onclick=\"pdcCard('pending')\"]"
   },
   {
    "say": "5. 📄 Read from cheque."
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
  "id": "scr-expiry-expiry-security",
  "area": "Every screen",
  "title": "Expiry Reminder > Expiry reminder > Security cheques & deposits",
  "auto": true,
  "words": "expiry reminder   expiry reminder   security cheques   deposits 0due to collect back 0collect within 30 days 0with others nowaed 0 00 0no collect back date cheque deposit paid   read from cheque add with others all  incl  collected back preview export pdf screen buttons what is",
  "go": {
   "page": "expiry",
   "tab": "expiry",
   "sub": "security"
  },
  "steps": [
   {
    "say": "This is Expiry Reminder > Expiry reminder > Security cheques & deposits. The numbers on the picture match the list below."
   },
   {
    "say": "1. 0Due to collect back."
   },
   {
    "say": "2. 0Collect within 30 days."
   },
   {
    "say": "3. 0With others nowAED 0.00."
   },
   {
    "say": "4. 0No collect-back date."
   },
   {
    "say": "5. Cheque.",
    "el": "button[onclick=\"scKind('cheque')\"]"
   },
   {
    "say": "6. Deposit paid.",
    "el": "button[onclick=\"scKind('deposit')\"]"
   },
   {
    "say": "7. 📄 Read from cheque."
   },
   {
    "say": "8. Add.",
    "el": "#sc-save"
   },
   {
    "say": "9. With others."
   },
   {
    "say": "10. All, incl. collected back.",
    "el": "button[onclick=\"scShow('all')\"]"
   },
   {
    "say": "11. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"scExport('view')\"]"
   },
   {
    "say": "12. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"scExport('pdf')\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-invoices-tax",
  "area": "Every screen",
  "title": "Accounts > Invoices > Tax Invoice",
  "auto": true,
  "words": "accounts   invoices   tax invoice   add line save   open pdf save clear screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "invoices",
   "sub": "tax"
  },
  "steps": [
   {
    "say": "This is Accounts > Invoices > Tax Invoice. The numbers on the picture match the list below."
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
  "id": "scr-accounts-invoices-proforma",
  "area": "Every screen",
  "title": "Accounts > Invoices > Proforma Invoice",
  "auto": true,
  "words": "accounts   invoices   proforma invoice   add line save   open pdf save clear screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "invoices",
   "sub": "proforma"
  },
  "steps": [
   {
    "say": "This is Accounts > Invoices > Proforma Invoice. The numbers on the picture match the list below."
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
  "id": "scr-accounts-invoices-receipts",
  "area": "Every screen",
  "title": "Accounts > Invoices > Receipts",
  "auto": true,
  "words": "accounts   invoices   receipts bank transfer cheque cash card pdc save   open receipt screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "invoices",
   "sub": "receipts"
  },
  "steps": [
   {
    "say": "This is Accounts > Invoices > Receipts. The numbers on the picture match the list below."
   },
   {
    "say": "1. Bank transfer.",
    "el": "button[onclick=\"rcMode('Bank transfer')\"]"
   },
   {
    "say": "2. Cheque.",
    "el": "button[onclick=\"rcMode('Cheque')\"]"
   },
   {
    "say": "3. Cash.",
    "el": "button[onclick=\"rcMode('Cash')\"]"
   },
   {
    "say": "4. Card.",
    "el": "button[onclick=\"rcMode('Card')\"]"
   },
   {
    "say": "5. PDC.",
    "el": "button[onclick=\"rcMode('PDC')\"]"
   },
   {
    "say": "6. Save & open receipt: keeps what you entered - nothing is kept until you press it.",
    "el": "#rc-save-pdf"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-site",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Site",
  "auto": true,
  "words": "accounts   petty cash   site preview export pdf export excel   read from receipt bill paid cash received add edit remove screen buttons what is",
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
    "say": "4. 📄 Read from receipt."
   },
   {
    "say": "5. Bill paid.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "6. Cash received.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "7. Add.",
    "el": "#pc-save"
   },
   {
    "say": "8. Edit: change what is there.",
    "el": "button[onclick=\"pcEdit(2)\"]"
   },
   {
    "say": "9. Remove: removes it (it asks first).",
    "el": "button[onclick=\"pcDelete(2)\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-pro",
  "area": "Every screen",
  "title": "Accounts > Petty cash > PRO",
  "auto": true,
  "words": "accounts   petty cash   pro general visa preview export pdf export excel   read from receipt bill paid cash received add screen buttons what is",
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
    "say": "1. General.",
    "el": "button[onclick=\"pcView('cash')\"]"
   },
   {
    "say": "2. Visa.",
    "el": "button[onclick=\"pcView('visa')\"]"
   },
   {
    "say": "3. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pcExport('view')\"]"
   },
   {
    "say": "4. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pcExport('pdf')\"]"
   },
   {
    "say": "5. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pcExport('excel')\"]"
   },
   {
    "say": "6. 📄 Read from receipt."
   },
   {
    "say": "7. Bill paid.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "8. Cash received.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "9. Add.",
    "el": "#pc-save"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-office",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Office",
  "auto": true,
  "words": "accounts   petty cash   office preview export pdf export excel   read from receipt bill paid cash received add screen buttons what is",
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
    "say": "4. 📄 Read from receipt."
   },
   {
    "say": "5. Bill paid.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "6. Cash received.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "7. Add.",
    "el": "#pc-save"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-naveen",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Naveen",
  "auto": true,
  "words": "accounts   petty cash   naveen preview export pdf export excel   read from receipt paid by naveen repaid to naveen add screen buttons what is",
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
    "say": "4. 📄 Read from receipt."
   },
   {
    "say": "5. Paid by Naveen.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "6. Repaid to Naveen.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "7. Add.",
    "el": "#pc-save"
   }
  ]
 },
 {
  "id": "scr-accounts-petty-praveen",
  "area": "Every screen",
  "title": "Accounts > Petty cash > Praveen",
  "auto": true,
  "words": "accounts   petty cash   praveen preview export pdf export excel   read from receipt paid by praveen repaid to praveen add screen buttons what is",
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
    "say": "4. 📄 Read from receipt."
   },
   {
    "say": "5. Paid by Praveen.",
    "el": "button[onclick=\"pcKind('paid')\"]"
   },
   {
    "say": "6. Repaid to Praveen.",
    "el": "button[onclick=\"pcKind('received')\"]"
   },
   {
    "say": "7. Add.",
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
  "id": "scr-accounts-projexp",
  "area": "Every screen",
  "title": "Accounts > Project expense",
  "auto": true,
  "words": "accounts   project expense preview export pdf export excel screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "projexp"
  },
  "steps": [
   {
    "say": "This is Accounts > Project expense. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"pxExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"pxExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"pxExport('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-bank",
  "area": "Every screen",
  "title": "Accounts > Bank",
  "auto": true,
  "words": "accounts   bank preview export pdf export excel upload adcb statement save screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "bank"
  },
  "steps": [
   {
    "say": "This is Accounts > Bank. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"bkExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"bkExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"bkExport('excel')\"]"
   },
   {
    "say": "4. Upload ADCB statement."
   },
   {
    "say": "5. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "#bk-save"
   }
  ]
 },
 {
  "id": "scr-accounts-subpay",
  "area": "Every screen",
  "title": "Accounts > Subcontractor payments",
  "auto": true,
  "words": "accounts   subcontractor payments whatsapp the md  1  print verified     send back mark paid screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "subpay"
  },
  "steps": [
   {
    "say": "This is Accounts > Subcontractor payments. The numbers on the picture match the list below."
   },
   {
    "say": "1. WhatsApp the MD (1): One WhatsApp message to the managers with one link for all of them."
   },
   {
    "say": "2. Print: prints it."
   },
   {
    "say": "3. Verified ✓."
   },
   {
    "say": "4. ↶ Send back."
   },
   {
    "say": "5. Mark paid."
   }
  ]
 },
 {
  "id": "scr-accounts-zoho",
  "area": "Every screen",
  "title": "Accounts > Send to Zoho",
  "auto": true,
  "words": "accounts   send to zoho petty cash2 bank0 lpos0 staff loans0 needs attention0 october check suppliers sent to zoho connect zoho preview export pdf export excel screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "zoho"
  },
  "steps": [
   {
    "say": "This is Accounts > Send to Zoho. The numbers on the picture match the list below."
   },
   {
    "say": "1. Petty cash2.",
    "el": "button[onclick=\"zhPane('petty')\"]"
   },
   {
    "say": "2. Bank0.",
    "el": "button[onclick=\"zhPane('bank')\"]"
   },
   {
    "say": "3. LPOs0.",
    "el": "button[onclick=\"zhPane('lpo')\"]"
   },
   {
    "say": "4. Staff loans0.",
    "el": "button[onclick=\"zhPane('loans')\"]"
   },
   {
    "say": "5. Needs attention0.",
    "el": "button[onclick=\"zhPane('attention')\"]"
   },
   {
    "say": "6. October check.",
    "el": "button[onclick=\"zhPane('october')\"]"
   },
   {
    "say": "7. Suppliers.",
    "el": "button[onclick=\"zhPane('suppliers')\"]"
   },
   {
    "say": "8. Sent to Zoho.",
    "el": "button[onclick=\"zhPane('sent')\"]"
   },
   {
    "say": "9. Connect Zoho.",
    "el": "button[onclick=\"zhConnect()\"]"
   },
   {
    "say": "10. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"zhExport('view')\"]"
   },
   {
    "say": "11. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"zhExport('pdf')\"]"
   },
   {
    "say": "12. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"zhExport('excel')\"]"
   }
  ]
 },
 {
  "id": "scr-accounts-credentials",
  "area": "Every screen",
  "title": "Accounts > Credentials",
  "auto": true,
  "words": "accounts   credentials preview export pdf export excel save screen buttons what is",
  "go": {
   "page": "accounts",
   "tab": "credentials"
  },
  "steps": [
   {
    "say": "This is Accounts > Credentials. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"crExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"crExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"crExport('excel')\"]"
   },
   {
    "say": "4. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"crSave()\"]"
   }
  ]
 },
 {
  "id": "scr-estimation-estdash",
  "area": "Every screen",
  "title": "Estimation > Dashboard",
  "auto": true,
  "words": "estimation   dashboard preview export pdf export excel share screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estdash"
  },
  "steps": [
   {
    "say": "This is Estimation > Dashboard. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print."
   },
   {
    "say": "2. Export PDF: downloads it as a PDF."
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet."
   },
   {
    "say": "4. Share."
   }
  ]
 },
 {
  "id": "scr-estimation-estproj",
  "area": "Every screen",
  "title": "Estimation > Projects",
  "auto": true,
  "words": "estimation   projects dashboard overview subcontractors site   technical bills previous records   new project screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   }
  ]
 },
 {
  "id": "scr-estimation-boards",
  "area": "Every screen",
  "title": "Estimation > Trello",
  "auto": true,
  "words": "estimation   trello boards recent starred templates create a inbox planner board switch boards screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "boards"
  },
  "steps": [
   {
    "say": "This is Estimation > Trello. The numbers on the picture match the list below."
   },
   {
    "say": "1. Boards."
   },
   {
    "say": "2. Recent."
   },
   {
    "say": "3. Starred."
   },
   {
    "say": "4. Templates."
   },
   {
    "say": "5. Create."
   },
   {
    "say": "6. A: Account."
   },
   {
    "say": "7. Inbox."
   },
   {
    "say": "8. Planner."
   },
   {
    "say": "9. Board."
   },
   {
    "say": "10. Switch boards."
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
  "words": "store   purchasing   stock   material list check all materials remove   add another material add stock save item screen buttons what is",
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
   },
   {
    "say": "5. Save Item: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"saveStoreItem()\"]"
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
  "words": "store   purchasing   purchasing   suppliers preview export excel template import save edit screen buttons what is",
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
   },
   {
    "say": "6. Edit: change what is there.",
    "el": "button[onclick=\"editSupplier('Test Supplier')\"]"
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
  "id": "scr-reports-labour-accom",
  "area": "Every screen",
  "title": "Reports > Labour > Accommodation",
  "auto": true,
  "words": "reports   labour   accommodation preview export pdf export excel share all beds90 in camp72 on vacation2 booked   arriving0 free beds16   book a bed for a new joiner rooms 1free  put someone screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "labour",
   "sub": "accom"
  },
  "steps": [
   {
    "say": "This is Reports > Labour > Accommodation. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print.",
    "el": "button[onclick=\"campExport('view')\"]"
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"campExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"campExport('excel')\"]"
   },
   {
    "say": "4. Share.",
    "el": "button[onclick=\"campShare()\"]"
   },
   {
    "say": "5. All beds90.",
    "el": "button[onclick=\"campFilter('all')\"]"
   },
   {
    "say": "6. In camp72.",
    "el": "button[onclick=\"campFilter('in')\"]"
   },
   {
    "say": "7. On vacation2.",
    "el": "button[onclick=\"campFilter('vac')\"]"
   },
   {
    "say": "8. Booked - arriving0.",
    "el": "button[onclick=\"campFilter('book')\"]"
   },
   {
    "say": "9. Free beds16.",
    "el": "button[onclick=\"campFilter('free')\"]"
   },
   {
    "say": "10. + Book a bed for a new joiner: adds a new book a bed for a new joiner.",
    "el": "#cp-bookbtn"
   },
   {
    "say": "11. Rooms.",
    "el": "#cp-roombtn"
   },
   {
    "say": "12. 1Free+ Put someone.",
    "el": "button[onclick=\"campBed(1,1)\"]"
   }
  ]
 },
 {
  "id": "scr-reports-labour-ppe",
  "area": "Every screen",
  "title": "Reports > Labour > PPE",
  "auto": true,
  "words": "reports   labour   ppe preview export pdf export excel share   give ppe screen buttons what is",
  "go": {
   "page": "reports",
   "tab": "labour",
   "sub": "ppe"
  },
  "steps": [
   {
    "say": "This is Reports > Labour > PPE. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print."
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"ppeExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"ppeExport('excel')\"]"
   },
   {
    "say": "4. Share."
   },
   {
    "say": "5. + Give PPE: adds a new give ppe.",
    "el": "#pe-give"
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
  "words": "reports   store   purchasing   issued to sites preview export pdf export excel edit screen buttons what is",
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
   },
   {
    "say": "4. Edit: change what is there.",
    "el": "button[onclick=\"editUsageRow(0)\"]"
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
  "id": "scr-admin-forms",
  "area": "Every screen",
  "title": "Admin > Forms",
  "auto": true,
  "words": "admin   forms preview pdf share screen buttons what is",
  "go": {
   "page": "admin",
   "tab": "forms"
  },
  "steps": [
   {
    "say": "This is Admin > Forms. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print."
   },
   {
    "say": "2. PDF: downloads it as a PDF.",
    "el": "button[onclick=\"formsGo('leave_office','pdf')\"]"
   },
   {
    "say": "3. Share."
   }
  ]
 },
 {
  "id": "scr-admin-docs",
  "area": "Every screen",
  "title": "Admin > Docs to office",
  "auto": true,
  "words": "admin   docs to office preview export pdf export excel share     add line send to office clear screen buttons what is",
  "go": {
   "page": "admin",
   "tab": "docs"
  },
  "steps": [
   {
    "say": "This is Admin > Docs to office. The numbers on the picture match the list below."
   },
   {
    "say": "1. Preview: opens it on screen to read or print."
   },
   {
    "say": "2. Export PDF: downloads it as a PDF.",
    "el": "button[onclick=\"dtRegExport('pdf')\"]"
   },
   {
    "say": "3. Export Excel: downloads it as an Excel sheet.",
    "el": "button[onclick=\"dtRegExport('excel')\"]"
   },
   {
    "say": "4. Share."
   },
   {
    "say": "5. ×: Remove this line.",
    "el": "button[onclick=\"DT_ROWS.splice(0,1); if(!DT_ROWS.length) DT_ROWS=[dtBlank()]; dtFormDraw()\"]"
   },
   {
    "say": "6. + Add line: adds a new add line.",
    "el": "button[onclick=\"DT_ROWS.push(dtBlank()); dtFormDraw()\"]"
   },
   {
    "say": "7. Send to office.",
    "el": "#dt-save"
   },
   {
    "say": "8. Clear.",
    "el": "button[onclick=\"['dt-q','dt-st','dt-f','dt-t'].forEach(i=>document.getElementById(i).value='');dtDraw()\"]"
   }
  ]
 },
 {
  "id": "scr-settings-general",
  "area": "Every screen",
  "title": "Settings > General",
  "auto": true,
  "words": "settings   general save turn on for this device screen buttons what is",
  "go": {
   "page": "settings",
   "tab": "general"
  },
  "steps": [
   {
    "say": "This is Settings > General. The numbers on the picture match the list below."
   },
   {
    "say": "1. Save: keeps what you entered - nothing is kept until you press it.",
    "el": "button[onclick=\"notifSave()\"]"
   },
   {
    "say": "2. Turn on for this device.",
    "el": "#push-on-btn"
   }
  ]
 },
 {
  "id": "scr-settings-companies",
  "area": "Every screen",
  "title": "Settings > Companies & sites",
  "auto": true,
  "words": "settings   companies   sites   add company   add site edit remove   add engineer screen buttons what is",
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
    "say": "2. + Add site: adds a new add site.",
    "el": "button[onclick=\"mdSiteForm(true)\"]"
   },
   {
    "say": "3. Edit: change what is there.",
    "el": "button[onclick=\"editSite(1, '306')\"]"
   },
   {
    "say": "4. Remove: removes it (it asks first).",
    "el": "button[onclick=\"removeSite(1, '306')\"]"
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
  "words": "settings   logins   new login edit name reset password screen buttons what is",
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
    "say": "2. Edit name: change what is there."
   },
   {
    "say": "3. Reset password."
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
  "id": "scr-people-vacation",
  "area": "Every screen",
  "title": "Staff > Leave",
  "auto": true,
  "words": "staff   leave labour office list calendar all on leave pending approved returned   add leave preview export pdf screen buttons what is",
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
    "say": "3. List."
   },
   {
    "say": "4. Calendar."
   },
   {
    "say": "5. All."
   },
   {
    "say": "6. On leave."
   },
   {
    "say": "7. Pending."
   },
   {
    "say": "8. Approved: approves it."
   },
   {
    "say": "9. Returned."
   },
   {
    "say": "10. + Add leave: adds a new add leave."
   },
   {
    "say": "11. Preview: opens it on screen to read or print."
   },
   {
    "say": "12. Export PDF: downloads it as a PDF."
   }
  ]
 },
 {
  "id": "scr-people-bday",
  "area": "Every screen",
  "title": "Staff > Birthdays",
  "auto": true,
  "words": "staff   birthdays all registers labour office local clients   client birthday preview export pdf export excel screen buttons what is",
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
   }
  ]
 },
 {
  "id": "scr-est-home-dash",
  "area": "Every screen",
  "title": "Estimation > Projects > Project dashboard",
  "auto": true,
  "words": "estimation   projects   project dashboard dashboard overview subcontractors site   technical bills previous records   new project screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "home.dash"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Project dashboard. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   }
  ]
 },
 {
  "id": "scr-est-client-boq",
  "area": "Every screen",
  "title": "Estimation > Projects > BOQ & budget",
  "auto": true,
  "words": "estimation   projects   boq   budget dashboard overview subcontractors site   technical bills previous records   new project boq   budget12 upload boq paste from excel   line preview screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "client.boq"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > BOQ & budget. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. BOQ & budget12."
   },
   {
    "say": "9. Upload BOQ: The estimation team's internal BOQ workbook (1.PRELIM, 2.SUBSTR ... 20. SPECIALIZED ITEMS). Only the lines are kept - the file is not stored.."
   },
   {
    "say": "10. Paste from Excel."
   },
   {
    "say": "11. + Line: adds a new line."
   },
   {
    "say": "12. Preview: opens it on screen to read or print."
   }
  ]
 },
 {
  "id": "scr-est-subs-reg",
  "area": "Every screen",
  "title": "Estimation > Projects > Subcontract register",
  "auto": true,
  "words": "estimation   projects   subcontract register dashboard overview subcontractors site   technical bills previous records   new project subcontract register1 invoice tracker2 payment certificates finalization log17 34   subcontract   lpo screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "subs.reg"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Subcontract register. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. Subcontract register1."
   },
   {
    "say": "9. Invoice tracker2."
   },
   {
    "say": "10. Payment certificates."
   },
   {
    "say": "11. Finalization log17/34."
   },
   {
    "say": "12. + Subcontract / LPO: adds a new subcontract / lpo."
   }
  ]
 },
 {
  "id": "scr-est-subs-inv",
  "area": "Every screen",
  "title": "Estimation > Projects > Invoice tracker",
  "auto": true,
  "words": "estimation   projects   invoice tracker dashboard overview subcontractors site   technical bills previous records   new project subcontract register1 invoice tracker2 payment certificates finalization log17 34   invoice received screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "subs.inv"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Invoice tracker. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. Subcontract register1."
   },
   {
    "say": "9. Invoice tracker2."
   },
   {
    "say": "10. Payment certificates."
   },
   {
    "say": "11. Finalization log17/34."
   },
   {
    "say": "12. + Invoice received: adds a new invoice received."
   }
  ]
 },
 {
  "id": "scr-est-subs-pcs",
  "area": "Every screen",
  "title": "Estimation > Projects > Payment certificates",
  "auto": true,
  "words": "estimation   projects   payment certificates dashboard overview subcontractors site   technical bills previous records   new project subcontract register1 invoice tracker2 payment certificates finalization log17 34 preview screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "subs.pcs"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Payment certificates. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. Subcontract register1."
   },
   {
    "say": "9. Invoice tracker2."
   },
   {
    "say": "10. Payment certificates."
   },
   {
    "say": "11. Finalization log17/34."
   },
   {
    "say": "12. Preview: opens it on screen to read or print."
   }
  ]
 },
 {
  "id": "scr-est-subs-final",
  "area": "Every screen",
  "title": "Estimation > Projects > Finalization log",
  "auto": true,
  "words": "estimation   projects   finalization log dashboard overview subcontractors site   technical bills previous records   new project subcontract register1 invoice tracker2 payment certificates finalization log17 34   item screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "subs.final"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Finalization log. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. Subcontract register1."
   },
   {
    "say": "9. Invoice tracker2."
   },
   {
    "say": "10. Payment certificates."
   },
   {
    "say": "11. Finalization log17/34."
   },
   {
    "say": "12. + Item: adds a new item."
   }
  ]
 },
 {
  "id": "scr-est-site-rfi",
  "area": "Every screen",
  "title": "Estimation > Projects > RFI log",
  "auto": true,
  "words": "estimation   projects   rfi log dashboard overview subcontractors site   technical bills previous records   new project rfi log1 nocs   approvals15 25 submittals25 variations5 reply in 7 days screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "site.rfi"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > RFI log. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. RFI log1."
   },
   {
    "say": "9. NOCs & approvals15/25."
   },
   {
    "say": "10. Submittals25."
   },
   {
    "say": "11. Variations5."
   },
   {
    "say": "12. Reply in 7 days: Days allowed for a reply - the due date is set from it."
   }
  ]
 },
 {
  "id": "scr-est-site-approval",
  "area": "Every screen",
  "title": "Estimation > Projects > NOCs & approvals",
  "auto": true,
  "words": "estimation   projects   nocs   approvals dashboard overview subcontractors site   technical bills previous records   new project rfi log1 nocs   approvals15 25 submittals25 variations5   item screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "site.approval"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > NOCs & approvals. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. RFI log1."
   },
   {
    "say": "9. NOCs & approvals15/25."
   },
   {
    "say": "10. Submittals25."
   },
   {
    "say": "11. Variations5."
   },
   {
    "say": "12. + Item: adds a new item."
   }
  ]
 },
 {
  "id": "scr-est-site-submittal",
  "area": "Every screen",
  "title": "Estimation > Projects > Submittals",
  "auto": true,
  "words": "estimation   projects   submittals dashboard overview subcontractors site   technical bills previous records   new project rfi log1 nocs   approvals15 25 submittals25 variations5   new submittal screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "site.submittal"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Submittals. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. RFI log1."
   },
   {
    "say": "9. NOCs & approvals15/25."
   },
   {
    "say": "10. Submittals25."
   },
   {
    "say": "11. Variations5."
   },
   {
    "say": "12. + New submittal: adds a new submittal."
   }
  ]
 },
 {
  "id": "scr-est-site-vo",
  "area": "Every screen",
  "title": "Estimation > Projects > Variations",
  "auto": true,
  "words": "estimation   projects   variations dashboard overview subcontractors site   technical bills previous records   new project rfi log1 nocs   approvals15 25 submittals25 variations5   variation screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "site.vo"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Variations. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. RFI log1."
   },
   {
    "say": "9. NOCs & approvals15/25."
   },
   {
    "say": "10. Submittals25."
   },
   {
    "say": "11. Variations5."
   },
   {
    "say": "12. + Variation: adds a new variation."
   }
  ]
 },
 {
  "id": "scr-est-bills-ipa",
  "area": "Every screen",
  "title": "Estimation > Projects > Bills to client",
  "auto": true,
  "words": "estimation   projects   bills to client dashboard overview subcontractors site   technical bills previous records   new project bills to client   new bill upload bill format   another contract open screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "bills.ipa"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Bills to client. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. Bills to client."
   },
   {
    "say": "9. + New bill: adds a new bill."
   },
   {
    "say": "10. Upload bill format."
   },
   {
    "say": "11. + Another contract: adds a new another contract - This project is under more than one agreement with the client (e.g. shell & core, MEP, swimming pool): each gets its own bills, certificates and variations.."
   },
   {
    "say": "12. Open."
   }
  ]
 },
 {
  "id": "scr-est-prev-rec",
  "area": "Every screen",
  "title": "Estimation > Projects > Previous records",
  "auto": true,
  "words": "estimation   projects   previous records dashboard overview subcontractors site   technical bills previous records   new project bring in old records   upload delete screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "estproj",
   "est": "prev.rec"
  },
  "steps": [
   {
    "say": "This is Estimation > Projects > Previous records. The numbers on the picture match the list below."
   },
   {
    "say": "1. Dashboard."
   },
   {
    "say": "2. Overview."
   },
   {
    "say": "3. Subcontractors."
   },
   {
    "say": "4. Site & technical."
   },
   {
    "say": "5. Bills."
   },
   {
    "say": "6. Previous records."
   },
   {
    "say": "7. + New project: adds a new project."
   },
   {
    "say": "8. Bring in old records."
   },
   {
    "say": "9. + Upload: adds a new upload."
   },
   {
    "say": "10. Delete: removes it (it asks first)."
   }
  ]
 },
 {
  "id": "scr-kb-board",
  "area": "Every screen",
  "title": "Estimation > Trello > Board",
  "auto": true,
  "words": "estimation   trello   board boards recent starred templates create a estimation board table calendar timeline dashboard screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "boards",
   "kb": "board",
   "kbView": "board"
  },
  "steps": [
   {
    "say": "This is Estimation > Trello > Board. The numbers on the picture match the list below."
   },
   {
    "say": "1. Boards."
   },
   {
    "say": "2. Recent."
   },
   {
    "say": "3. Starred."
   },
   {
    "say": "4. Templates."
   },
   {
    "say": "5. Create."
   },
   {
    "say": "6. A: Account."
   },
   {
    "say": "7. Estimation: Rename board."
   },
   {
    "say": "8. Board: Board view."
   },
   {
    "say": "9. Table: Table view."
   },
   {
    "say": "10. Calendar: Calendar view."
   },
   {
    "say": "11. Timeline: Timeline view."
   },
   {
    "say": "12. Dashboard: Dashboard view."
   }
  ]
 },
 {
  "id": "scr-kb-table",
  "area": "Every screen",
  "title": "Estimation > Trello > Table",
  "auto": true,
  "words": "estimation   trello   table boards recent starred templates create a estimation board table calendar timeline dashboard screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "boards",
   "kb": "board",
   "kbView": "table"
  },
  "steps": [
   {
    "say": "This is Estimation > Trello > Table. The numbers on the picture match the list below."
   },
   {
    "say": "1. Boards."
   },
   {
    "say": "2. Recent."
   },
   {
    "say": "3. Starred."
   },
   {
    "say": "4. Templates."
   },
   {
    "say": "5. Create."
   },
   {
    "say": "6. A: Account."
   },
   {
    "say": "7. Estimation: Rename board."
   },
   {
    "say": "8. Board: Board view."
   },
   {
    "say": "9. Table: Table view."
   },
   {
    "say": "10. Calendar: Calendar view."
   },
   {
    "say": "11. Timeline: Timeline view."
   },
   {
    "say": "12. Dashboard: Dashboard view."
   }
  ]
 },
 {
  "id": "scr-kb-calendar",
  "area": "Every screen",
  "title": "Estimation > Trello > Calendar",
  "auto": true,
  "words": "estimation   trello   calendar boards recent starred templates create a estimation board table calendar timeline dashboard screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "boards",
   "kb": "board",
   "kbView": "calendar"
  },
  "steps": [
   {
    "say": "This is Estimation > Trello > Calendar. The numbers on the picture match the list below."
   },
   {
    "say": "1. Boards."
   },
   {
    "say": "2. Recent."
   },
   {
    "say": "3. Starred."
   },
   {
    "say": "4. Templates."
   },
   {
    "say": "5. Create."
   },
   {
    "say": "6. A: Account."
   },
   {
    "say": "7. Estimation: Rename board."
   },
   {
    "say": "8. Board: Board view."
   },
   {
    "say": "9. Table: Table view."
   },
   {
    "say": "10. Calendar: Calendar view."
   },
   {
    "say": "11. Timeline: Timeline view."
   },
   {
    "say": "12. Dashboard: Dashboard view."
   }
  ]
 },
 {
  "id": "scr-kb-timeline",
  "area": "Every screen",
  "title": "Estimation > Trello > Timeline",
  "auto": true,
  "words": "estimation   trello   timeline boards recent starred templates create a estimation board table calendar timeline dashboard screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "boards",
   "kb": "board",
   "kbView": "timeline"
  },
  "steps": [
   {
    "say": "This is Estimation > Trello > Timeline. The numbers on the picture match the list below."
   },
   {
    "say": "1. Boards."
   },
   {
    "say": "2. Recent."
   },
   {
    "say": "3. Starred."
   },
   {
    "say": "4. Templates."
   },
   {
    "say": "5. Create."
   },
   {
    "say": "6. A: Account."
   },
   {
    "say": "7. Estimation: Rename board."
   },
   {
    "say": "8. Board: Board view."
   },
   {
    "say": "9. Table: Table view."
   },
   {
    "say": "10. Calendar: Calendar view."
   },
   {
    "say": "11. Timeline: Timeline view."
   },
   {
    "say": "12. Dashboard: Dashboard view."
   }
  ]
 },
 {
  "id": "scr-kb-dashboard",
  "area": "Every screen",
  "title": "Estimation > Trello > Dashboard",
  "auto": true,
  "words": "estimation   trello   dashboard boards recent starred templates create a estimation board table calendar timeline dashboard screen buttons what is",
  "go": {
   "page": "estimation",
   "tab": "boards",
   "kb": "board",
   "kbView": "dashboard"
  },
  "steps": [
   {
    "say": "This is Estimation > Trello > Dashboard. The numbers on the picture match the list below."
   },
   {
    "say": "1. Boards."
   },
   {
    "say": "2. Recent."
   },
   {
    "say": "3. Starred."
   },
   {
    "say": "4. Templates."
   },
   {
    "say": "5. Create."
   },
   {
    "say": "6. A: Account."
   },
   {
    "say": "7. Estimation: Rename board."
   },
   {
    "say": "8. Board: Board view."
   },
   {
    "say": "9. Table: Table view."
   },
   {
    "say": "10. Calendar: Calendar view."
   },
   {
    "say": "11. Timeline: Timeline view."
   },
   {
    "say": "12. Dashboard: Dashboard view."
   }
  ]
 }
];

"""How much room the database and its backups need, measured not guessed.

Run: cd app && DATABASE_URL=sqlite:////tmp/size.db python3 ../tests/size_forecast.py

Builds Infinia's actual shape - 74 workers, 3,238 materials, five sites,
attendance every working day, ten purchase orders a day with their
requests, deliveries and issues, and the activity log that all of it
writes - then measures a real backup at one month and again at twelve,
compressed as it is stored and plain as it is downloaded.
"""
import sys, io, json, gzip, random, datetime as dt
sys.path.insert(0, '.')
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

random.seed(7)
WORKERS, MATERIALS, SITES = 74, 3238, 5
LPOS_PER_DAY, LINES_PER_LPO = 10, 5
WORKING_DAYS_PER_MONTH = 26

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Praveen', role='admin'))
for i in range(6):
    db.add(models.User(username=f'staff{i}', hashed_password=auth.hash_password('p'), full_name=f'Staff {i}', role='office'))
for i in range(WORKERS):
    db.add(models.Employee(emp_no=f'F-{700+i}', name=f'WORKER NAME {i} SOMEWHAT LONG', trade='MASON',
                           company='Infinia', total_salary=1500 + i * 10, basic_salary=1000, active=True))
for s in range(SITES):
    db.add(models.Site(code=f'9{s:02d}', plot_no=f'PLOT-{s}', project_name=f'Project {s}',
                       incharge='Febiyan', address='Dubai', active=True))
for e in ('Febiyan', 'Akhil', 'Muhsina'):
    db.add(models.Engineer(name=e, mobile='0501234567', active=True))
for i in range(MATERIALS):
    db.add(models.StoreItem(code=f'ITM{i+1}', name=f'Material Description Number {i} - 50kg grade A',
                            unit='pcs', item_type='consumable', category='General', active=True))
for i in range(60):
    db.add(models.Supplier(name=f'Supplier Trading LLC {i}', name_key=f'suppliertradingllc{i}',
                           contact_person='Contact Person', phone='0509876543',
                           trn='100200300400500', address='Industrial Area, Dubai',
                           email='sales@supplier.ae', payment_terms='30 days'))
db.commit()

START = dt.date(2026, 1, 1)
def add_day(d, day_no):
    """One working day exactly as the company generates it."""
    for w in range(WORKERS):
        db.add(models.DailyRow(employee_id=w + 1, emp_no=f'F-{700+w}', emp_name=f'WORKER NAME {w} SOMEWHAT LONG',
                               trade='MASON', month_year=d.strftime('%B %Y'), full_date=d, day=d.day,
                               am='Present', pm='Present', ot=2, bh=0, site='901', engineer='Febiyan',
                               comments='' if w % 5 else 'night shift'))
    for n in range(LPOS_PER_DAY):
        mr = models.MaterialRequest(ref=f'MR-{day_no*LPOS_PER_DAY+n:04d}', site='901', requested_by='Febiyan',
                                    needed_by=d, urgency='normal', status='delivered',
                                    notes='For slab and blockwork', requested_on=d)
        db.add(mr); db.flush()
        for l in range(LINES_PER_LPO):
            db.add(models.MaterialRequestLine(request_id=mr.id, item_id=random.randint(1, MATERIALS),
                                              description='', qty_requested=100, qty_approved=100,
                                              qty_received=100, unit='pcs', est_cost=16.5,
                                              status='approved', purpose='slab'))
        po_no = 20260100 + day_no * LPOS_PER_DAY + n
        po = models.PurchaseOrder(po_no=po_no, ref=f'IC/LPO/{po_no}', order_date=d, terms='Due on Receipt',
                                  supplier_id=random.randint(1, 60), supplier_name='Supplier Trading LLC 3',
                                  supplier_address='Industrial Area, Dubai', supplier_trn='100200300400500',
                                  supplier_email='sales@supplier.ae', request_id=mr.id, plot_no='PLOT-1',
                                  contact_person='Amal', mobile='0509876543', job_scope='Slab works',
                                  project_location='901', tax_pct=5.0,
                                  terms_text='Standard terms apply to this order.')
        db.add(po); db.flush()
        for l in range(LINES_PER_LPO):
            db.add(models.PurchaseOrderLine(order_id=po.id, item_id=random.randint(1, MATERIALS),
                                            description='Material Description Number 7 - 50kg grade A',
                                            qty=100, unit='pcs', rate=16.5, tax_pct=5.0))
        # The delivery in, and an issue out to a site.
        for kind, loc in (('in', ''), ('out', '901')):
            db.add(models.StoreMovement(item_id=random.randint(1, MATERIALS), kind=kind, qty=100,
                                        from_location='' if kind == 'out' else '', location=loc,
                                        incharge='Amal', supplier='Supplier Trading LLC 3',
                                        reference=f'DO-{day_no}{n}', notes='', moved_on=d))
    # The activity log: every save, approval, order, delivery and login.
    for a in range(120):
        db.add(models.AuditLog(user_id=1, action='store_movement',
                               details=f'issued 100 pcs ITM{random.randint(1, MATERIALS)} to 901'))

def measure(label, days):
    d = database.SessionLocal()
    data = main.build_backup_data(d)
    plain = json.dumps(data, default=str)
    stored = main._backup_dump(data)
    d.close()
    rows = sum(len(v) for v in data.values() if isinstance(v, list))
    return {'label': label, 'days': days, 'rows': rows,
            'plain_mb': len(plain) / 1e6, 'stored_mb': len(stored) / 1e6}

results = []
day_no = 0
for month in range(12):
    for _ in range(WORKING_DAYS_PER_MONTH):
        day_no += 1
        add_day(START + dt.timedelta(days=day_no), day_no)
    db.commit()
    if month in (0, 5, 11):
        results.append(measure(f'after {month+1} month(s)', day_no))
db.close()

print(f"\nInfinia's shape: {WORKERS} workers, {MATERIALS} materials, {SITES} sites,")
print(f"{LPOS_PER_DAY} purchase orders a day with {LINES_PER_LPO} lines each, {WORKING_DAYS_PER_MONTH} working days a month.\n")
print(f"{'':22} {'rows':>10} {'backup (plain)':>16} {'backup (stored)':>17}")
for r in results:
    print(f"{r['label']:22} {r['rows']:>10,} {r['plain_mb']:>13.1f} MB {r['stored_mb']:>14.2f} MB")

first, last = results[0], results[-1]
per_day_rows = (last['rows'] - first['rows']) / (last['days'] - first['days'])
per_day_mb = (last['stored_mb'] - first['stored_mb']) / (last['days'] - first['days'])
print(f"\nGrowth per working day: {per_day_rows:,.0f} rows, {per_day_mb*1000:.1f} KB on a stored backup")
print(f"A year of records, backed up once: {last['stored_mb']:.2f} MB stored, {last['plain_mb']:.1f} MB downloaded")
print(f"40 daily backups at the end of that year: {last['stored_mb']*40:.1f} MB")
print(f"Database rows after a year: {last['rows']:,}")

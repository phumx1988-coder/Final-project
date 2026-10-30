"""Use `python test_sales_features.py`: isolated tests, does not edit store DB."""
import tempfile
from pathlib import Path
from unittest.mock import Mock
import database, order, sales_overview, admin, main

class Ctx:
    def __init__(self,db,q=None,f=None,admin_user=True):
        self.db=db;self.q=q or {};self.f=f or {};self.user={'id':1,'is_admin':1 if admin_user else 0}
        self.esc=main.esc;self.baht=main.baht;self.to_int=main.to_int;self.cookies={}
    def redirect(self,path,message='',err=False):return ('redirect',path,message,err)
    def page(self,title,body,status=200):return (title,body,status)
    def not_found(self):return ('not_found',)

with tempfile.TemporaryDirectory() as tmp:
    database.DB=Path(tmp)/'store.db';database.init_db()
    with database.connect() as db:
        p=db.execute('SELECT id,name,image FROM products WHERE id=1').fetchone()
        db.execute('INSERT INTO users(id,name,email,password_hash,is_admin) VALUES(1,?,?,?,1)',('Admin','admin@local','dummy'))
        db.execute('INSERT INTO orders(id,user_id,total,status,address,payment_method,payment_status,payment_reviewed_at,vat_rate,vat_amount,net_before_vat) VALUES(1,1,2000,"Completed","test","transfer","paid","2026-10-24 13:00:00",.07,130.84,1869.16)')
        db.execute('INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES(1,1,2,1000)')
        db.commit()
        for period,value in [('day','2026-10-24'),('month','2026-10'),('year','2026')]:
            ctx=Ctx(db,{'period':period,'date':value})
            title,body,status=sales_overview.overview(ctx)
            assert status==200 and '2,000' in body and '2 ชิ้น' in body and 'Mercurial Vapor Academy' in body, (period,body[:1000])
        before=db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0]
        ctx=Ctx(db,{'period':'year','date':'2026'}, {'id':'1'})
        admin.valid_post=lambda ctx:True
        assert admin.product_toggle(ctx)[0]=='redirect'
        assert db.execute('SELECT is_active FROM products WHERE id=1').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0]==before
        assert db.execute('SELECT image FROM products WHERE id=1').fetchone()[0]==p['image']
        assert sales_overview.overview(ctx)[2]==200
        assert db.execute('SELECT COUNT(*) FROM products').fetchone()[0]==64
        assert admin.product_toggle(ctx)[0]=='redirect'
        assert db.execute('SELECT is_active FROM products WHERE id=1').fetchone()[0]==1
        database.init_db()
        assert db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0]==before
    assert order.totals([{'price':1000,'quantity':2}])[-1]==2000
    assert order.vat_breakdown(2000)==(1869.16,130.84)
    print('PASS: VAT included, daily/monthly/yearly, product leader, archive/restore, image/history preservation')

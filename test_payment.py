"""Run with python test_payment.py; uses isolated temporary database."""
import tempfile, threading, http.client, urllib.parse, secrets, re, os
from pathlib import Path
import database, main, auth, payment
from datetime import datetime,timedelta,timezone
from http.server import ThreadingHTTPServer

def run():
  with tempfile.TemporaryDirectory() as td:
    database.DB=Path(td)/'test.db'; payment.UPLOAD_DIR=Path(td)/'proofs';database.init_db()
    db=database.connect()
    db.execute('INSERT INTO users(name,email,phone,password_hash,is_admin) VALUES(?,?,?,?,0)',('Customer','buyer@test.local','0111111111',auth.digest('Testing123!')))
    buyer=db.execute('SELECT id FROM users WHERE email=?',('buyer@test.local',)).fetchone()[0]
    db.execute('INSERT INTO users(name,email,phone,password_hash,is_admin) VALUES(?,?,?,?,1)',('Admin','admin@test.local','0222222222',auth.digest('Testing123!')))
    admin=db.execute('SELECT id FROM users WHERE email=?',('admin@test.local',)).fetchone()[0]
    db.execute('UPDATE products SET price=1000,stock=20 WHERE id=1')
    buyer_token=secrets.token_urlsafe(32);admin_token=secrets.token_urlsafe(32)
    exp=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    db.executemany('INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)',[(buyer_token,buyer,exp),(admin_token,admin,exp)]);db.commit();db.close()
    server=ThreadingHTTPServer(('127.0.0.1',0),main.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def req(method,path,form=None,token=None,raw=None,ctype=None):
      con=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
      b=urllib.parse.urlencode(form).encode() if form is not None else raw
      headers={'Cookie':'session='+token} if token else {}
      if b is not None:headers['Content-Type']=ctype or 'application/x-www-form-urlencoded'
      con.request(method,path,b,headers)
      res=con.getresponse();data=res.read();code=res.status;headers=dict(res.getheaders());con.close();return code,data.decode('utf-8','ignore'),headers
    try:
      assert req('GET','/')[0]==200
      assert req('GET','/checkout')[0]==303
      assert req('GET','/admin/payments',token=buyer_token)[0]==404
      code,body,_=req('GET','/products');assert code==200
      assert req('POST','/cart/add',{'product_id':'1','quantity':'2'},buyer_token)[0]==303
      code,body,_=req('GET','/checkout',token=buyer_token);assert code==200 and '2,000' in body and 'PromptPay' in body
      assert 'เก็บเงินปลายทาง' not in body and 'value="cod"' not in body
      csrf=re.search(r'name="csrf" value="([^"]+)"',body).group(1)
      assert req('POST','/checkout',{'csrf':csrf,'address':'Khon Kaen','payment_method':'cod'},buyer_token)[0]==303
      db=database.connect();assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0;db.close()
      assert req('POST','/checkout',{'csrf':csrf,'address':'Khon Kaen','payment_method':'promptpay'},buyer_token)[0]==303
      db=database.connect();o=db.execute('SELECT * FROM orders').fetchone();assert o['payment_status']=='pending' and o['total']==2000 and o['vat_amount']==round(2000-2000/1.07,2) and o['net_before_vat']==round(2000/1.07,2) and o['shipping_fee']==0
      oid=o['id'];db.close()
      code,body,_=req('GET',f'/order?id={oid}',token=buyer_token);assert code==200 and 'แนบสลิป' in body
      assert req('GET',f'/order?id={oid}',token=admin_token)[0]==404
      assert req('GET',f'/payment/slip?id={oid}',token=admin_token)[0]==404
      boundary='----FOOTZONEtest'
      png=b'\x89PNG\r\n\x1a\n'+b'a'*100
      raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="id"\r\n\r\n{oid}\r\n--{boundary}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n--{boundary}\r\nContent-Disposition: form-data; name="slip"; filename="proof.png"\r\nContent-Type: image/png\r\n\r\n').encode()+png+f'\r\n--{boundary}--\r\n'.encode()
      assert req('POST','/payment/notify',token=buyer_token,raw=raw,ctype=f'multipart/form-data; boundary={boundary}')[0]==303
      db=database.connect();assert db.execute('SELECT payment_status FROM orders WHERE id=?',(oid,)).fetchone()[0]=='review';db.close()
      assert req('GET',f'/payment/slip?id={oid}',token=buyer_token)[0]==200
      code,body,_=req('GET',f'/admin/payments?q={oid}',token=admin_token);assert code==200 and 'ยืนยันชำระแล้ว' in body
      admincsrf=re.search(r'name="csrf" value="([^"]+)"',body).group(1)
      assert req('POST','/admin/payment/review',{'csrf':admincsrf,'id':oid,'decision':'paid'},admin_token)[0]==303
      db=database.connect();o=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone();assert o['payment_status']=='paid' and o['payment_reviewed_by']==admin and o['payment_reviewed_at'];db.close()
      assert req('POST','/admin/payment/review',{'csrf':admincsrf,'id':oid,'decision':'paid'},admin_token)[0]==303
      print('PASS: catalog, auth, checkout, totals, upload, review, protected slip, payment audit')
      print('PASS: PromptPay EMV payload checksum:',payment.promptpay_payload('0812345678',2060)[-4:])
    finally:server.shutdown();server.server_close()
if __name__=='__main__':run()

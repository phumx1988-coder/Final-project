"""Manual shipment tracking, scoped to the order owner and authorized staff."""
from urllib.parse import quote
from admin import guard, valid_post, page

CARRIERS = {
    'thailand-post': ('ไปรษณีย์ไทย', 'https://track.thailandpost.co.th/'),
    'flash': ('Flash Express', 'https://www.flashexpress.co.th/tracking/'),
    'jnt': ('J&T Express', 'https://www.jtexpress.co.th/'),
    'kex': ('KEX (Kerry)', 'https://th.kex-express.com/'),
    'dhl': ('DHL Express', 'https://www.dhl.com/th-th/home/tracking.html'),
}
EVENTS = {'preparing':'กำลังเตรียมสินค้า', 'shipped':'ส่งสินค้าแล้ว', 'out_for_delivery':'กำลังนำจ่าย', 'delivered':'จัดส่งสำเร็จ', 'exception':'มีปัญหาการจัดส่ง'}
STEPS = ('ordered','payment','preparing','shipped','out_for_delivery','delivered')
LABELS = {'ordered':'รับคำสั่งซื้อแล้ว', 'payment':'ตรวจสอบการชำระเงิน', **EVENTS}

def latest(ctx, oid):
    return ctx.db.execute('SELECT * FROM shipments WHERE order_id=?',(oid,)).fetchone()

def tracking_fragment(ctx, o):
    sh=latest(ctx,o['id'])
    history=ctx.db.execute('SELECT e.*,u.name AS editor FROM shipment_events e LEFT JOIN users u ON u.id=e.updated_by WHERE order_id=? ORDER BY e.id DESC',(o['id'],)).fetchall()
    state=sh['tracking_status'] if sh else ('delivered' if o['status']=='Completed' else 'shipped' if o['status']=='Shipped' else 'preparing' if o['status']=='Confirmed' else 'ordered')
    if o['status']=='Cancelled':state='cancelled'
    carrier=CARRIERS.get(sh['carrier']) if sh else None
    detail='<p class="muted">ยังไม่มีเลขพัสดุ ร้านจะเพิ่มเมื่อส่งสินค้า</p>'
    if sh and sh['tracking_number']:
        detail=f'<p>ขนส่ง: <b>{ctx.esc(carrier[0] if carrier else "ยังไม่ระบุ")}</b></p><p>หมายเลขพัสดุ: <code>{ctx.esc(sh["tracking_number"])}</code></p>'
        if carrier:detail+=f'<p><a class="btn btn-sm btn-outline" href="{ctx.esc(carrier[1])}" target="_blank" rel="noopener noreferrer">เปิดเว็บไซต์ขนส่ง ↗</a></p><p class="muted">คัดลอกเลขพัสดุไปค้นหาในเว็บไซต์ขนส่ง ข้อมูลสถานะด้านล่างอัปเดตโดยร้านเอง</p>'
    if state=='cancelled':
        bars='<div class="ship-step"><b>ยกเลิกคำสั่งซื้อ</b></div>'
    else:
        current_idx = STEPS.index(state) if state in STEPS else 2
        bars=''.join(f'<div class="ship-step {"ship-done" if i<=current_idx else ""}"><span class="ship-dot">{"✓" if i<=current_idx else "○"}</span><b>{LABELS[s]}</b></div>' for i,s in enumerate(STEPS))
    paymsg='ชำระเงิน: '+('ตรวจสอบสำเร็จ' if o['payment_status']=='paid' else 'ยังไม่ยืนยันชำระเงิน')
    if history:
        logs=''.join(f'<li><b>{ctx.esc(EVENTS.get(e["status"],e["status"]))}</b> · {ctx.esc(e["created_at"])}<p class="muted">{ctx.esc(e["note"] or "ไม่มีหมายเหตุ")}</p></li>' for e in history)
    else:logs='<li class="muted">ยังไม่มีประวัติการอัปเดตจากร้าน</li>'
    return f'<section class="tracking-block"><h2>ติดตามพัสดุ</h2><p>{ctx.esc(paymsg)}</p>{detail}<div class="ship-timeline">{bars}</div><h3>ประวัติการจัดส่ง</h3><ol class="ship-history">{logs}</ol></section>'

def customer_tracking(ctx):
    if not ctx.user:return ctx.need_login('/orders')
    oid=ctx.to_int(ctx.q.get('id'))
    order=ctx.db.execute('SELECT * FROM orders WHERE id=? AND user_id=?',(oid,ctx.user['id'])).fetchone() if oid else None
    if not order:return ctx.not_found()
    return ctx.page('ติดตามพัสดุ',f'<section class="container section narrow"><p><a href="/order?id={oid}">← รายละเอียดคำสั่งซื้อ</a></p><h1>ติดตามคำสั่งซื้อ #{oid}</h1>{tracking_fragment(ctx,order)}</section>')

def admin_shipments(ctx):
    denied=guard(ctx)
    if denied:return denied
    query=ctx.q.get('q','').strip();args=[]
    sql='SELECT o.*,u.name AS customer,s.carrier,s.tracking_number,s.tracking_status FROM orders o JOIN users u ON u.id=o.user_id LEFT JOIN shipments s ON s.order_id=o.id'
    if query:
        if not query.isdigit():return page(ctx,'จัดการการจัดส่ง','<p>กรุณากรอกหมายเลขคำสั่งซื้อเป็นตัวเลข</p>')
        sql+=' WHERE o.id=?';args.append(int(query))
    sql+=' ORDER BY o.id DESC LIMIT 200'
    rows=ctx.db.execute(sql,args).fetchall()
    out=f'<form class="filters" action="/admin/shipping" method="get"><input name="q" placeholder="ค้นหาเลขคำสั่งซื้อ" value="{ctx.esc(query)}"><button class="btn">ค้นหา</button></form>'
    out+='<div class="admin-scroll"><table class="admin-table"><tr><th>คำสั่งซื้อ</th><th>ลูกค้า</th><th>ชำระเงิน</th><th>สถานะพัสดุ</th><th>จัดการ</th></tr>'
    for r in rows:
        label=EVENTS.get(r['tracking_status'],r['status'])
        out+=f'<tr><td>#{r["id"]}</td><td>{ctx.esc(r["customer"])}</td><td>{ctx.esc(r["payment_status"])}</td><td>{ctx.esc(label)}</td><td><a class="btn btn-sm" href="/admin/shipment?id={r["id"]}">จัดการพัสดุ</a></td></tr>'
    return page(ctx,'จัดการการจัดส่ง',out+'</table></div>')

def admin_shipment(ctx):
    denied=guard(ctx)
    if denied:return denied
    oid=ctx.to_int(ctx.q.get('id'))
    o=ctx.db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone() if oid else None
    if not o:return ctx.not_found()
    sh=latest(ctx,oid)
    def val(key):return ctx.esc(sh[key] or '') if sh else ''
    carriers=''.join(f'<option value="{k}" {"selected" if sh and sh["carrier"]==k else ""}>{ctx.esc(v[0])}</option>' for k,v in CARRIERS.items())
    states=''.join(f'<option value="{k}" {"selected" if sh and sh["tracking_status"]==k else ""}>{ctx.esc(v)}</option>' for k,v in EVENTS.items())
    from admin import csrf
    form=f'''<div class="admin-form"><p>คำสั่งซื้อ #{oid} · ชำระเงิน: {ctx.esc(o['payment_status'])} · สถานะคำสั่งซื้อ: {ctx.esc(o['status'])}</p><p class="muted">สถานะนี้เป็นการอัปเดตด้วยมือ ไม่ได้ดึงจากบริษัทขนส่ง</p><form method="post" action="/admin/shipment/save" class="form"><input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{oid}"><label>บริษัทขนส่ง<select name="carrier"><option value="">ยังไม่เลือกบริษัทขนส่ง</option>{carriers}</select></label><label>เลขพัสดุ<input name="tracking_number" maxlength="100" value="{val('tracking_number')}" placeholder="กรอกตามใบรับฝากจริง"></label><label>อัปเดตสถานะ<select name="status">{states}</select></label><label>หมายเหตุการอัปเดต<input name="note" maxlength="500" placeholder="เช่น ส่งพัสดุเข้าระบบขนส่งแล้ว"></label><button class="btn">บันทึกสถานะพัสดุ</button></form></div>'''
    return page(ctx,'จัดการพัสดุ',f'<p><a href="/admin/shipping">← กลับรายการจัดส่ง</a></p>{form}{tracking_fragment(ctx,o)}')

def save_shipment(ctx):
    if not valid_post(ctx):return ctx.page('Access denied','<section class="container">ไม่มีสิทธิ์</section>',403)
    oid=ctx.to_int(ctx.f.get('id'));carrier=ctx.f.get('carrier','').strip();number=ctx.f.get('tracking_number','').strip();status=ctx.f.get('status','');note=ctx.f.get('note','').strip()
    if not oid or status not in EVENTS or (carrier and carrier not in CARRIERS) or len(number)>100 or len(note)>500 or any(ord(ch)<32 for ch in number):
        return ctx.redirect('/admin/shipping','ข้อมูลพัสดุไม่ถูกต้อง',True)
    db=ctx.db;o=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if not o:return ctx.not_found()
    if o['status']=='Cancelled':return ctx.redirect('/admin/shipment?id='+str(oid),'คำสั่งซื้อยกเลิกแล้ว',True)
    if o['payment_status']!='paid':return ctx.redirect('/admin/shipment?id='+str(oid),'ต้องตรวจสอบรับชำระเงินก่อนจัดส่ง',True)
    if status in ('shipped','out_for_delivery','delivered','exception') and (not carrier or not number):
        return ctx.redirect('/admin/shipment?id='+str(oid),'กรุณาระบุบริษัทขนส่งและเลขพัสดุ',True)
    sh=latest(ctx,oid)
    if sh and (sh['tracking_status'],sh['carrier'],sh['tracking_number'])==(status,carrier,number) and not note:
        return ctx.redirect('/admin/shipment?id='+str(oid),'ไม่มีการเปลี่ยนแปลง')
    order_status={'preparing':'Confirmed','shipped':'Shipped','out_for_delivery':'Shipped','delivered':'Completed','exception':'Shipped'}[status]
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO shipments(order_id,carrier,tracking_number,tracking_status,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(order_id) DO UPDATE SET carrier=excluded.carrier,tracking_number=excluded.tracking_number,tracking_status=excluded.tracking_status,updated_at=CURRENT_TIMESTAMP',(oid,carrier,number,status))
        db.execute('INSERT INTO shipment_events(order_id,status,note,updated_by) VALUES(?,?,?,?)',(oid,status,note,ctx.user['id']))
        db.execute('UPDATE orders SET status=? WHERE id=?',(order_status,oid))
        db.commit()
    except Exception:db.rollback();raise
    return ctx.redirect('/admin/shipment?id='+str(oid),'อัปเดตสถานะจัดส่งแล้ว')

ROUTES={('GET','/tracking'):customer_tracking,('GET','/admin/shipping'):admin_shipments,('GET','/admin/shipment'):admin_shipment,('POST','/admin/shipment/save'):save_shipment}

"""Unified admin sales dashboard for daily, monthly and yearly views."""
import calendar
import re
from datetime import date, timedelta
from html import escape
from admin import guard, page

PERIODS={'day':('รายวัน',10),'month':('รายเดือน',7),'year':('รายปี',4)}
PAID="o.payment_status='paid' AND o.status!='Cancelled'"
STAMP="COALESCE(NULLIF(o.payment_reviewed_at,''),o.created_at)"

def period_dates(kind, chosen):
    if kind=='day':
        end=date.fromisoformat(chosen)
        return [(end-timedelta(days=i)).isoformat() for i in range(29,-1,-1)]
    if kind=='year':
        return [str(int(chosen)-i) for i in range(4,-1,-1)]
    y,m=map(int,chosen.split('-'))
    out=[]
    for i in range(11,-1,-1):
        z=y*12+m-1-i
        out.append(f'{z//12:04d}-{z%12+1:02d}')
    return out

def overview(ctx):
    denied=guard(ctx)
    if denied:return denied
    period=ctx.q.get('period','month')
    if period not in PERIODS:period='month'
    today=date.today()
    current={'day':today.isoformat(),'month':today.strftime('%Y-%m'),'year':str(today.year)}[period]
    chosen=ctx.q.get('date',current)
    regex={'day':r'\d{4}-\d{2}-\d{2}','month':r'\d{4}-\d{2}','year':r'\d{4}'}[period]
    try:
        if not re.fullmatch(regex,chosen):raise ValueError
        if period=='day':date.fromisoformat(chosen)
        elif period=='month':date.fromisoformat(chosen+'-01')
        else:date(int(chosen),1,1)
    except ValueError:chosen=current
    label,n=PERIODS[period]
    matches=f'substr({STAMP},1,{n})=?'
    summary=ctx.db.execute(f'''SELECT COUNT(*) orders_count,COALESCE(SUM(o.total),0) revenue,
         COALESCE(SUM(o.vat_amount),0) vat FROM orders o WHERE {PAID} AND {matches}''',(chosen,)).fetchone()
    products=ctx.db.execute(f'''SELECT oi.product_id,p.name,b.name brand,SUM(oi.quantity) units,
         COUNT(DISTINCT o.id) orders_count,COALESCE(SUM(oi.quantity*oi.unit_price),0) amount
         FROM order_items oi JOIN orders o ON o.id=oi.order_id
         JOIN products p ON p.id=oi.product_id LEFT JOIN brands b ON b.id=p.brand_id
         WHERE {PAID} AND {matches}
         GROUP BY oi.product_id,p.name,b.name ORDER BY units DESC,amount DESC,oi.product_id ASC''',(chosen,)).fetchall()
    variants=ctx.db.execute(f'''SELECT oi.product_id,p.name,COALESCE(oi.size_name,'') size_name,
         COALESCE(oi.color_name,'') color_name,SUM(oi.quantity) units,
         COALESCE(SUM(oi.quantity*oi.unit_price),0) amount
         FROM order_items oi JOIN orders o ON o.id=oi.order_id
         JOIN products p ON p.id=oi.product_id WHERE {PAID} AND {matches}
         GROUP BY oi.product_id,oi.size_name,oi.color_name
         ORDER BY units DESC,amount DESC,oi.product_id ASC''',(chosen,)).fetchall()
    timeline=period_dates(period,chosen)
    timeline_rows=ctx.db.execute(f'''SELECT substr({STAMP},1,{n}) k,COUNT(*) cnt,
         COALESCE(SUM(o.total),0) revenue FROM orders o
         WHERE {PAID} AND substr({STAMP},1,{n}) BETWEEN ? AND ?
         GROUP BY k''',(timeline[0],timeline[-1])).fetchall()
    timeline_map={r['k']:r for r in timeline_rows}
    maximum=max([float(r['revenue']) for r in timeline_rows]+[1])
    history=''.join(f'''<tr><td>{escape(key)}</td><td>{int(timeline_map[key]['cnt']) if key in timeline_map else 0:,}</td>
        <td>{ctx.baht(timeline_map[key]['revenue'] if key in timeline_map else 0)}</td>
        <td><div class="sales-bar-bg"><div class="sales-bar" style="width:{100*float(timeline_map[key]['revenue'])/maximum if key in timeline_map else 0:.2f}%"></div></div></td></tr>''' for key in timeline)
    product_rows=''.join(f'<tr><td>#{r["product_id"]}</td><td>{escape(r["name"])} · {escape(r["brand"] or "-")}</td><td>{r["units"]:,}</td><td>{r["orders_count"]:,}</td><td>{ctx.baht(r["amount"])}</td></tr>' for r in products) or '<tr><td colspan="5">ยังไม่มีรายการขายในช่วงนี้</td></tr>'
    variant_rows=''.join(f'<tr><td>#{r["product_id"]} {escape(r["name"])}</td><td>{escape(r["size_name"] or "ไม่ระบุ")}</td><td>{escape(r["color_name"] or "ไม่ระบุ")}</td><td>{r["units"]:,}</td><td>{ctx.baht(r["amount"])}</td></tr>' for r in variants) or '<tr><td colspan="5">ยังไม่มีรายการขายในช่วงนี้</td></tr>'
    best=products[0] if products else None
    winner=f'#{best["product_id"]} {escape(best["name"])} ({escape(best["brand"] or "-")}) — {best["units"]:,} ชิ้น' if best else 'ยังไม่มีสินค้าที่ขาย'
    links=''.join(f'<a class="btn {"" if period==p else "btn-outline"}" href="/admin/sales?period={p}">{title}</a> ' for p,(title,_) in PERIODS.items())
    input_type={'day':'date','month':'month','year':'number'}[period]
    input_extra=' min="2000" max="9999" step="1"' if period=='year' else ''
    total_units=sum(int(r['units']) for r in products)
    count=int(summary['orders_count'])
    body=f'''<p class="muted">รายงานอยู่หน้าเดียวกัน เลือก รายวัน / รายเดือน / รายปี เพื่อเปลี่ยนมุมมอง โดยใช้ข้อมูลออเดอร์ที่ยืนยันชำระเงินแล้ว</p>
    <div class="sales-period-tabs" style="display:flex;gap:8px;flex-wrap:wrap;margin:15px 0">{links}</div>
    <form method="get" action="/admin/sales" class="sales-month-form">
      <input type="hidden" name="period" value="{period}">
      <label>เลือก{label} <input type="{input_type}" name="date" value="{escape(chosen)}"{input_extra} required></label>
      <button class="btn" type="submit">แสดงรายงาน</button>
    </form>
    <div class="admin-stats">
      <div class="admin-tile"><small>ยอดรับชำระ {escape(label)}</small><strong>{ctx.baht(summary['revenue'])}</strong></div>
      <div class="admin-tile"><small>ออเดอร์ที่ชำระแล้ว</small><strong>{count:,}</strong></div>
      <div class="admin-tile"><small>จำนวนสินค้าที่ขาย</small><strong>{total_units:,} ชิ้น</strong></div>
      <div class="admin-tile"><small>ยอดเฉลี่ยต่อออเดอร์</small><strong>{ctx.baht(float(summary['revenue'])/count if count else 0)}</strong></div>
      <div class="admin-tile"><small>VAT ที่รวมอยู่ในยอดรับชำระ</small><strong>{ctx.baht(summary['vat'])}</strong></div>
    </div>
    <h2>สินค้าขายดีที่สุด — {escape(chosen)}</h2><p><strong>{winner}</strong></p>
    <h2>ยอดขายย้อนหลัง ({'30 วัน' if period=='day' else '12 เดือน' if period=='month' else '5 ปี'})</h2>
    <div class="admin-scroll"><table class="admin-table sales-table"><thead><tr><th>ช่วงเวลา</th><th>ออเดอร์</th><th>ยอดขาย</th><th>กราฟเปรียบเทียบ</th></tr></thead><tbody>{history}</tbody></table></div>
    <h2>ยอดขายแยกตามสินค้า — {escape(chosen)}</h2>
    <div class="admin-scroll"><table class="admin-table"><thead><tr><th>รหัส</th><th>สินค้า / แบรนด์</th><th>ขายได้ (ชิ้น)</th><th>ออเดอร์</th><th>ยอดขายสินค้า</th></tr></thead><tbody>{product_rows}</tbody></table></div>
    <details style="margin-top:20px"><summary style="cursor:pointer;font-weight:700">ดูยอดขายแยกตามไซส์และสี</summary><div class="admin-scroll"><table class="admin-table"><thead><tr><th>สินค้า</th><th>ไซส์</th><th>สี</th><th>ขายได้ (ชิ้น)</th><th>ยอดขาย</th></tr></thead><tbody>{variant_rows}</tbody></table></div></details>
    <p class="muted">รายงานใช้วันที่ยืนยันชำระเงิน (ออเดอร์เก่าที่ไม่มีวันที่นี้ใช้วันที่สั่งซื้อ) ไม่รวมรายการยกเลิกหรือคืนเงินแล้ว ยอดขายสินค้าต่างจากยอดรับชำระได้เพราะค่าจัดส่งและส่วนลด</p>'''
    return page(ctx,'รายงานยอดขายรายวัน / รายเดือน / รายปี',body)

ROUTES={('GET','/admin/sales'):overview,('GET','/admin/sales/overview'):overview}

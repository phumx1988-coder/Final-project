"""Admin-only monthly sales report, counted by confirmed payment date."""
import calendar
import re
from datetime import datetime, date
from html import escape
from admin import guard, page


def monthly_sales(ctx):
    denied = guard(ctx)
    if denied:
        return denied
    today = date.today()
    chosen = ctx.q.get('month', today.strftime('%Y-%m'))
    if not re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', chosen):
        chosen = today.strftime('%Y-%m')
    year, month = map(int, chosen.split('-'))
    months = []
    for index in range(11, -1, -1):
        y = year
        m = month - index
        while m <= 0:
            m += 12
            y -= 1
        months.append(f'{y:04d}-{m:02d}')

    # paid: refund/cancelled/failed orders are excluded; payment_reviewed_at marks confirmation.
    # Historical paid rows with no confirmation timestamp use created_at as fallback.
    records = ctx.db.execute('''
        SELECT substr(COALESCE(payment_reviewed_at, created_at),1,7) AS sale_month,
               COUNT(*) AS orders_count,
               COALESCE(SUM(total),0) AS revenue
        FROM orders
        WHERE payment_status='paid' AND status!='Cancelled'
          AND substr(COALESCE(payment_reviewed_at, created_at),1,7) BETWEEN ? AND ?
        GROUP BY sale_month
    ''', (months[0],months[-1])).fetchall()
    mapped = {r['sale_month']: r for r in records}
    selected = mapped.get(chosen)
    revenue = float(selected['revenue']) if selected else 0.0
    orders = int(selected['orders_count']) if selected else 0
    average = revenue/orders if orders else 0
    best = max([float(mapped[x]['revenue']) for x in months if x in mapped] + [1])

    entries = []
    for key in months:
        r = mapped.get(key)
        amount = float(r['revenue']) if r else 0
        n = int(r['orders_count']) if r else 0
        percent = max(0, min(100, amount/best*100))
        entries.append(f'''<tr><td>{escape(key)}</td><td>{n}</td><td>{ctx.baht(amount)}</td>
            <td><div class="sales-bar-bg" aria-label="ยอดขาย {ctx.baht(amount)}"><div class="sales-bar" style="width:{percent:.2f}%"></div></div></td></tr>''')
    # Aggregate purchased units from order_items, not current inventory. Use the same
    # paid/cancelled rules and month attribution as the summary above.
    product_records = ctx.db.execute('''
        SELECT oi.product_id, p.name AS product_name, b.name AS brand,
               SUM(oi.quantity) AS units_sold,
               COUNT(DISTINCT o.id) AS order_count,
               COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS gross_sales
        FROM order_items oi
        JOIN orders o ON o.id=oi.order_id
        JOIN products p ON p.id=oi.product_id
        LEFT JOIN brands b ON b.id=p.brand_id
        WHERE o.payment_status='paid' AND o.status!='Cancelled'
          AND substr(COALESCE(o.payment_reviewed_at,o.created_at),1,7)=?
        GROUP BY oi.product_id, p.name, b.name
        ORDER BY units_sold DESC, gross_sales DESC, oi.product_id ASC
    ''', (chosen,)).fetchall()
    product_rows = ''.join(
        f'<tr><td>#{r["product_id"]}</td>'
        f'<td><b>{escape(r["product_name"])}</b><small style="display:block" class="muted">{escape(r["brand"] or "-")}</small></td>'
        f'<td class="number">{r["units_sold"]:,}</td>'
        f'<td class="number">{r["order_count"]:,}</td>'
        f'<td class="number">{ctx.baht(r["gross_sales"])}</td></tr>'
        for r in product_records
    ) or '<tr><td colspan="5" class="muted">เดือนนี้ยังไม่มีสินค้าที่ขายและยืนยันชำระเงินแล้ว</td></tr>'
    units_total = sum(int(r['units_sold']) for r in product_records)
    product_value = sum(float(r['gross_sales']) for r in product_records)

    variant_records = ctx.db.execute('''
        SELECT oi.product_id, p.name AS product_name,
               COALESCE(oi.size_name,'') AS size_name,
               COALESCE(oi.color_name,'') AS color_name,
               SUM(oi.quantity) AS units_sold,
               COALESCE(SUM(oi.quantity * oi.unit_price),0) AS gross_sales
        FROM order_items oi
        JOIN orders o ON o.id=oi.order_id
        JOIN products p ON p.id=oi.product_id
        WHERE o.payment_status='paid' AND o.status!='Cancelled'
          AND substr(COALESCE(o.payment_reviewed_at,o.created_at),1,7)=?
        GROUP BY oi.product_id, oi.size_name, oi.color_name
        ORDER BY units_sold DESC, gross_sales DESC, oi.product_id ASC
    ''', (chosen,)).fetchall()
    variant_rows = ''.join(
        f'<tr><td>#{r["product_id"]} · {escape(r["product_name"])}</td>'
        f'<td>{escape(r["size_name"] or "ไม่ระบุ")}</td>'
        f'<td>{escape(r["color_name"] or "ไม่ระบุ")}</td>'
        f'<td class="number">{r["units_sold"]:,}</td>'
        f'<td class="number">{ctx.baht(r["gross_sales"])}</td></tr>'
        for r in variant_records
    ) or '<tr><td colspan="5" class="muted">ไม่มีข้อมูลไซส์และสีของสินค้าที่ขายในเดือนนี้</td></tr>'

    body = f'''<p class="muted">นับรายได้ตามเดือนที่แอดมินยืนยันการชำระเงิน ไม่รวมคำสั่งซื้อที่ยกเลิกหรือคืนเงินแล้ว</p>
    <form method="get" action="/admin/sales" class="sales-month-form">
       <label>เลือกเดือน <input type="month" name="month" value="{escape(chosen)}" required></label>
       <button class="btn" type="submit">แสดงรายงาน</button>
    </form>
    <div class="admin-stats">
       <div class="admin-tile"><small>ยอดขายเดือน {escape(chosen)}</small><strong>{ctx.baht(revenue)}</strong></div>
       <div class="admin-tile"><small>คำสั่งซื้อที่ชำระแล้ว</small><strong>{orders}</strong></div>
       <div class="admin-tile"><small>เฉลี่ยต่อคำสั่งซื้อ</small><strong>{ctx.baht(average)}</strong></div>
    </div>
    <h2>ยอดขาย 12 เดือน (รวมเดือนที่เลือก)</h2>
    <div class="admin-scroll"><table class="admin-table sales-table">
    <thead><tr><th>เดือน</th><th>ออเดอร์</th><th>ยอดขาย</th><th>กราฟเปรียบเทียบ</th></tr></thead>
    <tbody>{''.join(entries)}</tbody></table></div>
    <h2>ยอดขายสินค้าแต่ละรุ่น — {escape(chosen)}</h2>
    <p class="muted">ขายรวม {units_total:,} ชิ้น จาก {len(product_records):,} รุ่น · ยอดขายสินค้า {ctx.baht(product_value)} (ยังไม่รวมค่าจัดส่ง/ส่วนลดระดับออเดอร์) เรียงจากจำนวนที่ขายมากที่สุด</p>
    <div class="admin-scroll"><table class="admin-table">
      <thead><tr><th>รหัส</th><th>ชื่อสินค้า / แบรนด์</th><th class="number">ขายได้ (ชิ้น)</th><th class="number">ออเดอร์</th><th class="number">ยอดขายสินค้า</th></tr></thead>
      <tbody>{product_rows}</tbody></table></div>
    <details style="margin-top:20px"><summary style="cursor:pointer;font-weight:700">ดูยอดขายแยกตามไซส์และสี</summary>
      <div class="admin-scroll"><table class="admin-table">
      <thead><tr><th>สินค้า</th><th>ไซส์</th><th>สี</th><th class="number">ขายได้ (ชิ้น)</th><th class="number">ยอดขายสินค้า</th></tr></thead>
      <tbody>{variant_rows}</tbody></table></div>
    </details>
    <p class="muted">จำนวนสินค้านับจากรายการในออเดอร์ที่ชำระเงินแล้ว ไม่รวมออเดอร์ที่ยกเลิก/คืนเงินแล้ว และไม่ใช่จำนวนคงเหลือในสต็อก<br>ยอดขายสินค้าอาจต่างจากยอดรับชำระ เนื่องจากค่าจัดส่งและส่วนลดของคำสั่งซื้อ</p>
    <p class="muted">รายการเก่าที่ไม่มีวันที่ยืนยันชำระเงิน จะใช้วันที่สร้างคำสั่งซื้อแทนเพื่อความเข้ากันได้</p>'''
    return page(ctx, 'รายงานยอดขายรายเดือน', body)

ROUTES = {('GET','/admin/sales'):monthly_sales}

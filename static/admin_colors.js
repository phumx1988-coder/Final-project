(() => {
  const pick = document.getElementById('new-color-picker');
  const hex = document.getElementById('new-color-hex');
  const name = document.getElementById('new-color-name');
  const lines = document.getElementById('product-color-lines');
  const add = document.getElementById('add-product-color');
  const message = document.getElementById('color-editor-message');
  if (!pick || !hex || !name || !lines || !add || !message) return;
  const valid = value => /^#[0-9a-fA-F]{6}$/.test(value);
  pick.addEventListener('input', () => {hex.value = pick.value.toUpperCase(); message.textContent = '';});
  hex.addEventListener('input', () => {
    const value = hex.value.trim();
    if (valid(value)) {pick.value = value; message.textContent = '';}
  });
  add.addEventListener('click', () => {
    const label = name.value.trim();
    const color = hex.value.trim().toUpperCase();
    if (!label || label.length > 50 || label.includes('|')) {message.textContent = 'กรุณาใส่ชื่อสีให้ถูกต้อง'; return;}
    if (!valid(color)) {message.textContent = 'รหัสสีต้องอยู่ในรูปแบบ #RRGGBB'; return;}
    const entries = lines.value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (entries.length >= 30) {message.textContent = 'เพิ่มได้สูงสุด 30 สีต่อสินค้า'; return;}
    if (entries.some(line => line.split('|')[0].trim().toLocaleLowerCase() === label.toLocaleLowerCase())) {
      message.textContent = 'ชื่อสีนี้อยู่ในรายการแล้ว'; return;
    }
    const entry = `${label} | ${color}`;
    if ((lines.value.trim().length + entry.length + 1) > 2000) {message.textContent = 'รายการสียาวเกินกำหนด'; return;}
    lines.value = entries.concat(entry).join('\n');
    name.value = '';
    message.textContent = `เพิ่มสี ${label} (${color}) แล้ว อย่าลืมกดบันทึกสินค้า`;
  });
})();

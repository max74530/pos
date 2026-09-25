// WEBPOS v0.5 — 實體鍵盤優先 + 觸控備用（品名/數量/單價三欄）
let selectedId = null;

const $ = (id) => document.getElementById(id);

function showError(msg) {
  const el = $("error-msg");
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(showError._t);
  showError._t = setTimeout(() => { el.style.display = "none"; }, 4000);
}

function friendlyErr(e) {
  const m = e.message || "";
  if (m.includes("單價超出範圍")) return "單價請輸入 1 到 5000";
  if (m.includes("數量超出範圍")) return "數量請輸入 1 到 99";
  return m;
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}

async function refreshCart() {
  const d = await api("/api/cart");
  $("total").textContent = "總計金額: $" + d.total + " 元";
  const tb = $("cart-body");
  tb.innerHTML = "";
  d.items.forEach((it, idx) => {
    const tr = document.createElement("tr");
    if (it.id === selectedId) tr.className = "selected";
    const no = document.createElement("td");
    no.textContent = (idx + 1) + ".";
    const nm = document.createElement("td");
    nm.textContent = it.empty ? "(空白)" : it.item_name;
    const qt = document.createElement("td");
    qt.textContent = it.empty ? "" : ("×" + it.qty);
    const pr = document.createElement("td");
    pr.textContent = it.empty ? "" : ("$" + it.unit_price);
    const amt = document.createElement("td");
    amt.textContent = it.empty ? "" : ("$" + it.amount + " 元");
    const ops = document.createElement("td");
    ops.className = "row-ops";
    if (!it.empty) {
      const b1 = document.createElement("button");
      b1.textContent = "M 修改";
      b1.onclick = () => editRow(it.id, it.item_name, it.qty, it.unit_price);
      const b2 = document.createElement("button");
      b2.textContent = "Del 刪";
      b2.onclick = () => delRow(it.id);
      ops.appendChild(b1); ops.appendChild(b2);
    }
    tr.appendChild(no); tr.appendChild(nm); tr.appendChild(qt);
    tr.appendChild(pr); tr.appendChild(amt); tr.appendChild(ops);
    tr.onclick = () => { selectedId = it.id; refreshCart(); };
    tb.appendChild(tr);
  });
}

async function refreshInvoice() {
  try {
    const d = await api("/api/invoice/next");
    if (d.invoice_no) $("invoice-input").value = d.invoice_no;
    try {
      const s = await api("/api/invoice/seq");
      const fmt = (n) => String(n).padStart(8, "0");
      $("invoice-used").textContent = "下一張：" + s.prefix + fmt(s.current_no);
    } catch (e) { /* 略過 */ }
    const w = $("invoice-warn");
    if (d.exhausted) {
      w.style.display = "inline-block";
      w.textContent = "發票已用罄！請設定新字軌";
    } else if (d.warning) {
      w.style.display = "inline-block";
      w.textContent = "發票剩餘 " + d.remaining + " 張";
    } else {
      w.style.display = "none";
    }
  } catch (e) { /* 尚未設定字軌時略過 */ }
}

function activeField() {
  const a = document.activeElement;
  if (a && (a.id === "qty-input" || a.id === "price-input")) return a;
  return $("price-input");
}

function tapDigit(d) {
  const f = activeField();
  f.value += d;
  f.focus();
}

function clearActiveField() {
  activeField().value = "";
  activeField().focus();
}

function setPrice(v) {
  $("price-input").value = v;
  $("price-input").focus();
}

function readLine() {
  const name = $("name-input").value.trim() || "文具";
  const qty = parseInt($("qty-input").value, 10);
  const price = parseInt($("price-input").value, 10);
  if (isNaN(qty) || qty < 1 || qty > 99) { showError("數量請輸入 1 到 99"); $("qty-input").focus(); return null; }
  if (isNaN(price) || price < 1 || price > 5000) { showError("單價請輸入 1 到 5000"); $("price-input").focus(); return null; }
  return {item_name: name, qty: qty, unit_price: price};
}

async function addFromInput() {
  const line = readLine();
  if (!line) return;
  try {
    await api("/api/cart/add", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(line),
    });
    $("price-input").value = "";
    $("qty-input").value = "1";
    $("price-input").focus();
    await refreshCart();
  } catch (e) { showError(friendlyErr(e)); }
}

async function editRow(id, oldName, oldQty, oldPrice) {
  const name = prompt("品名：", oldName);
  if (name === null) return;
  const q = prompt("數量（1-99）：", oldQty);
  if (q === null) return;
  const p = prompt("單價（1-5000）：", oldPrice);
  if (p === null) return;
  const qty = parseInt(q, 10), price = parseInt(p, 10);
  if (!name.trim()) { showError("品名不可空白"); return; }
  if (isNaN(qty) || qty < 1 || qty > 99) { showError("數量請輸入 1 到 99"); return; }
  if (isNaN(price) || price < 1 || price > 5000) { showError("單價請輸入 1 到 5000"); return; }
  try {
    await api("/api/cart/" + id, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({item_name: name.trim(), qty: qty, unit_price: price}),
    });
    await refreshCart();
  } catch (e) { showError(friendlyErr(e)); }
}

async function delRow(id) {
  if (!confirm("確定刪除第這筆金額嗎？")) return;
  try {
    await api("/api/cart/" + id, {method: "DELETE"});
    if (selectedId === id) selectedId = null;
    await refreshCart();
  } catch (e) { showError(e.message); }
}

async function clearAll() {
  if (!confirm("確定清除整張單嗎？")) return;
  await api("/api/cart/clear", {method: "DELETE"});
  selectedId = null;
  await refreshCart();
}

async function checkout() {
  const no = $("invoice-input").value.trim().toUpperCase();
  if (!/^[A-Z]{2}[0-9]{8}$/.test(no)) {
    showError("發票格式錯誤：前2碼英文大寫＋後8碼數字");
    $("invoice-input").focus();
    return;
  }
  const cart = await api("/api/cart");
  if (!cart.count) { showError("明細清單為空，無法結帳"); return; }
  let shop = {};
  try { shop = await api("/api/shop/config"); } catch (e) { /* 用預設 */ }
  if (!shop.shop_name) {
    showError("請先完成商店設定");
    openShopSettings();
    return;
  }
  const today = new Date().toLocaleDateString("zh-TW", {year: "numeric", month: "2-digit", day: "2-digit"});
  let rows = "";
  cart.items.filter((it) => !it.empty).forEach((it, i) => {
    rows += "<tr><td>" + (i + 1) + "</td><td>" + it.item_name + "</td><td>×"
      + it.qty + "</td><td>$" + it.unit_price + "</td><td>$" + it.amount + "</td></tr>";
  });
  let html = "<h2>二聯式統一發票（模擬）</h2>";
  html += "<table><tr><th>營業人</th><td>" + (shop.shop_name || "成功文具行") + "</td>"
    + "<th>統編</th><td>" + (shop.tax_id || "") + "</td></tr>";
  html += "<tr><th>發票號碼</th><td>" + no + "</td><th>日期</th><td>" + today + "</td></tr></table>";
  html += "<table><tr><th>項次</th><th>品名</th><th>數量</th><th>單價</th><th>總金額</th></tr>" + rows + "</table>";
  html += "<h2>總計：$" + cart.total + " 元</h2>";
  html += "<label class='field-label' for='pay-tendered'>收現（Enter 直接確認）</label>"
    + "<input id='pay-tendered' inputmode='numeric' style='font-size:36px;width:100%' value='" + cart.total + "'>"
    + "<h2 id='pay-change'>找零：$0 元</h2>";
  html += "<p><button id='btn-confirm-checkout' onclick=\"doCheckout('" + no + "')\">確認結帳 (Enter)</button> "
    + "<button onclick=\"document.getElementById('modal').style.display='none'\">取消 (Esc)</button></p>";
  $("modal-box").innerHTML = html;
  $("modal").style.display = "block";
  const upd = () => {
    const t = parseInt($("pay-tendered").value, 10);
    $("pay-change").textContent = (!isNaN(t) && t >= cart.total)
      ? ("找零：$" + (t - cart.total) + " 元") : "找零：—";
  };
  $("pay-tendered").addEventListener("input", upd);
  $("pay-tendered").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); doCheckout(no); }
  }, true);
  $("pay-tendered").focus();
  $("pay-tendered").select();
}

function nowHM() {
  const n = new Date();
  const p = (x) => String(x).padStart(2, "0");
  return n.getFullYear() + "-" + p(n.getMonth() + 1) + "-" + p(n.getDate())
    + " " + p(n.getHours()) + ":" + p(n.getMinutes());
}

function receiptHTML(shop, lines, total, tendered, change, dt) {
  let rows = "";
  lines.forEach((it, i) => {
    rows += "<div>" + (i + 1) + ". " + it.item_name + " $" + it.unit_price
      + "*" + it.qty + " " + it.amount + "T</div>";
  });
  return "<html><head><meta charset='utf-8'><title>交易明細</title><style>"
    + "body{font-family:sans-serif;color:#000;background:#fff;font-size:20px;padding:24px;}"
    + "h1{font-size:28px;margin:2px 0;}p{margin:2px 0;}h2{margin-top:8px;}</style></head><body>"
    + "<h1>" + (shop.shop_name || "") + "</h1>"
    + "<p>" + (shop.tax_id || "") + "</p>"
    + "<p>" + (shop.address || "") + "</p>"
    + "<p>" + (shop.phone || "") + "</p>"
    + "<p>" + dt + "</p>"
    + rows
    + "<h2>合計：" + total + "<br>應收：" + total + "<br>收現：" + tendered
    + "<br>找零：" + change + "</h2>"
    + "</body></html>";
}

async function doCheckout(no) {
  const btn = $("btn-confirm-checkout");
  if (btn) { btn.disabled = true; btn.textContent = "結帳中…"; }
  const tendered = parseInt(($("pay-tendered") || {}).value, 10);
  // 先開空窗（點擊手勢內，避阻擋）；被擋則退回手動鈕
  let pw = null;
  try { pw = window.open("", "_blank", "width=500,height=700"); } catch (e) { pw = null; }
  try {
    const cart = await api("/api/cart");
    const lines = cart.items.filter((it) => !it.empty);
    if (!lines.length) throw new Error("明細清單為空，無法結帳");
    const shop = await api("/api/shop/config").catch(() => ({}));
    const d = await api("/api/checkout", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({invoice_no: no, tendered: isNaN(tendered) ? cart.total : tendered}),
    });
    selectedId = null;
    await refreshCart().catch(() => {});
    await refreshInvoice().catch(() => {});
    const html = receiptHTML(shop, lines, d.total, d.tendered, d.change, nowHM());
    let printBtn = "";
    if (!pw || pw.closed) {
      printBtn = "<button onclick='reprintInvoice(\"" + d.invoice_no + "\")'>列印交易明細</button> ";
    } else {
      pw.document.write(html);
      pw.document.close();
      pw.focus();
      pw.print();
    }
    let done = "<h2>結帳完成</h2><p style='font-size:32px;font-weight:bold'>找零：$" + d.change + " 元</p>";
    done += "<p>" + printBtn
      + "<button onclick=\"document.getElementById('modal').style.display='none';document.getElementById('name-input').focus()\">下一筆 (Esc)</button></p>";
    $("modal-box").innerHTML = done;
    $("modal").style.display = "block";
  } catch (e) {
    try { if (pw && !pw.closed) pw.close(); } catch (e2) {}
    // 失敗訊息留在視窗內，不關視窗、不讓訊息躲到背後
    let html = "<h2>結帳失敗</h2><p style='color:#B00020;font-weight:bold'>"
      + friendlyErr(e) + "</p>";
    html += "<p><button onclick=\"document.getElementById('modal').style.display='none';refreshCart();refreshInvoice();\">關閉 (Esc)</button></p>";
    $("modal-box").innerHTML = html;
    $("modal").style.display = "block";
  }
}

async function reprintInvoice(no) {
  const d = await api("/api/invoice/" + no);
  const w = window.open("", "_blank", "width=500,height=700");
  if (!w) { showError("列印視窗被阻擋，請允許彈出視窗"); return; }
  w.document.write(receiptHTML(d.shop, d.lines, d.invoice.total_amount,
    d.invoice.tendered, d.invoice.change, d.invoice.created_at.slice(0, 16)));
  w.document.close();
  w.focus();
  w.print();
}

async function openShopSettings() {
  let cur = {};
  try { cur = await api("/api/shop/config"); } catch (e) { cur = {}; }
  const v = (k) => (cur[k] || "").replace(/'/g, "&#39;");
  let html = "<h2>商店設定</h2>";
  html += "<label class='field-label' for='shop-name'>1. 公司名稱</label>"
    + "<input id='shop-name' style='font-size:32px;width:100%' value='" + v("shop_name") + "'>";
  html += "<label class='field-label' for='shop-tax'>2. 統編號碼（8碼）</label>"
    + "<input id='shop-tax' inputmode='numeric' maxlength='8' style='font-size:32px;width:100%' value='" + v("tax_id") + "'>";
  html += "<label class='field-label' for='shop-addr'>3. 地址</label>"
    + "<input id='shop-addr' style='font-size:32px;width:100%' value='" + v("address") + "'>";
  html += "<label class='field-label' for='shop-phone'>4. 電話</label>"
    + "<input id='shop-phone' style='font-size:32px;width:100%' value='" + v("phone") + "'>";
  html += "<p><button onclick='saveShopSettings()'>儲存</button> "
    + "<button onclick=\"document.getElementById('modal').style.display='none'\">取消 (Esc)</button></p>";
  $("modal-box").innerHTML = html;
  $("modal").style.display = "block";
  $("shop-name").focus();
}

async function saveShopSettings() {
  const name = $("shop-name").value.trim();
  const tax = $("shop-tax").value.trim();
  const addr = $("shop-addr").value.trim();
  const phone = $("shop-phone").value.trim();
  if (!name) { alert("公司名稱不可空白"); $("shop-name").focus(); return; }
  if (!/^\d{8}$/.test(tax)) { alert("統編號碼必須是 8 碼數字"); $("shop-tax").focus(); return; }
  if (!addr) { alert("地址不可空白"); $("shop-addr").focus(); return; }
  if (!phone) { alert("電話不可空白"); $("shop-phone").focus(); return; }
  // 字軌前綴跟實際 invoice_seq 走（商店設定不管字軌）
  let prefix = "";
  try { prefix = (await api("/api/invoice/seq")).prefix || ""; } catch (e) {}
  if (!/^[A-Z]{2}$/.test(prefix)) { alert("請先完成字軌設定"); return; }
  try {
    await api("/api/shop/config", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({tax_id: tax, shop_name: name, invoice_prefix: prefix, address: addr, phone: phone}),
    });
    $("modal").style.display = "none";
    const t = document.getElementById("shop-title");
    if (t) {
      const i = t.textContent.indexOf(" POS 系統");
      t.textContent = name + (i >= 0 ? t.textContent.slice(i) : " POS 系統");
    }
    document.title = t ? t.textContent : document.title;
    alert("商店設定已更新");
  } catch (e) { alert(friendlyErr(e)); }
}

async function openSeqSettings() {
  let cur = {};
  try { cur = await api("/api/invoice/seq"); } catch (e) { cur = {}; }
  let nxt = {};
  try { nxt = await api("/api/invoice/next"); } catch (e) { nxt = {}; }
  const fmt = (n) => String(n == null ? "" : n).padStart(8, "0");
  let html = "<h2>發票字軌設定</h2>";
  if (cur.prefix) {
    const used = cur.current_no - cur.start_no;
    const total = cur.end_no - cur.start_no + 1;
    html += "<p>目前：前二碼 " + cur.prefix + "／開始 " + fmt(cur.start_no)
      + "／停止 " + fmt(cur.end_no) + "<br>已用 " + used + "／共 " + total
      + " 張，剩餘 " + (nxt.remaining != null ? nxt.remaining : "?") + " 張</p>";
  } else {
    html += "<p>尚未設定字軌，請輸入新發票本範圍</p>";
  }
  html += "<label class='field-label' for='seq-prefix'>1. 前二碼英文</label>"
    + "<input id='seq-prefix' maxlength='2' style='font-size:36px;width:100%;text-transform:uppercase' value='" + (cur.prefix || "") + "'>";
  html += "<label class='field-label' for='seq-start'>2. 開始號碼（8碼數字）</label>"
    + "<input id='seq-start' inputmode='numeric' maxlength='8' style='font-size:36px;width:100%' value='" + (cur.start_no != null ? fmt(cur.start_no) : "") + "'>";
  html += "<label class='field-label' for='seq-end'>3. 停止號碼（8碼數字）</label>"
    + "<input id='seq-end' inputmode='numeric' maxlength='8' style='font-size:36px;width:100%' value='" + (cur.end_no != null ? fmt(cur.end_no) : "") + "'>";
  html += "<p><button onclick='saveSeqSettings()'>儲存</button> "
    + "<button onclick=\"document.getElementById('modal').style.display='none'\">取消 (Esc)</button></p>";
  $("modal-box").innerHTML = html;
  $("modal").style.display = "block";
  $("seq-prefix").focus();
}

async function saveSeqSettings() {
  const prefix = $("seq-prefix").value.trim().toUpperCase();
  const startRaw = $("seq-start").value.trim();
  const endRaw = $("seq-end").value.trim();
  if (!/^[A-Z]{2}$/.test(prefix)) { alert("前二碼必須是 2 個英文字母"); $("seq-prefix").focus(); return; }
  if (!/^\d{8}$/.test(startRaw)) { alert("開始號碼必須是 8 碼數字"); $("seq-start").focus(); return; }
  if (!/^\d{8}$/.test(endRaw)) { alert("停止號碼必須是 8 碼數字"); $("seq-end").focus(); return; }
  const start = parseInt(startRaw, 10), end = parseInt(endRaw, 10);
  if (start > end) { alert("開始號碼不可大於停止號碼"); $("seq-start").focus(); return; }
  // 目前號碼不給改：同本（前綴＋開始號不變）沿用進度並夾在新範圍內；換新本從開始號
  let curr = start;
  try {
    const old = await api("/api/invoice/seq");
    if (old.prefix === prefix && old.start_no === start) {
      curr = Math.min(Math.max(old.current_no, start), end + 1);
    }
  } catch (e) { /* 無舊字軌就從開始號 */ }
  try {
    await api("/api/invoice/seq", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({prefix: prefix, current_no: curr, start_no: start, end_no: end}),
    });
    $("modal").style.display = "none";
    await refreshInvoice();
    alert("字軌已更新：" + prefix + startRaw + "–" + prefix + endRaw);
  } catch (e) { alert(friendlyErr(e)); }
}

function currentYM() {
  const n = new Date();
  return n.getFullYear() + "-" + String(n.getMonth() + 1).padStart(2, "0");
}

async function openReport(ym) {
  ym = ym || currentYM();
  const d = await api("/api/report/monthly?month=" + ym);
  const roc = (parseInt(ym.slice(0, 4), 10) - 1911) + " 年 " + parseInt(ym.slice(5, 7), 10) + " 月份";
  const shop = d.shop || {};
  let html = "<h2>營業人使用二聯式收銀機統一發票明細表</h2>";
  html += "<div>中華民國 " + roc + "（第 " + d.period + " 期申報）</div>";
  html += "<table><tr><th>統一編號</th><td>" + (shop.tax_id || "") + "</td>"
    + "<th>發票字軌</th><td>" + (shop.invoice_prefix || "") + "</td></tr>";
  html += "<tr><th>營業人名稱</th><td colspan='3'>" + (shop.shop_name || "") + "</td></tr></table>";
  html += "<div>月份：<input id='rpt-month' type='month' value='" + ym + "'> "
    + "<button onclick=\"openReport(document.getElementById('rpt-month').value)\">查詢</button> "
    + "<button onclick=\"print401()\">列印本表</button></div>";
  html += "<div id='print401'>";
  html += "<table><tr><th>日期</th><th>發票起訖號碼</th><th>張數</th><th>發票總金額</th></tr>";
  d.days.forEach((dd) => {
    const rng = dd.count ? (dd.start_no + (dd.count > 1 ? "–" + dd.end_no : "")) : "";
    html += "<tr><td>" + dd.day + "</td><td>" + rng + "</td><td>"
      + (dd.count || "") + "</td><td>" + (dd.total || "") + "</td></tr>";
  });
  html += "</table>";
  html += "<table><tr><th>項目</th><th>發票總金額</th><th>銷售額</th><th>稅額</th></tr>";
  html += "<tr><td>本月總計（" + d.invoice_count + " 張）</td><td>" + d.total_amount
    + "</td><td>" + d.sales_amount + "</td><td>" + d.tax_amount + "</td></tr></table>";
  if (d.void_list.length) {
    html += "<div>誤開作廢：" + d.void_list.join("、") + "（共 " + d.void_count + " 張）</div>";
  }
  html += "</div>";
  html += "<p><button onclick=\"openDaily()\">今日日結</button> "
    + "<button onclick=\"document.getElementById('modal').style.display='none'\">關閉 (Esc)</button></p>";
  $("modal-box").innerHTML = html;
  $("modal").style.display = "block";
}

async function openDaily() {
  const d = await api("/api/report/daily");
  let html = "<h2>日結報表 " + d.date + "</h2>";
  html += "<table><tr><th>項目</th><th>數值</th></tr>";
  html += "<tr><td>總銷售金額</td><td>$" + d.total_amount + "</td></tr>";
  html += "<tr><td>交易筆數</td><td>" + d.total_count + "</td></tr>";
  html += "<tr><td>作廢張數</td><td>" + d.void_count + "</td></tr>";
  html += "<tr><td>作廢金額</td><td>$" + d.void_amount + "</td></tr>";
  html += "<tr><td>發票起號</td><td>" + d.start_invoice + "</td></tr>";
  html += "<tr><td>發票訖號</td><td>" + d.end_invoice + "</td></tr></table>";
  html += "<p><a href='/api/report/export_csv?date=" + d.date + "'>下載 CSV</a></p>";
  html += "<table><tr><th>發票號</th><th>金額</th><th>作廢</th><th>操作</th></tr>";
  d.invoices.forEach((inv) => {
    html += "<tr><td>" + inv.invoice_no + "</td><td>$" + inv.total_amount
      + "</td><td>" + (inv.is_void ? "作廢" : "") + "</td>"
      + "<td>" + (inv.is_void ? "" : "<button onclick=\"voidInvoice('" + inv.invoice_no + "')\">作廢</button>")
      + " <button onclick=\"printReceipt('" + inv.invoice_no + "'," + inv.total_amount + ",'" + d.date + "')\">列印</button></td></tr>";
  });
  html += "</table>";
  html += "<p><button onclick=\"openReport()\">回月報 (F5)</button> "
    + "<button onclick=\"document.getElementById('modal').style.display='none'\">關閉 (Esc)</button></p>";
  $("modal-box").innerHTML = html;
  $("modal").style.display = "block";
}

function print401() {
  const ym = (document.getElementById("rpt-month") || {}).value || "";
  const part = document.getElementById("print401").innerHTML;
  const w = window.open("", "_blank", "width=900,height=700");
  if (!w) { showError("列印視窗被阻擋，請允許彈出視窗"); return; }
  w.document.write("<html><head><meta charset='utf-8'><title>401明細表 " + ym + "</title><style>"
    + "body{font-family:sans-serif;color:#000;background:#fff;font-size:18px;padding:24px;}"
    + "h2{font-size:24px;}table{width:100%;border-collapse:collapse;}"
    + "td,th{border:1px solid #000;padding:4px 8px;}</style></head><body>"
    + "<h2>營業人使用二聯式收銀機統一發票明細表</h2>" + part + "</body></html>");
  w.document.close();
  w.focus();
  w.print();
}

async function voidInvoice(no) {
  if (!confirm("確定作廢發票 " + no + " 嗎？")) return;
  try {
    await api("/api/invoice/" + no + "/void", {method: "POST"});
    await openReport();
  } catch (e) { showError(e.message); }
}

function printReceipt(no) {
  // 日結重印：走明細端點，用新五段格式（不印發票號）
  reprintInvoice(no);
}

function moveSelection(dir) {
  const rows = document.querySelectorAll("#cart-body tr");
  let ids = [];
  rows.forEach((tr) => {
    const btn = tr.querySelector(".row-ops button");
    if (btn) {
      const m = btn.getAttribute("onclick").match(/editRow\((\d+),/);
      if (m) ids.push(parseInt(m[1], 10));
    }
  });
  if (!ids.length) return;
  let i = ids.indexOf(selectedId);
  if (i < 0) i = dir > 0 ? -1 : 0;
  i = Math.min(ids.length - 1, Math.max(0, i + dir));
  selectedId = ids[i];
  refreshCart();
}

// 實體鍵盤全域綁定
const INPUT_IDS = ["name-input", "qty-input", "price-input"];
function inInput() {
  const a = document.activeElement || {};
  return a.tagName === "INPUT" && INPUT_IDS.includes(a.id);
}
document.addEventListener("keydown", (e) => {
  if ($("modal").style.display === "block") {
    if (e.key === "Escape") $("modal").style.display = "none";
    return;
  }
  const tag = (document.activeElement || {}).tagName;
  const typing = tag === "INPUT" && !INPUT_IDS.includes(document.activeElement.id);
  if (e.key === "F9") { e.preventDefault(); checkout(); }
  else if (e.key === "F5") { e.preventDefault(); openReport(); }
  else if (e.key === "ArrowDown") { e.preventDefault(); moveSelection(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); moveSelection(-1); }
  else if ((e.key === "m" || e.key === "M") && selectedId && !inInput()) {
    const rows = document.querySelectorAll("#cart-body tr.selected .row-ops button");
    if (rows.length) rows[0].click();
  } else if (e.key === "Delete" && selectedId && !inInput()) {
    delRow(selectedId);
  } else if (e.key === "Escape") {
    const a = document.activeElement;
    if (a && INPUT_IDS.includes(a.id) && a.value) {
      a.value = "";
    } else { clearAll(); }
  }
  if (typing) return;
});

window.addEventListener("DOMContentLoaded", () => {
  ["name-input", "qty-input", "price-input"].forEach((id, i, arr) => {
    $(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (id === "price-input") addFromInput();
        else $(arr[i + 1]).focus();
      }
      e.stopPropagation();
    }, true);
  });
  // 阻止 F5/Enter 在按鈕上的預設行為造成重複
  refreshCart();
  refreshInvoice();
  $("price-input").focus();
  // 商店未設定：強制先填（無預設值）
  api("/api/shop/config").then((s) => {
    if (!s.shop_name) openShopSettings();
  }).catch(() => {});
});

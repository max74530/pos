# database.py — WEBPOS 本地 SQLite 資料庫模組
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "webpos.db")

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def get_db():
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    ensure_data_dir()
    conn = get_db()
    cursor = conn.cursor()

    # 1. 明細檔 / 銷售單記錄（v0.5：品名＋數量＋單價，小計 amount = qty * unit_price）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount INTEGER NOT NULL CHECK (amount >= 1),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        invoice_no TEXT,
        void_flag INTEGER DEFAULT 0,
        item_name TEXT NOT NULL DEFAULT '文具',
        qty INTEGER NOT NULL DEFAULT 1,
        unit_price INTEGER NOT NULL DEFAULT 0
    );
    """)
    # 舊庫遷移：補欄位（冪等）
    cols = {r[1] for r in cursor.execute("PRAGMA table_info(sales)").fetchall()}
    for col, ddl in (
        ("item_name", "ALTER TABLE sales ADD COLUMN item_name TEXT NOT NULL DEFAULT '文具'"),
        ("qty", "ALTER TABLE sales ADD COLUMN qty INTEGER NOT NULL DEFAULT 1"),
        ("unit_price", "ALTER TABLE sales ADD COLUMN unit_price INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in cols:
            cursor.execute(ddl)
    # 舊資料回填單價（qty=1 時單價＝小計）
    cursor.execute("UPDATE sales SET unit_price = amount WHERE unit_price = 0 AND qty = 1")

    # 2. 發票主檔
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_no TEXT PRIMARY KEY,
        total_amount INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_void INTEGER DEFAULT 0
    );
    """)

    # 3. 發票字軌與計數檔
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_seq (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        prefix TEXT NOT NULL CHECK (length(prefix) = 2),
        current_no INTEGER NOT NULL,
        start_no INTEGER NOT NULL,
        end_no INTEGER NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 預設寫入一筆初始發票字軌 (例如 AB12345600 ~ AB12345799)
    cursor.execute("SELECT COUNT(*) FROM invoice_seq")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO invoice_seq (id, prefix, current_no, start_no, end_no)
        VALUES (1, 'AB', 12345601, 12345601, 12345800)
        """)

    # 4. 商店設定檔（v0.6：401 表頭＋列印用；無預設值，首跑強制填寫）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shop_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # 5. 發票收現找零欄（v0.6，冪等遷移）
    cols = {r[1] for r in cursor.execute("PRAGMA table_info(invoices)").fetchall()}
    if "tendered" not in cols:
        cursor.execute("ALTER TABLE invoices ADD COLUMN tendered INTEGER NOT NULL DEFAULT 0")
    if "change" not in cols:
        cursor.execute('ALTER TABLE invoices ADD COLUMN "change" INTEGER NOT NULL DEFAULT 0')

    conn.commit()
    conn.close()
    return ["sales", "invoices", "invoice_seq", "shop_config"]

# ==================== 發票與字軌管理 ====================

def get_invoice_seq():
    """取得目前發票字軌設定。"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM invoice_seq WHERE id = 1").fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()

def set_invoice_seq(prefix: str, current_no: int, start_no: int, end_no: int):
    """手動修改/設定當期發票字軌。允許 current_no = end_no+1 表示用罄狀態。"""
    if len(prefix) != 2 or not prefix.isalpha():
        raise ValueError("發票前綴必須是 2 碼英文字母")
    if current_no < start_no or current_no > end_no + 1:
        raise ValueError("當前號碼必須在起始與終止號碼之間")
    
    conn = get_db()
    try:
        conn.execute("""
        INSERT INTO invoice_seq (id, prefix, current_no, start_no, end_no, updated_at)
        VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            prefix = excluded.prefix,
            current_no = excluded.current_no,
            start_no = excluded.start_no,
            end_no = excluded.end_no,
            updated_at = CURRENT_TIMESTAMP
        """, (prefix.upper(), current_no, start_no, end_no))
        conn.commit()
    finally:
        conn.close()

def get_next_invoice_number():
    """預覽下一張發票號碼、剩餘張數、是否用罄。"""
    seq = get_invoice_seq()
    if not seq:
        raise RuntimeError("發票字軌尚未設定")
    
    prefix = seq["prefix"]
    curr = seq["current_no"]
    end = seq["end_no"]
    
    remaining = end - curr + 1
    
    if remaining <= 0:
        return {
            "invoice_no": None,
            "remaining": 0,
            "warning": True,
            "exhausted": True
        }
    
    formatted_no = f"{prefix}{curr:08d}"
    warning = remaining <= 20
    
    return {
        "invoice_no": formatted_no,
        "remaining": remaining,
        "warning": warning,
        "exhausted": False
    }

# ==================== 結帳與交易事務 ====================

def checkout_transaction(items: list, custom_invoice_no: str = None, tendered: int = None) -> str:
    """
    結帳交易（原子操作）：
    1. 驗證並獲取發票號碼
    2. 驗證收現 >= 合計（未給收現則視同合計，不找零）
    3. 寫入 invoices 主表（含收現/找零）
    4. 寫入 sales 明細表
    5. 自動遞增發票字軌號碼
    回傳發票號碼；找零請用 get_invoice_tender() 查詢。
    """
    if not items:
        raise ValueError("明細清單為空，無法結帳")
    
    conn = get_db()
    try:
        conn.execute("BEGIN TRANSACTION")
        
        # 1. 取得發票號碼
        if custom_invoice_no:
            # 手動輸入發票號碼驗證
            import re
            if not re.match(r"^[A-Z]{2}[0-9]{8}$", custom_invoice_no):
                raise ValueError("發票號碼格式必須為 2 碼大寫英文 + 8 碼數字")
            invoice_no = custom_invoice_no
            # 檢查是否重複
            dup = conn.execute("SELECT 1 FROM invoices WHERE invoice_no = ?", (invoice_no,)).fetchone()
            if dup:
                raise ValueError(f"發票號碼 {invoice_no} 已經使用過，請重新輸入")
            # 手動號若落在目前字軌同一前綴，必須在有效範圍內（超 range 要先換新本）
            seq_now = conn.execute("SELECT * FROM invoice_seq WHERE id = 1").fetchone()
            if seq_now and invoice_no[:2] == seq_now["prefix"]:
                num = int(invoice_no[2:])
                if num < seq_now["start_no"] or num > seq_now["end_no"]:
                    raise ValueError(
                        f"發票號碼超出有效範圍 "
                        f"({seq_now['prefix']}{seq_now['start_no']:08d}–"
                        f"{seq_now['prefix']}{seq_now['end_no']:08d})，請先換新發票本")
                # 手動號用到哪，字軌就跟到下一號（自動跳號不斷頭）
                if num >= seq_now["current_no"]:
                    conn.execute("""
                    UPDATE invoice_seq
                    SET current_no = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """, (num + 1,))
        else:
            # 自動取得
            seq = conn.execute("SELECT * FROM invoice_seq WHERE id = 1").fetchone()
            if not seq:
                raise ValueError("未設定發票字軌")
            if seq["current_no"] > seq["end_no"]:
                raise ValueError("發票號碼已用罄！請先設定新發票字軌。")
            invoice_no = f"{seq['prefix']}{seq['current_no']:08d}"
            
            # 自動遞增 current_no + 1
            conn.execute("""
            UPDATE invoice_seq
            SET current_no = current_no + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """)

        total_amount = sum(item["amount"] for item in items)

        # 收現驗證（預設＝合計）
        if tendered is None:
            tendered = total_amount
        try:
            tendered = int(tendered)
        except (ValueError, TypeError):
            raise ValueError("收現必須是整數")
        if tendered < total_amount:
            raise ValueError(f"收現 ${tendered} 不足合計 ${total_amount}")
        change = tendered - total_amount

        # 2. 寫入 invoices
        conn.execute("""
        INSERT INTO invoices (invoice_no, total_amount, created_at, is_void, tendered, "change")
        VALUES (?, ?, datetime('now', 'localtime'), 0, ?, ?)
        """, (invoice_no, total_amount, tendered, change))
        
        # 3. 寫入 sales（含品名/數量/單價，舊格式只有 amount 時自動補）
        for item in items:
            name = (item.get("item_name") or "文具")
            qty = int(item.get("qty", 1))
            price = int(item.get("unit_price", item["amount"]))
            conn.execute("""
            INSERT INTO sales (amount, created_at, invoice_no, void_flag, item_name, qty, unit_price)
            VALUES (?, datetime('now', 'localtime'), ?, 0, ?, ?, ?)
            """, (item["amount"], invoice_no, name, qty, price))
            
        conn.commit()
        return invoice_no
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_invoice(invoice_no: str):
    """查詢單張發票（含收現/找零）。"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM invoices WHERE invoice_no = ?", (invoice_no,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_invoice_lines(invoice_no: str):
    """查詢單張發票的銷售明細行。"""
    conn = get_db()
    try:
        rows = conn.execute("""
        SELECT item_name, qty, unit_price, amount FROM sales
        WHERE invoice_no = ? ORDER BY id ASC
        """, (invoice_no,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def void_invoice(invoice_no: str):
    """作廢指定發票及明細。"""
    conn = get_db()
    try:
        conn.execute("BEGIN TRANSACTION")
        
        # 檢查發票是否存在
        row = conn.execute("SELECT * FROM invoices WHERE invoice_no = ?", (invoice_no,)).fetchone()
        if not row:
            raise KeyError(f"找不到發票號碼 {invoice_no}")
        if row["is_void"] == 1:
            raise ValueError(f"發票 {invoice_no} 已經是作廢狀態")
            
        conn.execute("UPDATE invoices SET is_void = 1 WHERE invoice_no = ?", (invoice_no,))
        conn.execute("UPDATE sales SET void_flag = 1 WHERE invoice_no = ?", (invoice_no,))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# ==================== 報表統計 ====================

def get_daily_report(date_str: str = None):
    """
    獲取日結報表：
    - 日期：預設今天 (YYYY-MM-DD)
    - 總銷售金額 (不含作廢)
    - 總交易筆數 (不含作廢)
    - 作廢統計 (張數、金額)
    - 開立發票起訖號碼
    - 開立明細列表
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    conn = get_db()
    try:
        # 當日所有開立發票
        rows = conn.execute("""
        SELECT * FROM invoices
        WHERE date(created_at) = ?
        ORDER BY invoice_no ASC
        """, (date_str,)).fetchall()
        
        invoices_list = [dict(r) for r in rows]
        
        # 計算統計數據
        total_amount = sum(inv["total_amount"] for inv in invoices_list if inv["is_void"] == 0)
        total_count = sum(1 for inv in invoices_list if inv["is_void"] == 0)
        
        void_count = sum(1 for inv in invoices_list if inv["is_void"] == 1)
        void_amount = sum(inv["total_amount"] for inv in invoices_list if inv["is_void"] == 1)
        
        # 起訖發票號碼
        active_invoices = [inv["invoice_no"] for inv in invoices_list]
        start_invoice = active_invoices[0] if active_invoices else "無"
        end_invoice = active_invoices[-1] if active_invoices else "無"
        
        return {
            "date": date_str,
            "total_amount": total_amount,
            "total_count": total_count,
            "void_count": void_count,
            "void_amount": void_amount,
            "start_invoice": start_invoice,
            "end_invoice": end_invoice,
            "invoices": invoices_list
        }
    finally:
        conn.close()

# ==================== 商店設定 ====================

def get_shop_config():
    """取得商店設定（統編/名稱/字軌前綴）。"""
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM shop_config").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()

def set_shop_config(tax_id: str, shop_name: str, invoice_prefix: str,
                    address: str = "", phone: str = ""):
    """更新商店設定（地址、電話不可空白）。"""
    tax_id = (tax_id or "").strip()
    shop_name = (shop_name or "").strip()
    invoice_prefix = (invoice_prefix or "").strip().upper()
    address = (address or "").strip()
    phone = (phone or "").strip()
    if not tax_id.isdigit() or len(tax_id) != 8:
        raise ValueError("統一編號必須是 8 碼數字")
    if not shop_name:
        raise ValueError("營業人名稱不可空白")
    if len(invoice_prefix) != 2 or not invoice_prefix.isalpha():
        raise ValueError("發票字軌必須是 2 碼英文")
    if not address:
        raise ValueError("地址不可空白")
    if not phone:
        raise ValueError("電話不可空白")
    conn = get_db()
    try:
        for k, v in (("tax_id", tax_id), ("shop_name", shop_name),
                     ("invoice_prefix", invoice_prefix),
                     ("address", address), ("phone", phone)):
            conn.execute("INSERT OR REPLACE INTO shop_config (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
    finally:
        conn.close()
    return get_shop_config()

# ==================== 401 月報 ====================

def calc_tax_split(total_amount: int):
    """應稅拆分：銷售額 = round(總額/1.05)，稅額 = 總額 - 銷售額。"""
    sales = round(total_amount / 1.05)
    return sales, total_amount - sales

def get_monthly_report(year_month: str):
    """
    401 格式月報（year_month: YYYY-MM）：
    - days: 每日 {day, count, start_no, end_no, total}（無開立則 count=0）
    - void_list: 作廢發票號碼清單
    - total_amount / sales_amount / tax_amount / period（申報期別 1-6）
    """
    import calendar
    import re
    if not re.match(r"^\d{4}-\d{2}$", year_month or ""):
        raise ValueError("月份格式錯誤 YYYY-MM")
    year, month = int(year_month[:4]), int(year_month[5:7])
    if month < 1 or month > 12:
        raise ValueError("月份格式錯誤 YYYY-MM")
    days_in_month = calendar.monthrange(year, month)[1]

    conn = get_db()
    try:
        rows = conn.execute("""
        SELECT * FROM invoices
        WHERE strftime('%Y-%m', created_at) = ?
        ORDER BY invoice_no ASC
        """, (year_month,)).fetchall()
        invoices_list = [dict(r) for r in rows]

        by_day = {}
        for inv in invoices_list:
            d = int(inv["created_at"][8:10])
            by_day.setdefault(d, []).append(inv)

        days = []
        for d in range(1, days_in_month + 1):
            invs = by_day.get(d, [])
            active = [i for i in invs if i["is_void"] == 0]
            days.append({
                "day": d,
                "count": len(active),
                "start_no": active[0]["invoice_no"] if active else "",
                "end_no": active[-1]["invoice_no"] if active else "",
                "total": sum(i["total_amount"] for i in active),
            })

        total_amount = sum(i["total_amount"] for i in invoices_list if i["is_void"] == 0)
        sales_amount, tax_amount = calc_tax_split(total_amount)
        void_list = [i["invoice_no"] for i in invoices_list if i["is_void"] == 1]
        # 字軌唯一來源：實際使用的 invoice_seq（報表跟收銀同一字軌，不再各說各話）
        seq = conn.execute("SELECT prefix FROM invoice_seq WHERE id = 1").fetchone()
        shop = get_shop_config()
        if seq:
            shop["invoice_prefix"] = seq["prefix"]
        return {
            "year_month": year_month,
            "period": (month + 1) // 2,
            "days": days,
            "invoice_count": sum(dd["count"] for dd in days),
            "total_amount": total_amount,
            "sales_amount": sales_amount,
            "tax_amount": tax_amount,
            "void_count": len(void_list),
            "void_amount": sum(i["total_amount"] for i in invoices_list if i["is_void"] == 1),
            "void_list": void_list,
            "shop": shop,
        }
    finally:
        conn.close()

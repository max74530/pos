# tests/test_database.py — 測試 SQLite 事務、發票與日結報表
import os
import pytest
import database as db
from database import (
    init_db, get_db, get_invoice_seq, set_invoice_seq,
    get_next_invoice_number, checkout_transaction, void_invoice, get_daily_report,
    get_shop_config, set_shop_config, calc_tax_split, get_monthly_report,
    get_invoice, get_invoice_lines,
)

@pytest.fixture(autouse=True)
def setup_test_db():
    """每個測試案例前重置測試 DB（路徑取動態 DB_PATH，配合 conftest 隔離）。"""
    # 刪除既有 DB 檔
    if os.path.exists(db.DB_PATH):
        try:
            os.remove(db.DB_PATH)
        except OSError:
            pass
    init_db()

def test_invoice_seq_management():
    # 預設值應該已建立
    seq = get_invoice_seq()
    assert seq is not None
    assert seq["prefix"] == "AB"
    assert seq["current_no"] == 12345601

    # 手動設定字軌
    set_invoice_seq("XY", 500, 100, 1000)
    seq = get_invoice_seq()
    assert seq["prefix"] == "XY"
    assert seq["current_no"] == 500

    # 字軌長度或格式不對
    with pytest.raises(ValueError):
        set_invoice_seq("XYZ", 500, 100, 1000)
    with pytest.raises(ValueError):
        set_invoice_seq("12", 500, 100, 1000)

def test_get_next_invoice_number():
    set_invoice_seq("AA", 100, 100, 120)
    info = get_next_invoice_number()
    assert info["invoice_no"] == "AA00000100"
    assert info["remaining"] == 21
    assert info["warning"] is False
    assert info["exhausted"] is False

    # 接近用罄（剩餘 20 張）
    set_invoice_seq("AA", 101, 100, 120)
    info = get_next_invoice_number()
    assert info["remaining"] == 20
    assert info["warning"] is True

    # 用罄
    set_invoice_seq("AA", 121, 100, 120)
    info = get_next_invoice_number()
    assert info["remaining"] == 0
    assert info["exhausted"] is True

def test_checkout_and_void():
    set_invoice_seq("BB", 1000, 1000, 2000)
    items = [{"amount": 100}, {"amount": 250}]
    
    # 自動分配發票號碼結帳
    inv_no = checkout_transaction(items)
    assert inv_no == "BB00001000"
    
    # 檢查字軌是否遞增
    seq = get_invoice_seq()
    assert seq["current_no"] == 1001

    # 查詢日結報表
    report = get_daily_report()
    assert report["total_amount"] == 350
    assert report["total_count"] == 1
    assert len(report["invoices"]) == 1
    assert report["invoices"][0]["invoice_no"] == "BB00001000"

    # 作廢發票
    void_invoice("BB00001000")
    report = get_daily_report()
    assert report["total_amount"] == 0
    assert report["total_count"] == 0
    assert report["void_count"] == 1
    assert report["void_amount"] == 350

def test_custom_invoice_and_duplicate():
    items = [{"amount": 150}]
    # 手動指定發票號碼
    inv_no = checkout_transaction(items, "CC99999999")
    assert inv_no == "CC99999999"

    # 格式錯誤
    with pytest.raises(ValueError):
        checkout_transaction(items, "invalid-inv")

    # 重複號碼
    with pytest.raises(ValueError):
        checkout_transaction(items, "CC99999999")

def test_custom_invoice_out_of_range():
    set_invoice_seq("DD", 10, 10, 20)
    with pytest.raises(ValueError, match="超出有效範圍"):
        checkout_transaction([{"amount": 50}], "DD00000021")
    # 範圍內可開
    assert checkout_transaction([{"amount": 50}], "DD00000015") == "DD00000015"

def test_auto_jump_after_custom_checkout():
    # 用顯示號碼結帳（手動分支）也要自動跳下一號
    set_invoice_seq("EE", 30, 30, 40)
    assert checkout_transaction([{"amount": 50}], "EE00000030") == "EE00000030"
    assert get_invoice_seq()["current_no"] == 31
    assert get_next_invoice_number()["invoice_no"] == "EE00000031"
    # 再用下一號結帳，不可撞號
    assert checkout_transaction([{"amount": 60}], "EE00000031") == "EE00000031"
    assert get_invoice_seq()["current_no"] == 32

def test_shop_config():
    # 無預設值：新庫是空的
    assert get_shop_config() == {}

    cfg = set_shop_config("12345678", "測試商店", "xy", "台北市 test 路 1 號", "02-12345678")
    assert cfg["tax_id"] == "12345678"
    assert cfg["invoice_prefix"] == "XY"
    assert cfg["address"] == "台北市 test 路 1 號"
    assert cfg["phone"] == "02-12345678"

    with pytest.raises(ValueError):
        set_shop_config("123", "測試商店", "XY", "addr", "phone")
    with pytest.raises(ValueError, match="地址"):
        set_shop_config("12345678", "測試商店", "XY", "", "phone")
    with pytest.raises(ValueError, match="電話"):
        set_shop_config("12345678", "測試商店", "XY", "addr", "")

def test_checkout_tendered_change():
    set_invoice_seq("FF", 1, 1, 100)
    no = checkout_transaction(
        [{"amount": 300, "item_name": "文具", "qty": 3, "unit_price": 100}],
        tendered=500)
    inv = get_invoice(no)
    assert inv["total_amount"] == 300
    assert inv["tendered"] == 500
    assert inv["change"] == 200
    # 預設收現＝合計
    no2 = checkout_transaction([{"amount": 150}])
    inv2 = get_invoice(no2)
    assert inv2["tendered"] == 150
    assert inv2["change"] == 0
    # 收現不足擋下
    with pytest.raises(ValueError, match="不足"):
        checkout_transaction([{"amount": 150}], tendered=100)
    # 明細行查詢
    lines = get_invoice_lines(no)
    assert lines == [{"item_name": "文具", "qty": 3, "unit_price": 100, "amount": 300}]

def test_tax_split_matches_401():
    # 401 本月實例：總額 1372 → 銷售額 1307、稅額 65
    sales, tax = calc_tax_split(1372)
    assert sales == 1307
    assert tax == 65

def test_monthly_report():
    import datetime
    ym = datetime.datetime.now().strftime("%Y-%m")
    set_invoice_seq("MM", 1, 1, 100)
    checkout_transaction([{"amount": 100, "item_name": "文具", "qty": 2, "unit_price": 50}])
    checkout_transaction([{"amount": 200, "item_name": "文具", "qty": 1, "unit_price": 200}])

    r = get_monthly_report(ym)
    assert r["period"] == (datetime.datetime.now().month + 1) // 2
    assert r["invoice_count"] == 2
    assert r["total_amount"] == 300
    sales, tax = calc_tax_split(300)
    assert r["sales_amount"] == sales
    assert r["tax_amount"] == tax
    today = datetime.datetime.now().day
    day_row = [d for d in r["days"] if d["day"] == today][0]
    assert day_row["count"] == 2
    assert day_row["total"] == 300
    assert day_row["start_no"] < day_row["end_no"]

    with pytest.raises(ValueError):
        get_monthly_report("2026-13")

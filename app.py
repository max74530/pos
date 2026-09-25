# app.py — WEBPOS Flask 伺服器入口
import csv
import io
import re
from flask import Flask, jsonify, render_template, request, Response
from version import APP_VERSION
from pos_core import POSCart
import database as db

app = Flask(__name__)

# 初始化 DB
db.init_db()

# 單機單收銀員：記憶體購物車
cart = POSCart()

INVOICE_RE = re.compile(r"^[A-Z]{2}[0-9]{8}$")

@app.route("/")
def index():
    shop = db.get_shop_config()
    return render_template("index.html", version=APP_VERSION,
                           shop_name=shop.get("shop_name", ""))

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "webpos",
        "version": APP_VERSION
    })

# ---------- 購物車 API ----------
@app.route("/api/cart", methods=["GET"])
def api_cart_list():
    return jsonify({
        "items": cart.get_display_list(20),
        "total": cart.get_total(),
        "count": len(cart.get_items()),
    })

@app.route("/api/cart/add", methods=["POST"])
def api_cart_add():
    data = request.get_json(force=True, silent=True) or {}
    try:
        if "unit_price" in data or "qty" in data or "item_name" in data:
            item = cart.add_item(
                data.get("item_name") or "文具",
                data.get("qty", 1),
                data.get("unit_price", 0),
            )
        elif "amount" in data:
            item = cart.add_item(int(data.get("amount", 0)))
        else:
            return jsonify({"error": "請輸入品名/數量/單價"}), 400
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"item": item, "total": cart.get_total()}), 201

@app.route("/api/cart/<int:item_id>", methods=["PATCH"])
def api_cart_edit(item_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        if "unit_price" in data or "qty" in data or "item_name" in data:
            item = cart.edit_item(item_id,
                                  item_name=data.get("item_name"),
                                  qty=data.get("qty"),
                                  unit_price=data.get("unit_price"))
        elif "amount" in data:
            item = cart.edit_item(item_id, new_amount=int(data.get("amount", 0)))
        else:
            return jsonify({"error": "請輸入品名/數量/單價"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"item": item, "total": cart.get_total()})

@app.route("/api/cart/<int:item_id>", methods=["DELETE"])
def api_cart_delete(item_id):
    try:
        cart.delete_item(item_id)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"total": cart.get_total()})

@app.route("/api/cart/clear", methods=["DELETE"])
def api_cart_clear():
    cart.clear()
    return jsonify({"total": 0})

# ---------- 發票字軌 API ----------
@app.route("/api/invoice/next", methods=["GET"])
def api_invoice_next():
    try:
        return jsonify(db.get_next_invoice_number())
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/invoice/seq", methods=["GET"])
def api_invoice_seq_get():
    seq = db.get_invoice_seq()
    if not seq:
        return jsonify({"error": "發票字軌尚未設定"}), 404
    return jsonify(seq)

@app.route("/api/invoice/seq", methods=["POST"])
def api_invoice_seq_set():
    data = request.get_json(force=True, silent=True) or {}
    try:
        db.set_invoice_seq(
            str(data.get("prefix", "")).upper(),
            int(data.get("current_no", 0)),
            int(data.get("start_no", 0)),
            int(data.get("end_no", 0)),
        )
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(db.get_invoice_seq())

# ---------- 結帳 / 作廢 ----------
@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    data = request.get_json(force=True, silent=True) or {}
    invoice_no = data.get("invoice_no") or None
    if invoice_no:
        invoice_no = str(invoice_no).strip().upper()
        if not INVOICE_RE.match(invoice_no):
            return jsonify({"error": "發票格式錯誤：前2碼英文大寫＋後8碼數字"}), 400
    items = cart.get_items()
    if not items:
        return jsonify({"error": "明細清單為空，無法結帳"}), 400
    tendered = data.get("tendered", None)
    try:
        no = db.checkout_transaction(
            [{"amount": it["amount"], "item_name": it.get("item_name", "文具"),
              "qty": it.get("qty", 1),
              "unit_price": it.get("unit_price", it["amount"])} for it in items],
            custom_invoice_no=invoice_no,
            tendered=tendered,
        )
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400
    cart.clear()
    inv = db.get_invoice(no) or {}
    return jsonify({"invoice_no": no, "total": inv.get("total_amount", 0),
                    "tendered": inv.get("tendered", 0),
                    "change": inv.get("change", 0)}), 201

@app.route("/api/invoice/<invoice_no>/void", methods=["POST"])
def api_invoice_void(invoice_no):
    try:
        db.void_invoice(invoice_no.strip().upper())
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})

@app.route("/api/invoice/<invoice_no>", methods=["GET"])
def api_invoice_detail(invoice_no):
    no = invoice_no.strip().upper()
    inv = db.get_invoice(no)
    if not inv:
        return jsonify({"error": "找不到發票 " + no}), 404
    return jsonify({"invoice": inv, "lines": db.get_invoice_lines(no),
                    "shop": db.get_shop_config()})

# ---------- 商店設定 ----------
@app.route("/api/shop/config", methods=["GET"])
def api_shop_get():
    return jsonify(db.get_shop_config())

@app.route("/api/shop/config", methods=["POST"])
def api_shop_set():
    data = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(db.set_shop_config(
            data.get("tax_id", ""),
            data.get("shop_name", ""),
            data.get("invoice_prefix", ""),
            data.get("address", ""),
            data.get("phone", ""),
        ))
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

# ---------- 報表 ----------
@app.route("/api/report/daily", methods=["GET"])
def api_report_daily():
    date_str = request.args.get("date") or None
    if date_str and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "日期格式錯誤 YYYY-MM-DD"}), 400
    return jsonify(db.get_daily_report(date_str))

@app.route("/api/report/monthly", methods=["GET"])
def api_report_monthly():
    ym = request.args.get("month") or None
    if not ym:
        from datetime import datetime as _dt
        ym = _dt.now().strftime("%Y-%m")
    try:
        return jsonify(db.get_monthly_report(ym))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/report/export_csv", methods=["GET"])
def api_report_csv():
    date_str = request.args.get("date") or None
    report = db.get_daily_report(date_str)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", report["date"]])
    w.writerow(["total_amount", report["total_amount"]])
    w.writerow(["total_count", report["total_count"]])
    w.writerow(["void_count", report["void_count"]])
    w.writerow(["void_amount", report["void_amount"]])
    w.writerow(["start_invoice", report["start_invoice"]])
    w.writerow(["end_invoice", report["end_invoice"]])
    w.writerow([])
    w.writerow(["invoice_no", "total_amount", "created_at", "is_void"])
    for inv in report["invoices"]:
        w.writerow([inv["invoice_no"], inv["total_amount"], inv["created_at"], inv["is_void"]])
    out = "\ufeff" + buf.getvalue()
    return Response(
        out,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=webpos-{report['date']}.csv"},
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

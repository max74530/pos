# pos_core.py — WEBPOS 交易明細與驗證邏輯（v0.5：品名＋數量＋單價）
DEFAULT_ITEM_NAME = "文具"
MAX_QTY = 99
MAX_UNIT_PRICE = 5000

def _to_int(v, label):
    if isinstance(v, bool):
        raise ValueError(f"{label}必須是整數")
    if not isinstance(v, int):
        try:
            v = int(v)
        except (ValueError, TypeError):
            raise ValueError(f"{label}必須是整數")
    return v

def validate_line(item_name, qty, unit_price):
    """驗證一筆明細，回傳 (name, qty, price, amount)。"""
    name = (item_name or "").strip() if isinstance(item_name, str) else DEFAULT_ITEM_NAME
    if not name:
        name = DEFAULT_ITEM_NAME
    qty = _to_int(qty, "數量")
    if qty < 1 or qty > MAX_QTY:
        raise ValueError(f"數量超出範圍 (必須在 1 至 {MAX_QTY} 之間)")
    unit_price = _to_int(unit_price, "單價")
    if unit_price < 1 or unit_price > MAX_UNIT_PRICE:
        raise ValueError(f"單價超出範圍 (必須在 1 至 {MAX_UNIT_PRICE} 元之間)")
    return name, qty, unit_price, qty * unit_price

class POSCart:
    def __init__(self):
        # 項目格式 {"id": int, "item_name": str, "qty": int, "unit_price": int, "amount": int}
        self.items = []
        self._next_id = 1

    def add_item(self, item_name=DEFAULT_ITEM_NAME, qty=1, unit_price=0, amount=None) -> dict:
        """加入一筆明細。舊格式 add_item(amount) 仍相容：視為 文具×1@amount。"""
        if amount is not None and (unit_price in (0, None)):
            # 舊呼叫 add_item(100)：第一個位置參數其實是金額
            if isinstance(item_name, (int, float)) and qty == 1:
                amount = int(item_name)
                name, q, p, total = DEFAULT_ITEM_NAME, 1, amount, amount
                if total < 1 or total > MAX_UNIT_PRICE:
                    raise ValueError(f"單價超出範圍 (必須在 1 至 {MAX_UNIT_PRICE} 元之間)")
            else:
                raise ValueError("單價必須是整數")
        elif isinstance(item_name, (int, float)) and qty == 1 and not unit_price:
            # add_item(100) 簡寫
            total = int(item_name)
            if total < 1 or total > MAX_UNIT_PRICE:
                raise ValueError(f"單價超出範圍 (必須在 1 至 {MAX_UNIT_PRICE} 元之間)")
            name, q, p = DEFAULT_ITEM_NAME, 1, total
        else:
            if unit_price is None:
                raise ValueError("單價必須是整數")
            name, q, p, total = validate_line(item_name, qty, unit_price)
        item = {"id": self._next_id, "item_name": name, "qty": q,
                "unit_price": p, "amount": total}
        self.items.append(item)
        self._next_id += 1
        return item

    def get_items(self) -> list:
        """回傳當前所有項目。"""
        return self.items

    def edit_item(self, item_id: int, item_name=None, qty=None, unit_price=None, new_amount=None) -> dict:
        """修改指定 ID 項目。支援新格式 (name/qty/price) 與舊格式 (new_amount)。"""
        for item in self.items:
            if item["id"] == item_id:
                if new_amount is not None and item_name is None and qty is None and unit_price is None:
                    total = _to_int(new_amount, "金額")
                    if total < 1 or total > MAX_UNIT_PRICE:
                        raise ValueError(f"單價超出範圍 (必須在 1 至 {MAX_UNIT_PRICE} 元之間)")
                    item.update({"item_name": DEFAULT_ITEM_NAME, "qty": 1,
                                 "unit_price": total, "amount": total})
                else:
                    name, q, p, total = validate_line(
                        item_name if item_name is not None else item["item_name"],
                        qty if qty is not None else item["qty"],
                        unit_price if unit_price is not None else item["unit_price"],
                    )
                    item.update({"item_name": name, "qty": q, "unit_price": p, "amount": total})
                return item
        raise KeyError(f"找不到項目 ID {item_id}")

    def delete_item(self, item_id: int):
        """刪除指定 ID 項目。"""
        for i, item in enumerate(self.items):
            if item["id"] == item_id:
                self.items.pop(i)
                return
        raise KeyError(f"找不到項目 ID {item_id}")

    def clear(self):
        """整單清除。"""
        self.items.clear()
        self._next_id = 1

    def get_total(self) -> int:
        """計算總計金額。"""
        return sum(item["amount"] for item in self.items)

    def _display_row(self, item):
        return {"id": item["id"], "item_name": item.get("item_name", DEFAULT_ITEM_NAME),
                "qty": item.get("qty", 1), "unit_price": item.get("unit_price", item["amount"]),
                "amount": item["amount"], "empty": False}

    def get_display_list(self, fixed_lines: int = 20) -> list:
        """
        取得固定行數的明細清單。
        若實際項目少於 fixed_lines，則用空白項填充；
        若大於 fixed_lines，回傳最後 fixed_lines 筆項目（自動捲動效果）。
        """
        count = len(self.items)
        if count <= fixed_lines:
            display_list = [self._display_row(item) for item in self.items]
            for _ in range(fixed_lines - count):
                display_list.append({"id": None, "item_name": "", "qty": "",
                                     "unit_price": "", "amount": "", "empty": True})
            return display_list
        else:
            return [self._display_row(item) for item in self.items[-fixed_lines:]]

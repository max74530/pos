# AGENTS.md — WEBPOS 獨立專案工作慣例

> 本專案已脫離 SMSGO 家族，為獨立專案。
> 不自動上傳 server、不讀任何 `.server-credentials`、不用家族埠段與 `deploy/upload.ps1`。

## 慣例

- 繁中文件；版號唯一來源 `version.py:APP_VERSION`，每次變更 +1。
- 工作區：開發中程式放 `dev/`；`data/`（SQLite 檔）、`__pycache__/`、`venv/` 不進版控。
- 破壞性操作（刪檔、改 DB 結構）先備份再動手，重要操作留驗收證據（pytest + health）。
- 驗收標準：`python -m pytest tests -q` 全過＋`GET /health` 正常＋開單→結帳→報表抽查。

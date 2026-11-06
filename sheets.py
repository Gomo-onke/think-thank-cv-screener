"""Optional Google Sheets sync via gspread + service account.
Identical in Build 1 and Build 2.

Input tab  (SHEET_CANDIDATES_TAB, default "Candidates") - header row, then one
candidate per row. Columns (case-insensitive):

    name | email | phone | position | cv_text | processed

`processed` is filled in by the screener after a row is imported, so rows are
never screened twice. Add the column header yourself, leave the cells blank.

Output tab (SHEET_RESULTS_TAB, default "Results") - one row appended per
decision, tab created automatically.
"""
from __future__ import annotations

import config

RESULT_HEADERS = ["timestamp", "name", "email", "position", "score", "status", "notes"]


def sheets_configured() -> bool:
    return bool(config.GOOGLE_CREDENTIALS_FILE and config.SHEET_ID)


def _open_spreadsheet():
    import gspread  # imported lazily so the app runs without gspread installed
    client = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
    return client.open_by_key(config.SHEET_ID)


def append_result(candidate: dict, result: dict, timestamp: str) -> dict:
    """Append one decision row to the results tab. Returns a log-style dict."""
    base = {"service": "sheets", "action": "append"}
    if not sheets_configured():
        return {**base, "success": False, "status_code": None,
                "detail": "skipped: GOOGLE_CREDENTIALS_FILE / SHEET_ID not set"}
    try:
        import gspread
        sh = _open_spreadsheet()
        try:
            ws = sh.worksheet(config.SHEET_RESULTS_TAB)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(config.SHEET_RESULTS_TAB, rows=1000, cols=len(RESULT_HEADERS))
            ws.append_row(RESULT_HEADERS)
        ws.append_row([timestamp, candidate["name"], candidate["email"], result["position"],
                       result["score"], result["status"], result["notes"]],
                      value_input_option="USER_ENTERED")
        return {**base, "success": True, "status_code": None, "detail": "row appended"}
    except Exception as exc:  # noqa: BLE001
        return {**base, "success": False, "status_code": None,
                "detail": f"{type(exc).__name__}: {exc}"}


def fetch_unprocessed() -> list[dict]:
    """Rows from the candidates tab that have no `processed` value yet.

    Each dict has name/email/phone/position/cv_text plus `_row` (sheet row
    number). Raises on configuration/auth errors so the UI can show them.
    """
    if not sheets_configured():
        raise RuntimeError("Google Sheets is not configured (set GOOGLE_CREDENTIALS_FILE and SHEET_ID).")
    ws = _open_spreadsheet().worksheet(config.SHEET_CANDIDATES_TAB)
    values = ws.get_all_values()
    if not values:
        return []
    headers = [h.strip().lower() for h in values[0]]
    missing = [h for h in ("name", "email", "position", "cv_text") if h not in headers]
    if missing:
        raise RuntimeError(f"Candidates tab is missing column(s): {', '.join(missing)}")
    rows = []
    for i, raw in enumerate(values[1:], start=2):
        row = {h: (raw[idx].strip() if idx < len(raw) else "") for idx, h in enumerate(headers)}
        if row.get("processed") or not any(row.get(k) for k in ("name", "email", "cv_text")):
            continue
        row["_row"] = i
        rows.append(row)
    return rows


def mark_processed(row_number: int, timestamp: str) -> None:
    ws = _open_spreadsheet().worksheet(config.SHEET_CANDIDATES_TAB)
    headers = [h.strip().lower() for h in ws.row_values(1)]
    if "processed" in headers:
        ws.update_cell(row_number, headers.index("processed") + 1, timestamp)

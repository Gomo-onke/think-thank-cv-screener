"""Professional Excel workbook for recruiters.

Sheets: Summary (headline numbers), Candidates (ranked), Interviews, Interns.
The file is rewritten after every change (see service.refresh_excel) and can also be
downloaded on demand from Admin > Download Excel.
"""
from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime

from openpyxl import Workbook
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config
import database as db

BLUE = "1D4ED8"
DARK = "0B1220"
LIGHT = "EAF1FF"
BAND = "F6F8FF"
FILL = {"Pass": ("DCFCE7", "166534"), "Needs Review": ("FEF3C7", "92400E"), "Reject": ("FEE2E2", "991B1B")}

THIN = Side(style="thin", color="1F2937")
HAIR = Side(style="thin", color="C7D2E5")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GRID = Border(left=HAIR, right=HAIR, top=HAIR, bottom=HAIR)
HEAD_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
BODY_FONT = Font(name="Calibri", size=11, color="111827")


def _put(ws, row: int, col: int, value, *, font=None, fill=None, align=None, border=None, fmt=None):
    """Write a cell. Text is always stored as text, so a name such as '=HYPERLINK(...)'
    can never be executed as an Excel formula."""
    cell = ws.cell(row=row, column=col)
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"
    cell.font = font or BODY_FONT
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = align or Alignment(vertical="top", wrap_text=True)
    if border:
        cell.border = border
    if fmt:
        cell.number_format = fmt
    return cell


def _dt(value: str):
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None) if value else None
    except ValueError:
        return None


def _header(ws, row: int, headers: list[str], widths: list[int]) -> None:
    for i, (h, w) in enumerate(zip(headers, widths), start=1):
        _put(ws, row, i, h, font=HEAD_FONT, fill=BLUE, border=BOX,
             align=Alignment(horizontal="center", vertical="center", wrap_text=True))
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 32


def _finish_table(ws, header_row: int, n_cols: int, n_rows: int, landscape: bool = True) -> None:
    ws.freeze_panes = ws.cell(row=header_row + 1, column=3 if n_cols > 4 else 1)
    if n_rows:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(n_cols)}{header_row + n_rows}"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.sheet_properties.tabColor = BLUE


def _title(ws, text: str, sub: str, span: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    _put(ws, 1, 1, text, font=Font(name="Calibri", bold=True, size=18, color=BLUE),
         align=Alignment(vertical="center"))
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
    _put(ws, 2, 1, sub, font=Font(name="Calibri", italic=True, size=10, color="4B5563"),
         align=Alignment(vertical="center"))


def _candidate_rows(conn) -> list[dict]:
    rows = db.latest_screenings(conn)
    rows.sort(key=lambda r: (-r["score"], r["screened_at"]))
    out = []
    for rank, r in enumerate(rows, start=1):
        c = db.get_candidate(conn, r["candidate_id"])
        latest = db.screening_history(conn, r["candidate_id"])[0]["breakdown"]
        out.append({**r, **{k: c[k] for k in ("highest_qualification", "field_of_study", "current_title",
                                              "current_employer", "years_experience", "notice_period",
                                              "available_from", "expected_salary", "work_arrangement",
                                              "linkedin_url", "referral_source", "work_authorisation")},
                    "rank": rank, "detail": latest})
    return out


def build_workbook(conn) -> Workbook:
    wb = Workbook()
    rows = _candidate_rows(conn)
    generated = datetime.now().strftime("%d %B %Y, %H:%M")

    # ------------------------------------------------------------------ Summary
    ws = wb.active
    ws.title = "Summary"
    _title(ws, f"{config.ORGANISATION_NAME} - Recruitment report",
           f"Generated {generated}. Scores are out of 100 and compare best within the same position.", 6)
    for col, w in zip("ABCDEF", (30, 14, 14, 14, 14, 16)):
        ws.column_dimensions[col].width = w

    counts = {"Pass": 0, "Needs Review": 0, "Reject": 0}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    avg = round(sum(r["score"] for r in rows) / len(rows), 1) if rows else 0
    kpis = [("Candidates screened", len(rows)), ("Pass", counts["Pass"]), ("Needs Review", counts["Needs Review"]),
            ("Reject", counts["Reject"]), ("Average score", avg)]
    _header(ws, 4, ["Headline", "Value"], [30, 14])
    for i, (label, val) in enumerate(kpis, start=5):
        fill = FILL.get(label, (BAND if i % 2 else "FFFFFF", DARK))[0]
        _put(ws, i, 1, label, fill=fill, border=GRID, font=Font(name="Calibri", bold=True, size=11))
        _put(ws, i, 2, val, fill=fill, border=GRID, align=Alignment(horizontal="center"),
             font=Font(name="Calibri", bold=True, size=11), fmt="0.0" if label == "Average score" else "0")

    r0 = 5 + len(kpis) + 1
    _put(ws, r0, 1, "Hiring pipeline", font=Font(name="Calibri", bold=True, size=13, color=BLUE),
         align=Alignment(vertical="center"))
    _header(ws, r0 + 1, ["Stage", "Candidates"], [30, 14])
    for i, (stage, n) in enumerate(db.stage_counts(conn).items(), start=r0 + 2):
        _put(ws, i, 1, stage, fill=BAND if i % 2 else "FFFFFF", border=GRID)
        _put(ws, i, 2, n, fill=BAND if i % 2 else "FFFFFF", border=GRID, align=Alignment(horizontal="center"))

    r1 = r0 + 2 + len(config.STAGES) + 1
    _put(ws, r1, 1, "By position", font=Font(name="Calibri", bold=True, size=13, color=BLUE),
         align=Alignment(vertical="center"))
    _header(ws, r1 + 1, ["Position", "Candidates", "Pass", "Needs Review", "Reject", "Average score"],
            [30, 14, 14, 14, 14, 16])
    by_pos: dict[str, list[dict]] = {}
    for r in rows:
        by_pos.setdefault(r["position"], []).append(r)
    for i, (pos, items) in enumerate(sorted(by_pos.items(), key=lambda kv: -len(kv[1])), start=r1 + 2):
        f = BAND if i % 2 else "FFFFFF"
        vals = [pos, len(items)] + [sum(1 for x in items if x["status"] == s) for s in ("Pass", "Needs Review", "Reject")] \
            + [round(sum(x["score"] for x in items) / len(items), 1)]
        for j, v in enumerate(vals, start=1):
            _put(ws, i, j, v, fill=f, border=GRID, align=Alignment(horizontal="left" if j == 1 else "center"),
                 fmt="0.0" if j == 6 else None)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = DARK
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # ------------------------------------------------------------------ Candidates
    ws = wb.create_sheet("Candidates")
    headers = ["Rank", "Candidate", "Position", "Score /100", "Auto decision", "Hiring stage", "Interview rating (1-5)",
               "Recruiter says right person?", "Email", "Phone", "Location", "Highest qualification",
               "Current role", "Years of experience (declared / detected)", "Notice period", "Expected salary",
               "Preferred department", "Required keywords found", "Missing required keywords", "Notes", "Applied"]
    widths = [7, 24, 22, 11, 15, 17, 14, 18, 30, 17, 20, 22, 30, 17, 14, 16, 22, 28, 28, 44, 17]
    _header(ws, 1, headers, widths)
    for i, r in enumerate(rows, start=2):
        band = BAND if i % 2 else "FFFFFF"
        d = r["detail"]
        rec = f"Yes {r['rec_yes']} / Maybe {r['rec_maybe']} / No {r['rec_no']}" if r["interview_count"] else ""
        role = " at ".join(x for x in (r["current_title"], r["current_employer"]) if x)
        declared = r["years_experience"] or "-"
        vals = [r["rank"], r["name"], r["position"], r["score"], r["status"], r["stage"],
                r["avg_rating"] if r["interview_count"] else None, rec, r["email"], r["phone"], r["location"],
                r["highest_qualification"], role, f"{declared} / {d['years_found']:g}", r["notice_period"],
                r["expected_salary"], r["preferred_department"],
                f"{len(d['required_found'])} of {len(d['required_found']) + len(d['required_missing'])}: "
                + ", ".join(d["required_found"]),
                ", ".join(d["required_missing"]), r["notes"], _dt(r["applied_at"])]
        for j, v in enumerate(vals, start=1):
            center = j in (1, 4, 5, 6, 7, 14)
            cell = _put(ws, i, j, v, fill=band, border=GRID,
                        align=Alignment(horizontal="center" if center else "left", vertical="top", wrap_text=True),
                        fmt={4: "0.0", 7: "0.0", 21: "yyyy-mm-dd hh:mm"}.get(j))
            if j == 5 and r["status"] in FILL:
                bg, fg = FILL[r["status"]]
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", bold=True, color=fg, size=11)
            if j in (1, 2):
                cell.font = Font(name="Calibri", bold=True, size=11, color=DARK)
    _finish_table(ws, 1, len(headers), len(rows))
    if rows:
        ws.conditional_formatting.add(
            f"D2:D{len(rows) + 1}",
            DataBarRule(start_type="num", start_value=0, end_type="num", end_value=100, color="7AA2F7"))

    # ------------------------------------------------------------------ Interviews
    ws = wb.create_sheet("Interviews")
    headers = ["Candidate", "Position", "Interviewer", "Interview date", "Skills", "Communication", "Culture fit",
               "Overall (personal ranking)", "Right person for the job?", "Discussion notes", "Recorded"]
    widths = [24, 22, 20, 15, 9, 15, 11, 16, 18, 70, 17]
    _header(ws, 1, headers, widths)
    interviews = db.list_interviews(conn)
    rec_fill = {"Yes": FILL["Pass"], "Maybe": FILL["Needs Review"], "No": FILL["Reject"]}
    for i, iv in enumerate(interviews, start=2):
        band = BAND if i % 2 else "FFFFFF"
        vals = [iv["candidate_name"], iv["position"], iv["interviewer"], iv["interview_date"], iv["skills_rating"],
                iv["communication_rating"], iv["culture_rating"], iv["overall_rating"], iv["recommendation"],
                iv["notes"], _dt(iv["created_at"])]
        for j, v in enumerate(vals, start=1):
            cell = _put(ws, i, j, v, fill=band, border=GRID,
                        align=Alignment(horizontal="center" if 5 <= j <= 9 else "left", vertical="top", wrap_text=True),
                        fmt="yyyy-mm-dd hh:mm" if j == 11 else None)
            if j == 9 and iv["recommendation"] in rec_fill:
                bg, fg = rec_fill[iv["recommendation"]]
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(name="Calibri", bold=True, color=fg, size=11)
            if j == 1:
                cell.font = Font(name="Calibri", bold=True, size=11, color=DARK)
    _finish_table(ws, 1, len(headers), len(interviews))

    # ------------------------------------------------------------------ Interns
    ws = wb.create_sheet("Interns")
    headers = ["Intern", "Email", "Department", "Supervisor", "Start date", "Updates posted", "Courses recommended"]
    widths = [24, 30, 28, 22, 14, 15, 20]
    _header(ws, 1, headers, widths)
    interns = db.list_interns(conn)
    for i, n in enumerate(interns, start=2):
        band = BAND if i % 2 else "FFFFFF"
        for j, v in enumerate([n["name"], n["email"], n["department"], n["supervisor"], n["start_date"],
                               n["update_count"], n["course_count"]], start=1):
            cell = _put(ws, i, j, v, fill=band, border=GRID,
                        align=Alignment(horizontal="center" if j >= 5 else "left", vertical="top", wrap_text=True))
            if j == 1:
                cell.font = Font(name="Calibri", bold=True, size=11, color=DARK)
    _finish_table(ws, 1, len(headers), len(interns))

    wb.properties.title = f"{config.ORGANISATION_NAME} recruitment report"
    wb.properties.creator = f"{config.ORGANISATION_NAME} recruitment portal"
    return wb


def workbook_bytes(conn) -> bytes:
    buf = io.BytesIO()
    build_workbook(conn).save(buf)
    return buf.getvalue()


def write_file(conn, path: str | None = None) -> str:
    """Write the workbook atomically (temp file + rename), so a recruiter opening the file
    never sees a half-written one."""
    path = path or config.EXCEL_PATH
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=folder)
    os.close(fd)
    try:
        build_workbook(conn).save(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path

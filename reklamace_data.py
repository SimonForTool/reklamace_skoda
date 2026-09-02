"""
Datový model a úložiště pro Reklamace — správa reklamací pro více značek
(ŠKODA, PORSCHE), každá se samostatnou číselnou řadou.

Reklamace prochází 4 nezávislými fázemi (WETSy, GETAC, ACTIA IMEA,
Ostatní dodavatel), z nichž každá se eviduje samostatně (stav, datum,
poznámka, odpovědná osoba, přílohy). Interní číslo má formát
<prefix značky>-<rok>-<pořadové číslo v daném roce>, rok se odvozuje
z data přijetí. Číselná řada se počítá zvlášť pro každou značku.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from werkzeug.utils import secure_filename

DATA_DIR = Path("data")
DATA_PATH = DATA_DIR / "reklamace.json"
UPLOAD_DIR = Path("uploads") / "reklamace"

BRANDS = {
    "skoda":   {"label": "ŠKODA",   "prefix": "SKO"},
    "porsche": {"label": "PORSCHE", "prefix": "POR"},
}
DEFAULT_BRAND = "skoda"

FAZE_DEFS = [
    {"key": "wetsy",   "label": "WETSy"},
    {"key": "getac",   "label": "GETAC"},
    {"key": "actia",   "label": "ACTIA IMEA"},
    {"key": "ostatni", "label": "Ostatní dodavatel"},
]
FAZE_KEYS = [f["key"] for f in FAZE_DEFS]
FAZE_LABEL_BY_KEY = {f["key"]: f["label"] for f in FAZE_DEFS}

STAVY = ["nezahájeno", "probíhá", "hotovo"]

# Předdefinované kroky procesu — podle reálné šablony "VAT Výkaz hodin"
# (předávací protokol pro fakturaci). WETSy má 7 kroků, GETAC a ACTIA IMEA
# mají svých 9 (zpracování reklamovaného zařízení u konkrétního dodavatele).
# Ostatní dodavatel přebírá stejnou strukturu jako GETAC/ACTIA (obecně).
# Minuty u WETSy jsou podle zadání; u GETAC/ACTIA/Ostatní jde o výchozí
# odhad podle povahy kroku — kdykoliv editovatelné přímo v appce.
KROKY_DEFS_BY_FAZE = {
    "wetsy": [
        {"nazev": "Telefonický příjem reklamace",           "minuty": 15},
        {"nazev": "Odchozí informační e-mail",               "minuty": 15},
        {"nazev": "Příchozí e-mail, založení složky",        "minuty": 30},
        {"nazev": "Založení ticket WETSy",                   "minuty": 60},
        {"nazev": "Komunikace VAT & ŠPC (č. fa z VW)",       "minuty": 30},
        {"nazev": "Komunikace se zák. (e-mail, tel.)",       "minuty": 30},
        {"nazev": "Správa ticketu WETSY",                    "minuty": 30},
    ],
    "getac": [
        {"nazev": "Založení ticketu GETAC",                  "minuty": 60},
        {"nazev": "Komunikace s GETAC",                      "minuty": 30},
        {"nazev": "Komunikace se zákazníkem",                "minuty": 30},
        {"nazev": "Odeslání zařízení (servis, výměna)",      "minuty": 30},
        {"nazev": "Správa ticketu GETAC",                    "minuty": 30},
        {"nazev": "Příjem reklamovaného zař.",                "minuty": 15},
        {"nazev": "Zpětná vazba u zákazníka",                "minuty": 15},
        {"nazev": "Uzavření ticketu",                        "minuty": 15},
        {"nazev": "Dokument potvrzení",                      "minuty": 15},
    ],
    "actia": [
        {"nazev": "Založení ticketu ACTIA",                  "minuty": 60},
        {"nazev": "Komunikace s ACTIA",                      "minuty": 30},
        {"nazev": "Komunikace se zákazníkem",                "minuty": 30},
        {"nazev": "Odeslání zařízení (servis, výměna)",      "minuty": 30},
        {"nazev": "Správa ticketu ACTIA",                    "minuty": 30},
        {"nazev": "Příjem reklamovaného zař.",                "minuty": 15},
        {"nazev": "Zpětná vazba u zákazníka",                "minuty": 15},
        {"nazev": "Uzavření ticketu",                        "minuty": 15},
        {"nazev": "Dokument potvrzení",                      "minuty": 15},
    ],
    "ostatni": [
        {"nazev": "Založení ticketu",                        "minuty": 60},
        {"nazev": "Komunikace s dodavatelem",                "minuty": 30},
        {"nazev": "Komunikace se zákazníkem",                "minuty": 30},
        {"nazev": "Odeslání zařízení (servis, výměna)",      "minuty": 30},
        {"nazev": "Správa ticketu",                          "minuty": 30},
        {"nazev": "Příjem reklamovaného zař.",                "minuty": 15},
        {"nazev": "Zpětná vazba u zákazníka",                "minuty": 15},
        {"nazev": "Uzavření ticketu",                        "minuty": 15},
        {"nazev": "Dokument potvrzení",                      "minuty": 15},
    ],
}
EXTRA_KROK_MINUTY_DEFAULT = 15

STAV_LABELS_HISTORIE = {"nová": "Otevřeno", "probíhá": "Probíhá", "vyřízeno": "Uzavřeno"}

# Export do Excelu (předávací protokol pro fakturaci) — jen WETSy/GETAC/ACTIA
# mají v reálné šabloně vlastní blok sloupců; Ostatní dodavatel se promítá
# jen do celkového součtu (TOTAL), nemá dedikovaný blok.
EXPORT_BLOKY = [
    ("wetsy", "WETSy", "E"),
    ("getac", "GETAC", "L"),
    ("actia", "ACTIA IME", "U"),
]


def _empty_kroky(faze_key: str) -> list:
    defs = KROKY_DEFS_BY_FAZE.get(faze_key, [])
    kroky = [{"nazev": d["nazev"], "minuty": d["minuty"], "editable_nazev": False} for d in defs]
    kroky.append({"nazev": "", "minuty": EXTRA_KROK_MINUTY_DEFAULT, "editable_nazev": True})
    return kroky


def _empty_faze(key: str) -> dict:
    f = {
        "stav": "nezahájeno",
        "datum": None,
        "poznamka": "",
        "odpovedna_osoba": "",
        "prilohy": [],
        "kroky": _empty_kroky(key),
    }
    if key == "ostatni":
        f["dodavatel"] = ""
    return f


def faze_total_minutes(faze: dict) -> float:
    return sum((k.get("minuty") or 0) for k in faze.get("kroky", []))


def reklamace_total_minutes(item: dict) -> float:
    return sum(faze_total_minutes(item["faze"][k]) for k in FAZE_KEYS)


def minutes_to_hours(minutes: float) -> float:
    return round(minutes / 60, 1)


def business_days_between(start: date, end: date) -> int:
    """Počet pracovních dnů (po-pá) mezi start (včetně) a end (bez), min. 0."""
    if not start or not end or end <= start:
        return 0
    days = 0
    d = start
    while d < end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def _sync_uzavreno(item: dict):
    if overall_status(item) == "vyřízeno":
        if not item.get("uzavreno"):
            item["uzavreno"] = date.today().isoformat()
    else:
        item["uzavreno"] = None


def aktualni_faze_label(item: dict) -> str:
    probihajici = [FAZE_LABEL_BY_KEY[k] for k in FAZE_KEYS if item["faze"][k]["stav"] == "probíhá"]
    if probihajici:
        return ", ".join(probihajici)
    if overall_status(item) == "vyřízeno":
        return "—"
    return "Nezahájeno"


def _empty_store() -> dict:
    return {"counters": {}, "items": {}}


def load_all() -> dict:
    if not DATA_PATH.exists():
        return _empty_store()
    return json.loads(DATA_PATH.read_text())


def save_all(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def list_all(brand: str | None = None) -> list:
    data = load_all()
    items = list(data.get("items", {}).values())
    if brand:
        items = [i for i in items if i.get("znacka", DEFAULT_BRAND) == brand]
    items.sort(key=lambda i: i["vytvoreno"], reverse=True)
    for item in items:
        item["celkovy_stav"] = overall_status(item)
        item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return items


def overall_status(item: dict) -> str:
    stavy = [item["faze"][k]["stav"] for k in FAZE_KEYS]
    if all(s == "hotovo" for s in stavy):
        return "vyřízeno"
    if any(s != "nezahájeno" for s in stavy):
        return "probíhá"
    return "nová"


def get_reklamace(cislo: str) -> dict | None:
    data = load_all()
    item = data.get("items", {}).get(cislo)
    if item:
        item["celkovy_stav"] = overall_status(item)
        item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return item


def new_reklamace(brand: str, servisni_partner: str, kontaktni_osoba: str, datum_prijeti: str) -> dict:
    if brand not in BRANDS:
        raise ValueError(f"Neznámá značka: {brand}")
    data = load_all()
    try:
        year = date.fromisoformat(datum_prijeti).year
    except (TypeError, ValueError):
        year = date.today().year
        datum_prijeti = date.today().isoformat()

    counters = data.setdefault("counters", {})
    counter_key = f"{brand}:{year}"
    counters[counter_key] = counters.get(counter_key, 0) + 1
    prefix = BRANDS[brand]["prefix"]
    cislo = f"{prefix}-{year}-{counters[counter_key]:03d}"

    item = {
        "cislo": cislo,
        "znacka": brand,
        "servisni_partner": servisni_partner.strip(),
        "kontaktni_osoba": kontaktni_osoba.strip(),
        "datum_prijeti": datum_prijeti,
        "vytvoreno": datetime.now().isoformat(timespec="seconds"),
        "faze": {k: _empty_faze(k) for k in FAZE_KEYS},
    }
    data.setdefault("items", {})[cislo] = item
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
    item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return item


def update_header(cislo: str, patch: dict) -> dict | None:
    data = load_all()
    item = data.get("items", {}).get(cislo)
    if not item:
        return None
    for key in ("servisni_partner", "kontaktni_osoba", "datum_prijeti"):
        if key in patch:
            item[key] = patch[key]
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
    item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return item


def update_faze(cislo: str, faze_key: str, patch: dict) -> dict | None:
    if faze_key not in FAZE_KEYS:
        return None
    data = load_all()
    item = data.get("items", {}).get(cislo)
    if not item:
        return None
    faze = item["faze"][faze_key]
    for key in ("stav", "datum", "poznamka", "odpovedna_osoba", "dodavatel"):
        if key in patch:
            faze[key] = patch[key]
    _sync_uzavreno(item)
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
    item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return item


def update_krok(cislo: str, faze_key: str, idx: int, patch: dict) -> dict | None:
    if faze_key not in FAZE_KEYS:
        return None
    data = load_all()
    item = data.get("items", {}).get(cislo)
    if not item:
        return None
    kroky = item["faze"][faze_key].setdefault("kroky", _empty_kroky(faze_key))
    if idx < 0 or idx >= len(kroky):
        return None
    krok = kroky[idx]
    if "minuty" in patch:
        try:
            krok["minuty"] = max(0, float(patch["minuty"]))
        except (TypeError, ValueError):
            krok["minuty"] = 0
    if "nazev" in patch and krok.get("editable_nazev"):
        krok["nazev"] = (patch["nazev"] or "").strip()
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
    item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return item


def _priloha_dir(cislo: str, faze_key: str) -> Path:
    return UPLOAD_DIR / secure_filename(cislo) / faze_key


def priloha_path(cislo: str, faze_key: str, filename: str) -> Path:
    return _priloha_dir(cislo, faze_key) / secure_filename(filename)


def add_priloha(cislo: str, faze_key: str, file_storage) -> dict | None:
    if faze_key not in FAZE_KEYS:
        return None
    data = load_all()
    item = data.get("items", {}).get(cislo)
    if not item:
        return None

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None
    target_dir = _priloha_dir(cislo, faze_key)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_storage.save(target_dir / filename)

    prilohy = item["faze"][faze_key]["prilohy"]
    if filename not in prilohy:
        prilohy.append(filename)
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
    item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return item


def history_row(item: dict) -> dict:
    start = None
    if item.get("datum_prijeti"):
        try:
            start = date.fromisoformat(item["datum_prijeti"])
        except ValueError:
            start = None
    stav = overall_status(item)
    end = date.today()
    if item.get("uzavreno"):
        try:
            end = date.fromisoformat(item["uzavreno"])
        except ValueError:
            pass
    total_minutes = reklamace_total_minutes(item)
    return {
        "cislo": item["cislo"],
        "servisni_partner": item["servisni_partner"],
        "kontaktni_osoba": item.get("kontaktni_osoba", ""),
        "datum_prijeti": item.get("datum_prijeti"),
        "uzavreno": item.get("uzavreno"),
        "stav": stav,
        "stav_label": STAV_LABELS_HISTORIE.get(stav, stav),
        "doba_pracovnich_dni": business_days_between(start, end) if start else None,
        "aktualni_faze": aktualni_faze_label(item),
        "celkem_minut": total_minutes,
        "celkem_hodin": minutes_to_hours(total_minutes),
    }


def history_all(brand: str | None = None) -> list:
    return [history_row(i) for i in list_all(brand)]


def export_xlsx(brand: str, out_path: Path) -> Path:
    """Export do Excelu ve formátu předávacího protokolu pro fakturaci
    (podle vzoru "VAT Výkaz hodin"): jeden řádek na reklamaci, sloupcové
    bloky WETSy/GETAC/ACTIA IME s jednotlivými kroky v hodinách, TOTAL
    a souhrnné řádky Průměr/TOTAL/PŘEVOD/SAZBA/K FAKTURACI bez DPH."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import column_index_from_string, get_column_letter

    items = list_all(brand)

    HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
    HEAD_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    SUB_FILL = PatternFill("solid", fgColor="BDD7EE")
    SUB_FONT = Font(name="Arial", size=8.5, bold=True, color="1F4E79")
    THIN = Side(style="thin", color="B7B7B7")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    BOLD = Font(name="Arial", size=10, bold=True)
    NORMAL = Font(name="Arial", size=10)
    CENTER_WRAP = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    ws = wb.active
    ws.title = date.today().strftime("%m.%Y")
    ws.sheet_view.showGridLines = False

    for col in ("A", "B", "C", "D"):
        ws[f"{col}1"].font = HEAD_FONT
        ws[f"{col}1"].fill = HEAD_FILL
        ws[f"{col}1"].alignment = CENTER_WRAP
        ws.merge_cells(f"{col}1:{col}2")
    ws["A1"] = "ZÁKAZNÍK"
    ws["B1"] = "DATUM PŘÍJMU"
    ws["C1"] = "DATUM VYŘÍZENÍ"
    ws["D1"] = "POČET PRAC. DNŮ"

    total_col_idx = 4
    for faze_key, label, start_col in EXPORT_BLOKY:
        steps = KROKY_DEFS_BY_FAZE[faze_key]
        start_idx = column_index_from_string(start_col)
        end_idx = start_idx + len(steps) - 1
        end_col = get_column_letter(end_idx)
        ws.merge_cells(f"{start_col}1:{end_col}1")
        cell = ws[f"{start_col}1"]
        cell.value = label
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.alignment = CENTER_WRAP
        for i, step in enumerate(steps):
            c = ws.cell(row=2, column=start_idx + i, value=step["nazev"])
            c.font = SUB_FONT
            c.fill = SUB_FILL
            c.alignment = CENTER_WRAP
            c.border = BORDER
            ws.column_dimensions[get_column_letter(start_idx + i)].width = 11
        total_col_idx = max(total_col_idx, end_idx)

    total_col_idx += 1
    total_col = get_column_letter(total_col_idx)
    ws[f"{total_col}1"] = "TOTAL (hod.)"
    ws[f"{total_col}1"].font = HEAD_FONT
    ws[f"{total_col}1"].fill = HEAD_FILL
    ws[f"{total_col}1"].alignment = CENTER_WRAP
    ws.merge_cells(f"{total_col}1:{total_col}2")

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 13
    ws.column_dimensions["C"].width = 13
    ws.column_dimensions["D"].width = 13
    ws.column_dimensions[total_col].width = 12

    row = first_data_row = 3
    for item in items:
        zakaznik = item["servisni_partner"]
        if item.get("kontaktni_osoba"):
            zakaznik = f"{item['kontaktni_osoba']}, {item['servisni_partner']}"
        datum_prijeti = item.get("datum_prijeti")
        uzavreno = item.get("uzavreno")
        start = date.fromisoformat(datum_prijeti) if datum_prijeti else None
        end = date.fromisoformat(uzavreno) if uzavreno else date.today()
        doba = business_days_between(start, end) if start else None

        ws.cell(row=row, column=1, value=zakaznik).font = NORMAL
        c2 = ws.cell(row=row, column=2, value=start)
        c2.font = NORMAL
        c2.number_format = "DD.MM.YYYY"
        c3 = ws.cell(row=row, column=3, value=date.fromisoformat(uzavreno) if uzavreno else None)
        c3.font = NORMAL
        c3.number_format = "DD.MM.YYYY"
        ws.cell(row=row, column=4, value=doba).font = NORMAL

        celkem_hodin = 0.0
        for faze_key, _label, start_col in EXPORT_BLOKY:
            faze = item["faze"][faze_key]
            kroky = faze.get("kroky", [])
            steps_defs = KROKY_DEFS_BY_FAZE[faze_key]
            start_idx = column_index_from_string(start_col)
            for i in range(len(steps_defs)):
                minuty = kroky[i]["minuty"] if i < len(kroky) else 0
                hodiny = round((minuty or 0) / 60, 2)
                if hodiny:
                    c = ws.cell(row=row, column=start_idx + i, value=hodiny)
                    c.number_format = "0.0#"
                    c.font = NORMAL
                celkem_hodin += hodiny
            if len(kroky) > len(steps_defs):  # volný "doplnit" krok — jen do součtu
                celkem_hodin += round((kroky[-1]["minuty"] or 0) / 60, 2)
        ostatni = item["faze"].get("ostatni")
        if ostatni:
            celkem_hodin += round(faze_total_minutes(ostatni) / 60, 2)

        tcell = ws.cell(row=row, column=total_col_idx, value=round(celkem_hodin, 2))
        tcell.font = BOLD
        tcell.number_format = "0.0#"
        row += 1

    last_data_row = row - 1
    for r in range(first_data_row, row):
        for c in range(1, total_col_idx + 1):
            ws.cell(row=r, column=c).border = BORDER

    row += 1
    ws.cell(row=row, column=1, value="Průměr").font = BOLD
    if last_data_row >= first_data_row:
        avg_cell = ws.cell(row=row, column=4, value=f"=AVERAGE(D{first_data_row}:D{last_data_row})")
        avg_cell.font = BOLD
        avg_cell.number_format = "0.0#"
    row += 1
    total_row = row
    ws.cell(row=row, column=1, value="TOTAL").font = BOLD
    if last_data_row >= first_data_row:
        sum_cell = ws.cell(row=row, column=total_col_idx,
                            value=f"=SUM({total_col}{first_data_row}:{total_col}{last_data_row})")
        sum_cell.font = BOLD
        sum_cell.number_format = "0.0#"
    row += 1
    ws.cell(row=row, column=1, value="PŘEVOD hodin do dalšího měsíce").font = NORMAL
    row += 1
    sazba_row = row
    ws.cell(row=row, column=1, value="SAZBA").font = NORMAL
    row += 1
    ws.cell(row=row, column=1, value="K FAKTURACI bez DPH").font = BOLD
    fakt_cell = ws.cell(row=row, column=total_col_idx, value=f"={total_col}{total_row}*{total_col}{sazba_row}")
    fakt_cell.font = BOLD
    fakt_cell.number_format = "#,##0"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def remove_priloha(cislo: str, faze_key: str, filename: str) -> dict | None:
    if faze_key not in FAZE_KEYS:
        return None
    data = load_all()
    item = data.get("items", {}).get(cislo)
    if not item:
        return None

    filename = secure_filename(filename)
    prilohy = item["faze"][faze_key]["prilohy"]
    if filename in prilohy:
        prilohy.remove(filename)
        path = priloha_path(cislo, faze_key, filename)
        if path.exists():
            path.unlink()
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
    item["celkem_hodin"] = minutes_to_hours(reklamace_total_minutes(item))
    return item

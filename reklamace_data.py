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

# Předdefinované kroky procesu — stejné pro každou fázi/dodavatele.
# Poslední řádek má editovatelný název (volný "doplňovací" krok).
KROKY_DEFS = [
    {"nazev": "Telefonický příjem reklamace",            "minuty": 15},
    {"nazev": "Odchozí informační e-mail",                "minuty": 15},
    {"nazev": "Příchozí e-mail, založení složky",         "minuty": 30},
    {"nazev": "Založení ticketu",                         "minuty": 60},
    {"nazev": "Komunikace VAT & ŠPC (č. fa z VW)",        "minuty": 30},
    {"nazev": "Komunikace se zákazníkem (e-mail, tel.)",  "minuty": 30},
    {"nazev": "Odeslání reklamace",                       "minuty": 60},
    {"nazev": "Správa ticketu",                           "minuty": 30},
    {"nazev": "Potvrzení o ukončení reklamace",           "minuty": 15},
]
EXTRA_KROK_MINUTY_DEFAULT = 15

STAV_LABELS_HISTORIE = {"nová": "Otevřeno", "probíhá": "Probíhá", "vyřízeno": "Uzavřeno"}


def _empty_kroky() -> list:
    kroky = [{"nazev": d["nazev"], "minuty": d["minuty"], "editable_nazev": False} for d in KROKY_DEFS]
    kroky.append({"nazev": "", "minuty": EXTRA_KROK_MINUTY_DEFAULT, "editable_nazev": True})
    return kroky


def _empty_faze(key: str) -> dict:
    f = {
        "stav": "nezahájeno",
        "datum": None,
        "poznamka": "",
        "odpovedna_osoba": "",
        "prilohy": [],
        "kroky": _empty_kroky(),
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
    kroky = item["faze"][faze_key].setdefault("kroky", _empty_kroky())
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
        "stav": stav,
        "stav_label": STAV_LABELS_HISTORIE.get(stav, stav),
        "doba_pracovnich_dni": business_days_between(start, end) if start else None,
        "aktualni_faze": aktualni_faze_label(item),
        "celkem_minut": total_minutes,
        "celkem_hodin": minutes_to_hours(total_minutes),
    }


def history_all(brand: str | None = None) -> list:
    return [history_row(i) for i in list_all(brand)]


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

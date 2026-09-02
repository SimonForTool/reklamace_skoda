"""
Datový model a úložiště pro Reklamace Škoda.

Reklamace prochází 4 nezávislými fázemi (WETSy, GETAC, ACTIA IMEA,
Ostatní dodavatel), z nichž každá se eviduje samostatně (stav, datum,
poznámka, odpovědná osoba, přílohy). Interní číslo má formát
REK-<rok>-<pořadové číslo v daném roce>, rok se odvozuje z data přijetí.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from werkzeug.utils import secure_filename

DATA_DIR = Path("data")
DATA_PATH = DATA_DIR / "reklamace.json"
UPLOAD_DIR = Path("uploads") / "reklamace"

FAZE_DEFS = [
    {"key": "wetsy",   "label": "WETSy"},
    {"key": "getac",   "label": "GETAC"},
    {"key": "actia",   "label": "ACTIA IMEA"},
    {"key": "ostatni", "label": "Ostatní dodavatel"},
]
FAZE_KEYS = [f["key"] for f in FAZE_DEFS]

STAVY = ["nezahájeno", "probíhá", "hotovo"]


def _empty_faze(key: str) -> dict:
    f = {
        "stav": "nezahájeno",
        "datum": None,
        "poznamka": "",
        "odpovedna_osoba": "",
        "prilohy": [],
    }
    if key == "ostatni":
        f["dodavatel"] = ""
    return f


def _empty_store() -> dict:
    return {"counters": {}, "items": {}}


def load_all() -> dict:
    if not DATA_PATH.exists():
        return _empty_store()
    return json.loads(DATA_PATH.read_text())


def save_all(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def list_all() -> list:
    data = load_all()
    items = list(data.get("items", {}).values())
    items.sort(key=lambda i: i["vytvoreno"], reverse=True)
    for item in items:
        item["celkovy_stav"] = overall_status(item)
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
    return item


def new_reklamace(servisni_partner: str, kontaktni_osoba: str, datum_prijeti: str) -> dict:
    data = load_all()
    try:
        year = date.fromisoformat(datum_prijeti).year
    except (TypeError, ValueError):
        year = date.today().year
        datum_prijeti = date.today().isoformat()

    counters = data.setdefault("counters", {})
    year_key = str(year)
    counters[year_key] = counters.get(year_key, 0) + 1
    cislo = f"REK-{year}-{counters[year_key]:03d}"

    item = {
        "cislo": cislo,
        "servisni_partner": servisni_partner.strip(),
        "kontaktni_osoba": kontaktni_osoba.strip(),
        "datum_prijeti": datum_prijeti,
        "vytvoreno": datetime.now().isoformat(timespec="seconds"),
        "faze": {k: _empty_faze(k) for k in FAZE_KEYS},
    }
    data.setdefault("items", {})[cislo] = item
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
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
    save_all(data)
    item["celkovy_stav"] = overall_status(item)
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
    return item


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
    return item

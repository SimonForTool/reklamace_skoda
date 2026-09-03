"""
Reklamace Škoda — evidence reklamací servisních partnerů.

Lokální spuštění: python3 app.py
Produkční spuštění (Railway/Render/PythonAnywhere): gunicorn app:app
"""
import os
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, abort
import reklamace_data

OUTPUT_DIR = Path("output") / "reklamace"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB na požadavek/přílohu

# ── HTML stránky ──────────────────────────────────────────────────────────────

@app.route("/")
def landing_page():
    return render_template("landing.html", brands=reklamace_data.BRANDS)

@app.route("/<brand>")
def reklamace_list_page(brand):
    if brand not in reklamace_data.BRANDS:
        abort(404)
    return render_template("reklamace_list.html", brand=brand,
                            brand_label=reklamace_data.BRANDS[brand]["label"])

@app.route("/<brand>/reklamace/<cislo>")
def reklamace_detail_page(brand, cislo):
    if brand not in reklamace_data.BRANDS:
        abort(404)
    item = reklamace_data.get_reklamace(cislo)
    if not item or item.get("znacka", reklamace_data.DEFAULT_BRAND) != brand:
        abort(404, f"Reklamace {cislo} nenalezena.")
    return render_template("reklamace_detail.html", cislo=cislo, brand=brand,
                            brand_label=reklamace_data.BRANDS[brand]["label"],
                            faze_defs=reklamace_data.FAZE_DEFS,
                            krok_katalog=reklamace_data.KROK_KATALOG,
                            dopravci=reklamace_data.DOPRAVCI)

@app.route("/<brand>/historie")
def reklamace_historie_page(brand):
    # Historie byla sloučena do hlavního přehledu reklamací.
    if brand not in reklamace_data.BRANDS:
        abort(404)
    return redirect(f"/{brand}")

# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/reklamace")
def api_reklamace_list():
    brand = request.args.get("znacka")
    if brand and brand not in reklamace_data.BRANDS:
        return jsonify({"status": "error", "message": "Neznámá značka."}), 400
    return jsonify(reklamace_data.list_all(brand))

@app.get("/api/reklamace/historie")
def api_reklamace_historie():
    brand = request.args.get("znacka")
    if brand and brand not in reklamace_data.BRANDS:
        return jsonify({"status": "error", "message": "Neznámá značka."}), 400
    return jsonify(reklamace_data.history_all(brand))

@app.post("/api/reklamace")
def api_reklamace_create():
    body = request.get_json(force=True)
    brand = body.get("znacka") or ""
    servisni_partner = (body.get("servisni_partner") or "").strip()
    kontaktni_osoba = (body.get("kontaktni_osoba") or "").strip()
    datum_prijeti = body.get("datum_prijeti") or ""
    if brand not in reklamace_data.BRANDS:
        return jsonify({"status": "error", "message": "Neznámá značka."}), 400
    if not servisni_partner or not datum_prijeti:
        return jsonify({"status": "error", "message": "Servisní partner a datum přijetí jsou povinné."}), 400
    item = reklamace_data.new_reklamace(brand, servisni_partner, kontaktni_osoba, datum_prijeti)
    return jsonify(item)

@app.get("/api/reklamace/<cislo>")
def api_reklamace_get(cislo):
    item = reklamace_data.get_reklamace(cislo)
    if not item:
        abort(404, f"Reklamace {cislo} nenalezena.")
    return jsonify(item)

@app.post("/api/reklamace/<cislo>")
def api_reklamace_update(cislo):
    body = request.get_json(force=True)
    item = reklamace_data.update_header(cislo, body)
    if not item:
        abort(404, f"Reklamace {cislo} nenalezena.")
    return jsonify(item)

@app.post("/api/reklamace/<cislo>/<faze_key>")
def api_reklamace_faze_update(cislo, faze_key):
    body = request.get_json(force=True)
    item = reklamace_data.update_faze(cislo, faze_key, body)
    if not item:
        abort(404, "Reklamace nebo fáze nenalezena.")
    return jsonify(item)

@app.post("/api/reklamace/<cislo>/<faze_key>/krok")
def api_reklamace_krok_add(cislo, faze_key):
    body = request.get_json(force=True)
    nazev = (body.get("nazev") or "").strip()
    item = reklamace_data.add_krok(cislo, faze_key, nazev)
    if not item:
        abort(404, "Reklamace nebo fáze nenalezena.")
    return jsonify(item)

@app.post("/api/reklamace/<cislo>/<faze_key>/krok/<int:idx>")
def api_reklamace_krok_update(cislo, faze_key, idx):
    body = request.get_json(force=True)
    item = reklamace_data.update_krok(cislo, faze_key, idx, body)
    if not item:
        abort(404, "Reklamace, fáze nebo krok nenalezen.")
    return jsonify(item)

@app.delete("/api/reklamace/<cislo>/<faze_key>/krok/<int:idx>")
def api_reklamace_krok_delete(cislo, faze_key, idx):
    item = reklamace_data.remove_krok(cislo, faze_key, idx)
    if not item:
        abort(404, "Reklamace, fáze nebo krok nenalezen.")
    return jsonify(item)

@app.post("/api/reklamace/<cislo>/<faze_key>/priloha")
def api_reklamace_priloha_upload(cislo, faze_key):
    file_storage = request.files.get("file")
    if not file_storage or not file_storage.filename:
        return jsonify({"status": "error", "message": "Žádný soubor nebyl vybrán."}), 400
    item = reklamace_data.add_priloha(cislo, faze_key, file_storage)
    if not item:
        abort(404, "Reklamace nebo fáze nenalezena.")
    return jsonify(item)

@app.delete("/api/reklamace/<cislo>/<faze_key>/priloha/<filename>")
def api_reklamace_priloha_delete(cislo, faze_key, filename):
    item = reklamace_data.remove_priloha(cislo, faze_key, filename)
    if not item:
        abort(404, "Reklamace nebo fáze nenalezena.")
    return jsonify(item)

@app.get("/api/reklamace/<cislo>/<faze_key>/priloha/<filename>")
def api_reklamace_priloha_download(cislo, faze_key, filename):
    path = reklamace_data.priloha_path(cislo, faze_key, filename)
    if not path.exists():
        abort(404, "Příloha nenalezena.")
    return send_file(path, as_attachment=True, download_name=filename)

@app.get("/api/reklamace/export")
def api_reklamace_export():
    brand = request.args.get("znacka")
    if brand not in reklamace_data.BRANDS:
        return jsonify({"status": "error", "message": "Neznámá značka."}), 400
    cisla_param = request.args.get("cisla")
    cisla = [c for c in cisla_param.split(",") if c] if cisla_param is not None else None
    from datetime import date
    filename = f"VAT_Vykaz_hodin_{brand}_{date.today().strftime('%m.%Y')}.xlsx"
    out_path = OUTPUT_DIR / filename
    reklamace_data.export_xlsx(brand, out_path, cisla)
    return send_file(out_path, as_attachment=True, download_name=filename)

@app.get("/api/nastaveni")
def api_nastaveni_get():
    brand = request.args.get("znacka")
    if brand not in reklamace_data.BRANDS:
        return jsonify({"status": "error", "message": "Neznámá značka."}), 400
    return jsonify(reklamace_data.get_nastaveni(brand))

@app.post("/api/nastaveni")
def api_nastaveni_update():
    body = request.get_json(force=True)
    brand = body.get("znacka")
    if brand not in reklamace_data.BRANDS:
        return jsonify({"status": "error", "message": "Neznámá značka."}), 400
    return jsonify(reklamace_data.update_nastaveni(brand, body))

@app.post("/api/reklamace/potvrdit-fakturaci")
def api_potvrdit_fakturaci():
    body = request.get_json(force=True)
    brand = body.get("znacka")
    if brand not in reklamace_data.BRANDS:
        return jsonify({"status": "error", "message": "Neznámá značka."}), 400
    cisla = body.get("cisla")
    return jsonify(reklamace_data.potvrdit_fakturaci(brand, cisla))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

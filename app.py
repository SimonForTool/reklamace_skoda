"""
Reklamace Škoda — evidence reklamací servisních partnerů.
Spuštění: python3 app.py
"""
from flask import Flask, jsonify, render_template, request, send_file, abort
import reklamace_data

app = Flask(__name__)

# ── HTML stránky ──────────────────────────────────────────────────────────────

@app.route("/")
def reklamace_list_page():
    return render_template("reklamace_list.html")

@app.route("/reklamace/<cislo>")
def reklamace_detail_page(cislo):
    if not reklamace_data.get_reklamace(cislo):
        abort(404, f"Reklamace {cislo} nenalezena.")
    return render_template("reklamace_detail.html", cislo=cislo, faze_defs=reklamace_data.FAZE_DEFS)

# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/reklamace")
def api_reklamace_list():
    return jsonify(reklamace_data.list_all())

@app.post("/api/reklamace")
def api_reklamace_create():
    body = request.get_json(force=True)
    servisni_partner = (body.get("servisni_partner") or "").strip()
    kontaktni_osoba = (body.get("kontaktni_osoba") or "").strip()
    datum_prijeti = body.get("datum_prijeti") or ""
    if not servisni_partner or not datum_prijeti:
        return jsonify({"status": "error", "message": "Servisní partner a datum přijetí jsou povinné."}), 400
    item = reklamace_data.new_reklamace(servisni_partner, kontaktni_osoba, datum_prijeti)
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

if __name__ == "__main__":
    app.run(debug=True, port=5000)

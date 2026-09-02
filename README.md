# Reklamace Škoda

Evidence reklamací servisních partnerů — od založení po vyřízení.

## Spuštění

```bash
pip install -r requirements.txt
python3 app.py
```

Appka poběží na `http://127.0.0.1:5000`.

## Funkce

- Založení nové reklamace s automatickým interním číslem ve formátu
  `REK-<rok>-<pořadí>` (číselná řada se resetuje každý rok podle data
  přijetí reklamace).
- Evidence servisního partnera, kontaktní osoby a data přijetí.
- 4 nezávislé fáze procesu reklamace: **WETSy**, **GETAC**, **ACTIA IMEA**
  a **Ostatní dodavatel** (s volitelným polem pro konkrétního dodavatele,
  např. Midtronics, Deutronic…). Fáze lze vyplňovat v libovolném pořadí.
- Pro každou fázi: stav (nezahájeno/probíhá/hotovo), datum, odpovědná
  osoba, poznámka a přílohy k nahrání.
- Přehled všech reklamací s barevným indikátorem stavu.

## Data

Reklamace se ukládají do `data/reklamace.json`, přílohy do
`uploads/reklamace/<číslo>/<fáze>/`.

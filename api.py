from flask import Flask, request, jsonify
from collections import deque
from flask_cors import CORS
import os, time, secrets

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Segredo simples partilhado (bridge usa o mesmo)
BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", "neves-12345")

# fila para o bridge consumir (novas marcações)
QUEUE = deque(maxlen=5000)

# histórico/confirmadas (para detectar conflitos)
BOOKINGS = deque(maxlen=5000)

def now_id():
    return str(int(time.time() * 1_000_000)) + "-" + secrets.token_hex(3)

def bad(msg, code=400):
    return jsonify({"error": msg}), code

def parse_hhmm(s: str) -> int:
    # "14:30" -> 870 (minutos)
    s = (s or "").strip()
    if len(s) < 5 or s[2] != ":":
        return -1
    try:
        hh = int(s[0:2])
        mm = int(s[3:5])
        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            return -1
        return hh * 60 + mm
    except:
        return -1

def overlaps(s1, e1, s2, e2) -> bool:
    return (s1 < e2) and (s2 < e1)

@app.get("/")
def home():
    return jsonify({
        "ok": True,
        "service": "barbearia-api",
        "queued": len(QUEUE),
        "bookings": len(BOOKINGS)
    })

@app.post("/book")
def book():
    data = request.get_json(silent=True) or {}
    required = ["name", "phone", "service", "barber", "date", "time", "dur"]
    for k in required:
        if not str(data.get(k, "")).strip():
            return bad(f"Campo obrigatório em falta: {k}")

    # normaliza HH:MM
    t = str(data["time"]).strip()
    if len(t) >= 5:
        t = t[:5]
    data["time"] = t

    bid = now_id()
    item = {
        "id": bid,
        "name": str(data.get("name","")).strip(),
        "phone": str(data.get("phone","")).strip(),
        "email": str(data.get("email","")).strip(),
        "service": str(data.get("service","")).strip(),
        "barber": str(data.get("barber","")).strip(),
        "date": str(data.get("date","")).strip(),   # AAAA-MM-DD
        "time": str(data.get("time","")).strip(),   # HH:MM
        "dur": int(float(data.get("dur", 30))),
        "notes": str(data.get("notes","")).strip(),
        "created_at": int(time.time())
    }

    # --- BLOQUEAR CONFLITOS ---
    ns = parse_hhmm(item["time"])
    if ns < 0:
        return bad("Hora inválida. Usa HH:MM")

    nd = int(item["dur"]) if int(item["dur"]) > 0 else 0
    ne = ns + nd

    for b in BOOKINGS:
        if b.get("date") != item["date"]:
            continue
        if b.get("barber") != item["barber"]:
            continue

        os_ = parse_hhmm(b.get("time"))
        if os_ < 0:
            continue
        od = int(b.get("dur", 0)) if int(b.get("dur", 0)) > 0 else 0
        oe = os_ + od

        if overlaps(ns, ne, os_, oe):
            return jsonify({
                "ok": False,
                "error": "conflict",
                "msg": f"Hora ocupada: {item['barber']} já tem marcação em {item['date']} às {b.get('time')}."
            }), 409

    # guarda
    QUEUE.append(item)     # para o bridge puxar
    BOOKINGS.append(item)  # para bloquear conflitos futuros

    return jsonify({"ok": True, "id": bid})

@app.get("/pull")
def pull():
    secret = request.args.get("secret", "")
    if secret != BRIDGE_SECRET:
        return bad("unauthorized", 401)

    limit = int(request.args.get("limit", "50"))
    out = []
    for _ in range(min(limit, len(QUEUE))):
        out.append(QUEUE.popleft())
    return jsonify({"ok": True, "items": out})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

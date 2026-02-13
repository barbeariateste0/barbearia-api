
from flask import Flask, request, jsonify
from collections import deque
from flask_cors import CORS
import os, time, secrets

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
# Segredo simples partilhado (bridge usa o mesmo)
BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", "muda-isto")

# fila em memória
QUEUE = deque(maxlen=5000)

def now_id():
    return str(int(time.time() * 1_000_000)) + "-" + secrets.token_hex(3)

def bad(msg, code=400):
    return jsonify({"error": msg}), code

@app.get("/")
def home():
    return jsonify({"ok": True, "service": "barbearia-api", "queued": len(QUEUE)})

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

    QUEUE.append(item)
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

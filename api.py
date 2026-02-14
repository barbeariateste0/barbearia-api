from flask import Flask, request, jsonify
from collections import deque, defaultdict
from flask_cors import CORS
import os, time, secrets

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", "muda-isto")

# fila para o bridge puxar (não é o “livro” definitivo)
QUEUE = deque(maxlen=5000)

# “livro” em memória para o site poder ver ocupações
# chave: (date, barber) -> lista de bookings
BOOKINGS = defaultdict(list)

def now_id():
    return str(int(time.time() * 1_000_000)) + "-" + secrets.token_hex(3)

def bad(msg, code=400):
    return jsonify({"error": msg}), code

def valid_time(hhmm: str) -> bool:
    if not hhmm or len(hhmm) != 5 or hhmm[2] != ":":
        return False
    try:
        hh = int(hhmm[:2]); mm = int(hhmm[3:])
        return 0 <= hh <= 23 and 0 <= mm <= 59
    except:
        return False

def to_minutes(hhmm: str) -> int:
    hh = int(hhmm[:2]); mm = int(hhmm[3:])
    return hh * 60 + mm

def overlaps(s1, e1, s2, e2):
    return (s1 < e2) and (s2 < e1)

def has_conflict(date: str, barber: str, hhmm: str, dur: int):
    if not valid_time(hhmm): 
        return True, "Hora inválida"
    if dur <= 0:
        return True, "Duração inválida"

    ns = to_minutes(hhmm)
    ne = ns + dur

    for b in BOOKINGS[(date, barber)]:
        os_ = to_minutes(b["time"])
        oe_ = os_ + int(b.get("dur", 30))
        if overlaps(ns, ne, os_, oe_):
            return True, f"Conflito com {b.get('time')} ({b.get('dur')} min) — {b.get('name','')}"
    return False, ""

@app.get("/")
def home():
    return jsonify({
        "ok": True,
        "service": "barbearia-api",
        "queued": len(QUEUE),
        "booked_keys": len(BOOKINGS)
    })

@app.get("/day")
def day():
    # Ex: /day?date=2026-02-14&barber=Pedro
    date = (request.args.get("date") or "").strip()
    barber = (request.args.get("barber") or "").strip()

    if not date:
        return bad("date obrigatório (AAAA-MM-DD)")
    if not barber:
        return bad("barber obrigatório")

    items = BOOKINGS.get((date, barber), [])
    # devolve só o necessário p/ UI
    out = [{
        "id": b["id"],
        "time": b["time"],
        "dur": int(b.get("dur", 30)),
        "name": b.get("name",""),
        "service": b.get("service",""),
        "phone": b.get("phone",""),
        "status": b.get("status","Marcado")
    } for b in items]

    return jsonify({"ok": True, "items": out})

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
    if not valid_time(t):
        return bad("Hora inválida. Usa HH:MM", 400)

    date = str(data.get("date","")).strip()
    barber = str(data.get("barber","")).strip()
    dur = int(float(data.get("dur", 30)))

    # força marcações em múltiplos de 30 (para bater com a grelha)
    if dur % 30 != 0:
        return bad("Duração tem de ser múltiplo de 30 (ex: 30, 60, 90).", 400)

    # anti-conflito (por barbeiro)
    conflict, desc = has_conflict(date, barber, t, dur)
    if conflict:
        return bad("Horário ocupado. " + desc, 409)

    bid = now_id()
    item = {
        "id": bid,
        "name": str(data.get("name","")).strip(),
        "phone": str(data.get("phone","")).strip(),
        "email": str(data.get("email","")).strip(),
        "service": str(data.get("service","")).strip(),
        "barber": barber,
        "date": date,
        "time": t,
        "dur": dur,
        "notes": str(data.get("notes","")).strip(),
        "status": "Marcado",
        "created_at": int(time.time())
    }

    # guarda no “livro” (para UI) e na fila (para bridge)
    BOOKINGS[(date, barber)].append(item)
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

    # NOTE: não apagamos do BOOKINGS, para a página continuar a ver ocupados
    return jsonify({"ok": True, "items": out})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

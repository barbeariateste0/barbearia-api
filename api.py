from flask import Flask, request, jsonify
from flask_cors import CORS
from collections import deque
import os, time, secrets
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", "muda-isto")

# fila para o bridge consumir
QUEUE = deque(maxlen=5000)

# “base de dados” em memória para disponibilidade/conflitos
BOOKINGS = deque(maxlen=20000)

OPEN_MIN = 9 * 60          # 09:00
CLOSE_MIN = 20 * 60        # 20:00 (última marcação tem de caber)
STEP_MIN = 5               # 5 em 5 minutos (bloqueia 14:31)
MAX_DUR = 240

def now_id():
    return str(int(time.time() * 1_000_000)) + "-" + secrets.token_hex(3)

def bad(msg, code=400):
    return jsonify({"error": msg}), code

def parse_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except:
        return False

def parse_hhmm(h):
    if not h or len(h) < 5 or h[2] != ":":
        return None
    try:
        hh = int(h[:2]); mm = int(h[3:5])
    except:
        return None
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return hh * 60 + mm

def overlaps(s1, e1, s2, e2):
    return (s1 < e2) and (s2 < e1)

def has_conflict(date, barber, start_min, dur, ignore_id=None):
    end_min = start_min + dur
    for it in BOOKINGS:
        if it.get("date") != date: 
            continue
        if it.get("barber") != barber:
            continue
        if ignore_id and it.get("id") == ignore_id:
            continue

        os_ = parse_hhmm(it.get("time",""))
        od  = int(it.get("dur", 30))
        if os_ is None: 
            continue
        oe_ = os_ + od
        if overlaps(start_min, end_min, os_, oe_):
            return it
    return None

def validate_step(start_min):
    return (start_min % STEP_MIN) == 0

@app.get("/")
def home():
    return jsonify({
        "ok": True,
        "service": "barbearia-api",
        "queued": len(QUEUE),
        "bookings": len(BOOKINGS),
        "step_min": STEP_MIN
    })

@app.post("/book")
def book():
    data = request.get_json(silent=True) or {}
    required = ["name", "phone", "service", "barber", "date", "time", "dur"]
    for k in required:
        if not str(data.get(k, "")).strip():
            return bad(f"Campo obrigatório em falta: {k}")

    date = str(data["date"]).strip()
    if not parse_date(date):
        return bad("Data inválida (use AAAA-MM-DD)")

    # normaliza HH:MM
    t = str(data["time"]).strip()[:5]
    start_min = parse_hhmm(t)
    if start_min is None:
        return bad("Hora inválida (use HH:MM)")

    dur = int(float(data.get("dur", 30)))
    if dur < 10: dur = 10
    if dur > MAX_DUR: dur = MAX_DUR

    # horário de trabalho
    if start_min < OPEN_MIN or (start_min + dur) > CLOSE_MIN:
        return bad("Fora do horário (09:00-20:00)")

    # bloqueia 14:31 etc
    if not validate_step(start_min):
        return bad(f"Hora inválida: só aceitamos de {STEP_MIN} em {STEP_MIN} minutos (ex: 14:30, 14:35...)")

    barber = str(data["barber"]).strip()

    # conflito?
    conf = has_conflict(date, barber, start_min, dur)
    if conf:
        return jsonify({
            "ok": False,
            "error": "conflict",
            "conflict_with": {
                "time": conf.get("time"),
                "dur": conf.get("dur"),
                "name": conf.get("name"),
                "service": conf.get("service"),
                "barber": conf.get("barber")
            }
        }), 409

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
        "created_at": int(time.time())
    }

    BOOKINGS.append(item)  # entra já no “ocupado” para slots
    QUEUE.append(item)     # bridge vai buscar
    return jsonify({"ok": True, "id": bid})

@app.get("/slots")
def slots():
    date = request.args.get("date","").strip()
    barber = request.args.get("barber","").strip()
    dur = int(float(request.args.get("dur","30")))

    if not parse_date(date):
        return bad("date inválida (AAAA-MM-DD)")
    if not barber:
        return bad("barber em falta")
    if dur < 10: dur = 10
    if dur > MAX_DUR: dur = MAX_DUR

    out = []
    t = OPEN_MIN
    while (t + dur) <= CLOSE_MIN:
        conf = has_conflict(date, barber, t, dur)
        if not conf:
            hh = t // 60
            mm = t % 60
            out.append(f"{hh:02d}:{mm:02d}")
        t += STEP_MIN

    return jsonify({"ok": True, "date": date, "barber": barber, "dur": dur, "slots": out})

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

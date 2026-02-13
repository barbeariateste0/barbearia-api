from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import os

app = FastAPI()

AGENDA_FILE = "agenda_online.txt"

class Booking(BaseModel):
    name: str
    email: str
    service: str
    date: str
    time: str

@app.post("/book")
def create_booking(booking: Booking):
    line = f"{booking.date}|{booking.time}|{booking.name}|{booking.email}|{booking.service}\n"

    with open(AGENDA_FILE, "a", encoding="utf-8") as f:
        f.write(line)

    return {"status": "ok"}

@app.get("/")
def root():
    return {"status": "API Barbearia Online OK"}

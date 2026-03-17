from fastapi import FastAPI, HTTPException
from typing import Dict, Any
import uuid

app = FastAPI()

SESSIONS: Dict[str, Any] = {}

MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


@app.post("/session")
def create_session():
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "month_idx": 0,
        "history": [],
        "current": {
            "month": MONTHS[0],
            "start_storage": 0.0,
            "loss": 0.0,
            "forecast": None,
            "climatology": None
        }
    }
    return {"session_id": session_id}


@app.post("/session/{session_id}/next")
def next_month(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    s = SESSIONS[session_id]

    # Save current month if completed
    if "end_storage" in s["current"]:
        s["history"].append(s["current"])

    # Move to next month
    s["month_idx"] = (s["month_idx"] + 1) % 12
    new_month = MONTHS[s["month_idx"]]

    prev = s["history"][-1] if s["history"] else s["current"]

    s["current"] = {
        "month": new_month,
        "start_storage": prev.get("end_storage", 0.0),
        "loss": 0.0,
        "forecast": None,
        "climatology": None
    }

    return s["current"]


@app.post("/session/{session_id}/update")
def update_current(session_id: str, data: Dict[str, Any]):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    s = SESSIONS[session_id]
    s["current"].update(data)

    return s["current"]


@app.post("/session/{session_id}/finalize")
def finalize(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    s = SESSIONS[session_id]

    # Ensure current month is included
    if "end_storage" in s["current"] and s["current"] not in s["history"]:
        s["history"].append(s["current"])

    # Scoring
    surcharges = sum(
        1 for m in s["history"]
        if m.get("flags", {}).get("surcharge")
    )

    deficits = sum(
        1 for m in s["history"]
        if m.get("flags", {}).get("deficit")
    )

    score = 50
    if surcharges > 0:
        score -= surcharges * 20
    score -= deficits * 5

    return {
        "score": score,
        "breakdown": {
            "surcharges": surcharges,
            "deficits": deficits
        },
        "history": s["history"]
    }


@app.get("/")
def root():
    return {"message": "API is running"}
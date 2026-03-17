from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
import uuid

app = FastAPI(title="FIRO Tabletop API", version="0.1")

EXCEL_PATH = "data/Table-top-exercise.xlsx"

# In-memory sessions (good for demo; later you can add a database)
SESSIONS = {}

MONTHS = ["May", "June", "July", "August", "September"]

CONSTRAINTS = {
    "max_capacity": 13.0,
    "conservation_pool": 5.0,
    "flood_pool": 8.0,
    "firo_limit": 6.0,
}

class ReleaseIn(BaseModel):
    release: float

def load_workbook():
    # Loads all sheets
    xls = pd.ExcelFile(EXCEL_PATH)
    sheets = {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}
    return sheets

def month_index(month: str) -> int:
    if month not in MONTHS:
        raise ValueError("Invalid month")
    return MONTHS.index(month)

@app.get("/")
def root():
    return {"ok": True, "message": "FIRO Tabletop API is running"}

@app.get("/sheets")
def list_sheets():
    sheets = load_workbook()
    return {"sheets": list(sheets.keys())}

@app.post("/session/start")
def start_session():
    # TODO: replace these placeholders with values read from Excel once we map sheets/columns
    session_id = str(uuid.uuid4())
    start_storage = 7.0

    SESSIONS[session_id] = {
        "month_idx": 0,
        "history": [],
        "current": {
            "month": MONTHS[0],
            "start_storage": start_storage,
            "loss": 0.0,        # from Excel
            "forecast": None,   # from Excel
            "climatology": None # from Excel
        },
        "done": False
    }

    return {
        "session_id": session_id,
        **SESSIONS[session_id]["current"],
        "constraints": CONSTRAINTS
    }

@app.get("/session/{session_id}/state")
def get_state(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    s = SESSIONS[session_id]
    return {
        "done": s["done"],
        **s["current"],
        "constraints": CONSTRAINTS
    }

@app.post("/session/{session_id}/release")
def submit_release(session_id: str, body: ReleaseIn):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    s = SESSIONS[session_id]
    if s["done"]:
        raise HTTPException(status_code=400, detail="Session already completed")

    current = s["current"]
    if "release" in current:
        raise HTTPException(status_code=400, detail="Decision already locked for this month")

    release = float(body.release)
    if release < 0:
        raise HTTPException(status_code=400, detail="Release must be >= 0")

    # TODO: actual inflow must come from Excel and be hidden until now
    actual_inflow = 2.0

    start_storage = float(current["start_storage"])
    loss = float(current["loss"] or 0.0)
    end_storage = start_storage + actual_inflow - release - loss

    surcharge = end_storage > CONSTRAINTS["max_capacity"]
    deficit = end_storage < CONSTRAINTS["conservation_pool"]
    firo_violation = end_storage > CONSTRAINTS["firo_limit"]

    current.update({
        "release": release,
        "actual_inflow": actual_inflow,
        "end_storage": end_storage,
        "flags": {"surcharge": surcharge, "deficit": deficit, "firo_violation": firo_violation}
    })

    return current

@app.post("/session/{session_id}/next")
def next_month(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    s = SESSIONS[session_id]
    if s["done"]:
        raise HTTPException(status_code=400, detail="Session already completed")

    current = s["current"]
    if "end_storage" not in current:
        raise HTTPException(status_code=400, detail="Submit release first")

    s["history"].append(current)

    s["month_idx"] += 1
    if s["month_idx"] >= len(MONTHS):
        s["done"] = True
        return {"done": True, "message": "Simulation ended. Call /finalize to compute score."}

    new_month = MONTHS[s["month_idx"]]
    s["current"] = {
        "month": new_month,
        "start_storage": current["end_storage"],
        "loss": 0.0,        # from Excel
        "forecast": None,   # from Excel
        "climatology": None # from Excel
    }
    return s["current"]

@app.post("/session/{session_id}/finalize")
def finalize(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    s = SESSIONS[session_id]
    # Include current month in history if it has been completed
    if "end_storage" in s["current"] and s["current"] not in s["history"]:
        s["history"].append(s["current"])

    # Basic scoring placeholder (we will match your real rules once we map Excel)
    surcharges = sum(1 for m in s["history"] if m.get("flags", {}).get("surcharge"))
    deficits = sum(1 for m in s["history"] if m.get("flags", {}).get("deficit"))

    score = 50 if surcharges == 0 else 0
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
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests

app = FastAPI()

DEVICE_NAME = os.getenv("DEVICE_NAME", "rpi-unknown")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:270m")


class OllamaRequest(BaseModel):
    prompt: str
    model: str | None = None


@app.get("/metrics/temperature")
def get_temperature():
    """Température CPU du Raspberry Pi (fichier monté dans /host/thermal_zone0_temp)."""
    path = "/host/thermal_zone0_temp"
    try:
        with open(path, "r") as f:
            milli_c = int(f.read().strip())
        temp_c = milli_c / 1000.0
        return {"device": DEVICE_NAME, "temperature_c": temp_c}
    except Exception as e:
        print(f"[{DEVICE_NAME}] Erreur lecture température: {e}")
        return {"device": DEVICE_NAME, "temperature_c": None}


@app.post("/ollama/generate")
def generate_text(req: OllamaRequest):
    """Relais vers Ollama local en /api/generate."""
    model = req.model or OLLAMA_MODEL
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": req.prompt,
        "stream": False,
    }

    try:
        r = requests.post(url, json=payload, timeout=300)
        r.raise_for_status()
    except Exception as e:
        print(f"[{DEVICE_NAME}] Erreur appel Ollama: {e}")
        raise HTTPException(status_code=502, detail="Erreur lors de l'appel à Ollama")

    data = r.json()
    return {
        "device": DEVICE_NAME,
        "model": model,
        "prompt": req.prompt,
        "response": data.get("response", ""),
    }

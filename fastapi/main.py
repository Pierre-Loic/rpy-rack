from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import os
import time
import requests

app = FastAPI()

DEVICE_NAME = os.getenv("DEVICE_NAME", "rpi-unknown")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:270m")

# Chemins des pseudo-systèmes de fichiers de l'hôte, montés dans le conteneur
# (voir docker-compose.yml). On retombe sur les chemins natifs si non montés.
HOST_PROC = os.getenv("HOST_PROC", "/host/proc")
HOST_CPU = os.getenv("HOST_CPU", "/host/sys_cpu")
if not os.path.isdir(HOST_PROC):
    HOST_PROC = "/proc"
if not os.path.isdir(HOST_CPU):
    HOST_CPU = "/sys/devices/system/cpu"


class OllamaRequest(BaseModel):
    prompt: str
    model: str | None = None
    stream: bool = False


def _read_temperature_c():
    """Température CPU en °C (fichier monté dans /host/thermal_zone0_temp)."""
    with open("/host/thermal_zone0_temp", "r") as f:
        milli_c = int(f.read().strip())
    return milli_c / 1000.0


def _read_ram_used_percent():
    """Pourcentage de RAM utilisée à partir de /proc/meminfo."""
    meminfo = {}
    with open(f"{HOST_PROC}/meminfo", "r") as f:
        for line in f:
            key, _, rest = line.partition(":")
            if rest:
                meminfo[key.strip()] = int(rest.split()[0])  # valeur en kB
    total = meminfo.get("MemTotal", 0)
    available = meminfo.get("MemAvailable", 0)
    if total <= 0:
        return None
    return round((total - available) / total * 100.0, 1)


def _list_cpu_cores():
    """Liste triée des cœurs logiques (cpu0, cpu1, ...) exposés par sysfs."""
    cores = [
        d for d in os.listdir(HOST_CPU)
        if d.startswith("cpu") and d[3:].isdigit()
    ]
    return sorted(cores, key=lambda d: int(d[3:]))


def _read_cpu_freq_mhz():
    """Fréquence courante de chaque cœur (MHz) depuis sysfs cpufreq."""
    per_core = []
    for core in _list_cpu_cores():
        freq_path = os.path.join(HOST_CPU, core, "cpufreq", "scaling_cur_freq")
        try:
            with open(freq_path, "r") as f:
                per_core.append(round(int(f.read().strip()) / 1000.0, 1))  # kHz -> MHz
        except (FileNotFoundError, ValueError):
            continue
    if not per_core:
        return None
    return {
        "per_core": per_core,
        "avg": round(sum(per_core) / len(per_core), 1),
    }


def _read_cpu_jiffies():
    """Compteurs (idle, total) par cœur depuis /proc/stat."""
    stats = {}
    with open(f"{HOST_PROC}/stat", "r") as f:
        for line in f:
            if not line.startswith("cpu") or line[3] == " ":
                continue  # on ignore la ligne agrégée "cpu "
            parts = line.split()
            values = [int(v) for v in parts[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
            stats[parts[0]] = (idle, sum(values))
    return stats


def _read_cpu_load_percent(interval=0.1):
    """Charge (%) de chaque cœur mesurée sur un court intervalle."""
    first = _read_cpu_jiffies()
    time.sleep(interval)
    second = _read_cpu_jiffies()

    per_core = []
    for name in sorted(second, key=lambda n: int(n[3:])):
        if name not in first:
            continue
        idle1, total1 = first[name]
        idle2, total2 = second[name]
        d_total = total2 - total1
        d_idle = idle2 - idle1
        per_core.append(
            round((1.0 - d_idle / d_total) * 100.0, 1) if d_total > 0 else 0.0
        )
    if not per_core:
        return None
    return {
        "per_core": per_core,
        "avg": round(sum(per_core) / len(per_core), 1),
    }


def _safe(name, func):
    """Exécute une lecture de métrique, renvoie None et loggue en cas d'erreur."""
    try:
        return func()
    except Exception as e:
        print(f"[{DEVICE_NAME}] Erreur lecture {name}: {e}")
        return None


@app.get("/metrics/temperature")
def get_temperature():
    """Métriques système du Raspberry Pi : température CPU, RAM utilisée,
    fréquence et charge des cœurs du CPU."""
    return {
        "device": DEVICE_NAME,
        "temperature_c": _safe("température", _read_temperature_c),
        "ram_used_percent": _safe("RAM", _read_ram_used_percent),
        "cpu_freq_mhz": _safe("fréquence CPU", _read_cpu_freq_mhz),
        "cpu_load_percent": _safe("charge CPU", _read_cpu_load_percent),
    }


@app.post("/ollama/generate")
def generate_text(req: OllamaRequest):
    """Relais vers Ollama local en /api/generate.

    Si `stream` est vrai, la réponse est renvoyée au fil de l'eau en NDJSON
    (une ligne JSON par fragment, telle que produite par Ollama)."""
    model = req.model or OLLAMA_MODEL
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": req.prompt,
        "stream": req.stream,
    }

    if req.stream:
        try:
            upstream = requests.post(url, json=payload, timeout=300, stream=True)
            upstream.raise_for_status()
        except Exception as e:
            print(f"[{DEVICE_NAME}] Erreur appel Ollama: {e}")
            raise HTTPException(status_code=502, detail="Erreur lors de l'appel à Ollama")

        def iter_chunks():
            try:
                # chunk_size=None : on ne bufferise pas, chaque token d'Ollama
                # est relayé dès sa réception (sinon ~512 o de buffer -> stream saccadé).
                for line in upstream.iter_lines(decode_unicode=True, chunk_size=None):
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue
                    out = {
                        "device": DEVICE_NAME,
                        "model": model,
                        "response": chunk.get("response", ""),
                        "done": chunk.get("done", False),
                    }
                    if chunk.get("done"):
                        out["eval_count"] = chunk.get("eval_count")
                        out["prompt_eval_count"] = chunk.get("prompt_eval_count")
                    yield json.dumps(out, ensure_ascii=False) + "\n"
            finally:
                upstream.close()

        return StreamingResponse(
            iter_chunks(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

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

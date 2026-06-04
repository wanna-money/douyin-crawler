import os
import random
import string
import subprocess
import time
import httpx
from pathlib import Path
from urllib.parse import urlencode

_AB_SERVER_PORT = 18686
_AB_SERVER_URL = f"http://127.0.0.1:{_AB_SERVER_PORT}"
_AB_SERVER_JS = Path(__file__).parent.parent.parent / "ab_server.js"
_NODE_MODULES = Path(__file__).parent.parent.parent / "node_modules"

_server_proc = None


def _ensure_server():
    global _server_proc
    try:
        httpx.get(_AB_SERVER_URL, timeout=1)
        return
    except Exception:
        pass
    env = os.environ.copy()
    env["NODE_PATH"] = str(_NODE_MODULES)
    _server_proc = subprocess.Popen(
        ["node", str(_AB_SERVER_JS)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(_AB_SERVER_JS.parent),
    )
    for _ in range(20):
        time.sleep(0.3)
        try:
            httpx.get(_AB_SERVER_URL, timeout=0.5)
            return
        except Exception:
            continue
    raise RuntimeError("ab_server 启动失败")


def generate_ms_token(length: int = 107) -> str:
    chars = string.ascii_letters + string.digits + "="
    return "".join(random.choices(chars, k=length))


def generate_a_bogus(params: dict) -> str:
    _ensure_server()
    query = urlencode(params, doseq=True)
    resp = httpx.post(_AB_SERVER_URL, json={"query": query, "data": ""}, timeout=10)
    return resp.json()["a_bogus"]


def sign_params(params: dict) -> dict:
    signed = dict(params)
    signed["msToken"] = generate_ms_token()
    signed["a_bogus"] = generate_a_bogus(signed)
    return signed

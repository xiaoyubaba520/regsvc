#!/usr/bin/env python3
"""registry：200 + Location 同时给"""
import hashlib
import json
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

MANIFEST = {
    "schemaVersion": 2,
    "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
    "config": {
        "mediaType": "application/vnd.docker.container.image.v1+json",
        "digest": "sha256:" + H_CONFIG,
        "size": len(CONFIG_BLOB),
    },
    "layers": [{
        "mediaType": "application/vnd.ollama.image.model",
        "digest": "sha256:" + H_MODEL,
        "size": len(MODEL_BLOB),
    }],
}


@app.middleware("http")
async def mw(request: Request, call_next):
    LOGS.append({"m": request.method, "p": request.url.path[:120]})
    if len(LOGS) > 300:
        del LOGS[:80]
    return await call_next(request)


@app.get("/logs")
def logs():
    return {"n": len(LOGS), "logs": LOGS[-80:]}


@app.get("/v2/")
def v2():
    return Response(status_code=200,
                    headers={"Docker-Distribution-Api-Version": "registry/2.0"})


@app.api_route("/v2/{ns}/{repo}/manifests/{tag}", methods=["GET", "HEAD"])
def manifest(ns: str, repo: str, tag: str, request: Request):
    body = json.dumps(MANIFEST)
    dg = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    hdr = {
        "Docker-Content-Digest": dg,
        "Content-Length": str(len(body)),
        "Location": BASE + "/v2/" + ns + "/" + repo + "/manifests/" + dg,
    }
    if request.method == "HEAD":
        return Response(status_code=200,
                        media_type="application/vnd.docker.distribution.manifest.v2+json",
                        headers=hdr)
    return Response(content=body,
                    media_type="application/vnd.docker.distribution.manifest.v2+json",
                    headers=hdr)


@app.api_route("/v2/{ns}/{repo}/blobs/{digest:path}", methods=["GET", "HEAD"])
def blob(ns: str, repo: str, digest: str, request: Request):
    key = digest.replace("sha256:", "").split("/")[-1]
    data = BLOBS.get(key) or MODEL_BLOB
    hdr = {
        "Content-Length": str(len(data)),
        "Location": BASE + "/content/" + key,
        "Docker-Content-Digest": "sha256:" + key,
        "Accept-Ranges": "bytes",
    }
    if request.method == "HEAD":
        return Response(status_code=200, headers=hdr)
    return Response(content=data, media_type="application/octet-stream", headers=hdr)


@app.api_route("/content/{key}", methods=["GET", "HEAD"])
def content(key: str, request: Request):
    data = BLOBS.get(key) or MODEL_BLOB
    hdr = {
        "Content-Length": str(len(data)),
        "Location": BASE + "/content/" + key,
        "Accept-Ranges": "bytes",
    }
    if request.method == "HEAD":
        return Response(status_code=200, headers=hdr)
    return Response(content=data, media_type="application/octet-stream", headers=hdr)

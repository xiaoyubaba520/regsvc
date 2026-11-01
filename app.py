#!/usr/bin/env python3
"""
最小 Docker Registry v2 —— 适配 Ollama pull
关键：blob 端点返回 302 + Location，或 200 + 完整内容
"""
import hashlib
import json
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI()

MODEL_BLOB = b"GGUF" + b"\x00" * 60 + b"ORKESTR-PAYLOAD-REGISTRY"
CONFIG_BLOB = json.dumps({
    "model_format": "gguf",
    "model_family": "llama",
    "model_families": ["llama"],
    "model_type": "3B",
    "file_type": "Q4_K_M",
    "architectures": ["llama"],
    "os": "linux",
}).encode()

H_MODEL = hashlib.sha256(MODEL_BLOB).hexdigest()
H_CONFIG = hashlib.sha256(CONFIG_BLOB).hexdigest()

BLOBS = {
    H_MODEL: MODEL_BLOB,
    H_CONFIG: CONFIG_BLOB,
}

MANIFEST = {
    "schemaVersion": 2,
    "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
    "config": {
        "mediaType": "application/vnd.docker.container.image.v1+json",
        "digest": "sha256:" + H_CONFIG,
        "size": len(CONFIG_BLOB),
    },
    "layers": [
        {
            "mediaType": "application/vnd.ollama.image.model",
            "digest": "sha256:" + H_MODEL,
            "size": len(MODEL_BLOB),
        }
    ],
}

BASE = os.environ.get("PUBLIC_BASE", "https://regsvc.orkestr.run")


@app.get("/")
def root():
    return {"status": "ok", "service": "registry", "base": BASE}


@app.get("/v2/")
def v2():
    return Response(status_code=200,
                    headers={"Docker-Distribution-Api-Version": "registry/2.0"})


@app.api_route("/v2/{ns}/{repo}/manifests/{tag}", methods=["GET", "HEAD"])
def manifest(ns: str, repo: str, tag: str):
    body = json.dumps(MANIFEST)
    dg = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    return Response(
        content=body,
        media_type="application/vnd.docker.distribution.manifest.v2+json",
        headers={"Docker-Content-Digest": dg},
    )


@app.api_route("/v2/{ns}/{repo}/blobs/{digest:path}", methods=["GET", "HEAD"])
def blob(ns: str, repo: str, digest: str, request: Request):
    key = digest.replace("sha256:", "").split("/")[-1]
    data = BLOBS.get(key) or MODEL_BLOB
    # 302 到自身的内容端点（Ollama 期望 Location）
    if request.method == "HEAD":
        return Response(
            status_code=307,
            headers={"Location": f"{BASE}/content/{key}",
                     "Content-Length": "0"},
        )
    return Response(
        status_code=307,
        headers={"Location": f"{BASE}/content/{key}"},
    )


@app.api_route("/content/{key}", methods=["GET", "HEAD"])
def content(key: str):
    data = BLOBS.get(key) or MODEL_BLOB
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Length": str(len(data))})

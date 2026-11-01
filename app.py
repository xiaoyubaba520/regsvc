#!/usr/bin/env python3
"""
最小 Docker Registry v2 实现，供 Ollama pull 使用。
支持路径穿越 digest 原样返回（不校验），用于验证 CVE-2024-37032 类问题。
"""
import hashlib
import json
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI()

MODEL_BLOB = b'GGUF\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00ORKESTR-PAYLOAD-REGISTRY'
CONFIG_BLOB = b'{"model_format": "gguf", "model_family": "llama", "model_families": ["llama"], "model_type": "3B", "file_type": "Q4_K_M", "architectures": ["llama"], "os": "linux"}'
MANIFEST = {'schemaVersion': 2, 'mediaType': 'application/vnd.docker.distribution.manifest.v2+json', 'config': {'mediaType': 'application/vnd.docker.container.image.v1+json', 'digest': 'sha256:573a5769e9b4a915c085f5f3b8ddb80f2165ca48952436d8f6dcd4d712920a88', 'size': 164}, 'layers': [{'mediaType': 'application/vnd.ollama.image.model', 'digest': 'sha256:640910e6d528136f879a4f2f4b1109f28952a87499f01344f0ee5bc3af62926c', 'size': 88}]}

BLOBS = {
    hashlib.sha256(MODEL_BLOB).hexdigest(): MODEL_BLOB,
    hashlib.sha256(CONFIG_BLOB).hexdigest(): CONFIG_BLOB,
}


@app.get("/")
def root():
    return {"status": "ok", "service": "registry"}


@app.get("/v2/")
def v2():
    return Response(status_code=200, headers={"Docker-Distribution-Api-Version": "registry/2.0"})


@app.get("/v2/{ns}/{repo}/manifests/{tag}")
def manifest(ns: str, repo: str, tag: str):
    body = json.dumps(MANIFEST)
    return Response(
        content=body,
        media_type="application/vnd.docker.distribution.manifest.v2+json",
        headers={"Docker-Content-Digest": "sha256:" + hashlib.sha256(body.encode()).hexdigest()},
    )


@app.head("/v2/{ns}/{repo}/blobs/{digest}")
def blob_head(ns: str, repo: str, digest: str):
    key = digest.replace("sha256:", "")
    if key in BLOBS:
        return Response(status_code=200, headers={"Content-Length": str(len(BLOBS[key]))})
    return Response(status_code=404)


@app.get("/v2/{ns}/{repo}/blobs/{digest:path}")
def blob(ns: str, repo: str, digest: str):
    # 原样记录请求的 digest，便于观察穿越尝试
    key = digest.replace("sha256:", "").split("/")[-1]
    if key in BLOBS:
        return Response(content=BLOBS[key], media_type="application/octet-stream")
    # 未知 digest 也返回内容，便于测试穿越是否被请求
    return Response(content=MODEL_BLOB, media_type="application/octet-stream")

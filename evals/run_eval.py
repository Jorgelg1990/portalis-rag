"""Retrieval eval runner (stdlib only).

Uploads the sample PDF, waits for ingestion, asks every question in
questions.json and checks retrieval + evidence gating.

Usage:
    python evals/run_eval.py
    python evals/run_eval.py --base-url http://localhost:8000
"""

import argparse
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))


def normalise(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def upload(url: str, path: str, workspace_id: str) -> dict:
    boundary = f"----eval{uuid.uuid4().hex}"
    filename = os.path.basename(path)
    with open(path, "rb") as handle:
        content = handle.read()

    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += content + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="workspace_id"\r\n\r\n'
    body += workspace_id.encode() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    request = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def wait_until_ready(base_url: str, document_id: str, workspace_id: str, timeout: int = 300) -> str:
    deadline = time.time() + timeout
    status = "pendiente"
    while time.time() < deadline:
        payload = get_json(
            f"{base_url}/api/documents/status/{document_id}?workspace_id={workspace_id}"
        )
        status = payload["status"]
        if status in {"listo", "fallido"}:
            return status
        time.sleep(2)
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--workspace", default="eval")
    parser.add_argument("--file", default=os.path.join(HERE, "manual-aduanas.pdf"))
    parser.add_argument("--questions", default=os.path.join(HERE, "questions.json"))
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    print(f"Subiendo {args.file} (workspace={args.workspace})...")
    uploaded = upload(f"{base}/api/documents/upload", args.file, args.workspace)
    document_id = uploaded["document_id"]
    print(f"  document_id={document_id} status={uploaded['status']}")

    status = wait_until_ready(base, document_id, args.workspace)
    if status != "listo":
        print(f"ERROR: la ingesta terminó en estado '{status}'")
        return 1
    print("  ingesta completada: listo\n")

    with open(args.questions, encoding="utf-8") as handle:
        questions = json.load(handle)

    failures = 0

    # Tenant isolation: the same question in another workspace must not see
    # this document's fragments.
    iso = post_json(
        f"{base}/api/query",
        {"question": questions[0]["question"], "workspace_id": "default", "top_k": 4},
    )
    iso_ok = iso["insufficient_evidence"] is True and iso["citations"] == []
    if not iso_ok:
        failures += 1
    print(
        f"[{'PASS' if iso_ok else 'FAIL'}] aislamiento por workspace: "
        f"otro workspace no recupera fragmentos (action={iso['action']})"
    )

    for item in questions:
        result = post_json(
            f"{base}/api/query",
            {"question": item["question"], "workspace_id": args.workspace, "top_k": 4},
        )
        haystack = normalise(
            result["answer"] + " " + " ".join(c["snippet"] for c in result["citations"])
        )

        if item["should_find"]:
            hits = [kw for kw in item["expected_keywords"] if normalise(kw) in haystack]
            passed = (
                result["action"] == "answer"
                and not result["insufficient_evidence"]
                and len(hits) > 0
                and len(result["citations"]) > 0
            )
            detail = f"keywords={hits}/{item['expected_keywords']}"
        else:
            passed = result["insufficient_evidence"] is True and result["action"] in {
                "abstain",
                "ask_clarification",
            }
            detail = f"action={result['action']} insufficient={result['insufficient_evidence']}"

        if not passed:
            failures += 1
        print(
            f"[{'PASS' if passed else 'FAIL'}] #{item['id']} {item['question']}\n"
            f"       action={result['action']} conf={result['confidence']:.2f} "
            f"citations={len(result['citations'])} frags={result['fragments_retrieved']} {detail}"
        )

    total = len(questions) + 1
    print(f"\nResultado: {total - failures}/{total} comprobaciones correctas")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as exc:
        print(f"No se pudo conectar con la API: {exc}")
        sys.exit(2)

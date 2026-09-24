"""The REACH half of the reference client (starting-point doc §6.3).

A generic client speaking to declared entry points: POST a task bundle to an
http-json interface, hold a chat thread against an openai-compatible one
(client-held, stateless Cog turns — §6.6), probe health. No Cog-specific code
anywhere in this module; every place the portable contract forced a guess is
tagged with a gap note.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

# Keys the current de facto envelope uses around the payload. A generic client
# should not need this list — that it does is gap #1 in DECISIONS.md's scorecard.
ENVELOPE_KEYS = {"raw", "problems", "binding", "latency_s", "error", "detail"}


def _post_json(url, body, timeout=180, api_key=None):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
            return resp.status, payload, round(time.monotonic() - started, 3), None
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {"error": "non-json-error-body"}
        return e.code, payload, round(time.monotonic() - started, 3), None
    except Exception as e:
        return None, None, round(time.monotonic() - started, 3), repr(e)


def invoke_task(endpoint, bundle, timeout=180):
    """Invoke a task-shaped Cog through its declared http-json entry point and
    interpret the response as a generic client must: heuristically."""
    status, payload, elapsed, transport_error = _post_json(endpoint, bundle, timeout)
    gaps = []
    if transport_error:
        return {"ok": False, "status": None, "transport_error": transport_error,
                "elapsed_s": elapsed, "gaps": gaps}

    payload_key = None
    result_payload = None
    if isinstance(payload, dict):
        candidates = [k for k in payload.keys() if k not in ENVELOPE_KEYS]
        if len(candidates) == 1:
            payload_key = candidates[0]
        elif candidates:
            payload_key = candidates[0]
            gaps.append(f"multiple non-envelope keys {candidates}; picked {payload_key!r} "
                        f"arbitrarily — no envelope contract")
        if payload_key:
            result_payload = payload.get(payload_key)
            gaps.append(f"payload key {payload_key!r} discovered heuristically — the "
                        f"response envelope is not a published contract")

    problems = payload.get("problems") if isinstance(payload, dict) else None
    if status == 200 and problems:
        gaps.append("HTTP 200 carried integrity problems — no machine rule says "
                    "whether this run 'passed'")

    return {
        "ok": status == 200 and not (isinstance(payload, dict) and payload.get("error")),
        "status": status,
        "error": payload.get("error") if isinstance(payload, dict) else None,
        "detail": payload.get("detail") if isinstance(payload, dict) else None,
        "payload_key": payload_key,
        "payload": result_payload,
        "problems": problems or [],
        "binding": payload.get("binding") if isinstance(payload, dict) else None,
        "latency_s": (payload.get("latency_s") if isinstance(payload, dict) else None),
        "elapsed_s": elapsed,
        "raw_envelope": payload,
        "gaps": gaps,
    }


def chat_turn(endpoint, messages, model=None, api_key_env=None, timeout=180):
    """One stateless chat turn against an openai-compatible entry point.

    The THREAD IS CLIENT-HELD (§6.6): the caller owns `messages` and sends the
    whole history every turn; the Cog stays an installable package, and every
    turn is an individually attributable invocation.
    """
    base = str(endpoint or "").rstrip("/")
    url = base + "/chat/completions"
    api_key = os.environ.get(api_key_env, "") if api_key_env else None
    body = {"messages": messages}
    if model:
        body["model"] = model
    status, payload, elapsed, transport_error = _post_json(url, body, timeout,
                                                           api_key=api_key)
    if transport_error:
        return {"ok": False, "transport_error": transport_error, "elapsed_s": elapsed}
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "error": "malformed provider payload",
                "raw": payload, "elapsed_s": elapsed, "status": status}
    return {"ok": status == 200, "status": status, "text": text,
            "model_echoed": payload.get("model"), "elapsed_s": elapsed}


def health(url, timeout=5):
    """Probe a health URL (a Cog api's /health, or a model endpoint's /models)."""
    for probe in ([url] if url else []):
        try:
            with urllib.request.urlopen(probe, timeout=timeout) as resp:
                body = resp.read().decode(errors="replace")[:500]
                try:
                    body = json.loads(body)
                except Exception:
                    pass
                return {"ok": resp.status == 200, "status": resp.status, "body": body}
        except Exception as e:
            return {"ok": False, "error": repr(e)}
    return {"ok": False, "error": "no health url"}


def model_health(endpoint, timeout=5):
    """Shallow probe of an openai-compatible endpoint (/models)."""
    base = str(endpoint or "").rstrip("/")
    return health(base + "/models", timeout)


def redact_endpoint(url):
    """Belt-and-braces: never display credential-bearing URLs."""
    return re.sub(r"//[^/@]+@", "//", str(url or ""))

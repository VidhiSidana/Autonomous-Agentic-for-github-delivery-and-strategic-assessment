#!/usr/bin/env python3
"""
Samsung PRISM Engineering Agent - LLM Endpoint Health & Zero-Egress Checker.

Validates:
1. Endpoint reachability (/api/tags)
2. Model availability and tags
3. Test generation (/api/generate) with round-trip latency
4. Localhost / Internal IP validation (Zero-Egress network compliance)
"""

import argparse
import ipaddress
import json
import socket
import sys
import time
import urllib.parse
import urllib.request


def is_local_or_private_endpoint(url: str) -> Tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or "localhost"
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return True, f"Localhost endpoint ({hostname})"
    
    try:
        resolved_ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(resolved_ip)
        if ip_obj.is_private or ip_obj.is_loopback:
            return True, f"Private / On-premise IP ({resolved_ip})"
        else:
            return False, f"PUBLIC IP ({resolved_ip}) violates Zero-Egress policy"
    except Exception as e:
        return False, f"Failed to resolve host '{hostname}': {e}"


def check_endpoint(endpoint: str, model: str, timeout: int = 15) -> bool:
    print(f"=== Checking LLM Endpoint: {endpoint} ===")
    
    # Check 1: Zero-Egress / Host compliance
    is_safe, reason = is_local_or_private_endpoint(endpoint)
    if not is_safe:
        print(f"[FAIL] Zero-Egress Policy Violation: {reason}")
        return False
    print(f"[PASS] Zero-Egress Verification: {reason}")

    # Check 2: Endpoint Tags / Health
    tags_url = endpoint.rstrip("/") + "/api/tags"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(tags_url, headers={"User-Agent": "prism-agent-healthcheck"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tags_latency = time.perf_counter() - t0
            print(f"[PASS] Connected to /api/tags in {tags_latency:.3f}s")
    except Exception as e:
        print(f"[FAIL] Unable to connect to {tags_url}: {e}")
        return False

    models_list = [m.get("name", "") for m in data.get("models", [])]
    print(f"[INFO] Available models ({len(models_list)}): {', '.join(models_list)}")
    
    # Check 3: Requested model presence
    matched = False
    for m in models_list:
        if m == model or m.startswith(model + ":") or (":" not in model and m.startswith(model)):
            matched = True
            model = m
            break
            
    if not matched:
        print(f"[FAIL] Requested model '{model}' not found in endpoint models list.")
        return False
    print(f"[PASS] Model '{model}' is present.")

    # Check 4: Test generation
    gen_url = endpoint.rstrip("/") + "/api/generate"
    gen_payload = json.dumps({
        "model": model,
        "prompt": "Respond with the single word: OK",
        "stream": False,
        "options": {
            "num_predict": 16,
            "temperature": 0.0,
        }
    }).encode("utf-8")

    t1 = time.perf_counter()
    try:
        req = urllib.request.Request(
            gen_url,
            data=gen_payload,
            headers={"Content-Type": "application/json", "User-Agent": "prism-agent-healthcheck"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            gen_latency = time.perf_counter() - t1
            response_text = res_json.get("response", "").strip()
            eval_count = res_json.get("eval_count", 0)
            print(f"[PASS] Generation test succeeded in {gen_latency:.3f}s (eval_count={eval_count} tokens)")
            print(f"       Response snippet: '{response_text[:40]}'")
    except Exception as e:
        print(f"[FAIL] Generation test failed at {gen_url}: {e}")
        return False

    print("\n[SUMMARY] All LLM endpoint health checks PASSED.")
    return True


if __name__ == "__main__":
    from typing import Tuple
    parser = argparse.ArgumentParser(description="Check LLM Endpoint Health & Policy Compliance")
    parser.add_argument("--endpoint", default="http://localhost:11434", help="Ollama / OpenAI-compatible endpoint URL")
    parser.add_argument("--model", default="qwen2.5:1.5b", help="Model name or tag to test")
    parser.add_argument("--timeout", type=int, default=15, help="Request timeout in seconds")
    args = parser.parse_args()

    success = check_endpoint(args.endpoint, args.model, args.timeout)
    sys.exit(0 if success else 1)


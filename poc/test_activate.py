#!/usr/bin/env python3
"""Test script: POST a TMF640 mobile service activation to the live server."""
import json, urllib.request, time, sys

payload = {
    "prompt": '{"serviceId":"MSISDN-VAR_MSISDN_1","action":"activate","characteristic":[{"name":"customerSegment","value":"retail"},{"name":"slaTier","value":"gold"},{"name":"productId","value":"mobile-voice"},{"name":"msisdn","value":"VAR_MSISDN_1"},{"name":"imsi","value":"VAR_MSISDN_2"}]}'
}

# POST to /api/process
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8090/api/process",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read().decode())

print("=== INITIAL RESPONSE ===")
print(json.dumps(result, indent=2))
order_id = result.get("order_id", "")
if not order_id:
    print("ERROR: no order_id")
    sys.exit(1)

print("\n=== POLLING ===")
for i in range(30):
    time.sleep(2)
    req2 = urllib.request.Request(f"http://127.0.0.1:8090/api/process/{order_id}")
    with urllib.request.urlopen(req2, timeout=5) as resp:
        poll = json.loads(resp.read().decode())
    status = poll.get("status", "")
    trace_count = len(poll.get("trace", []))
    print(f"  poll {i+1}: status={status}, trace_steps={trace_count}")
    if status in ("completed", "blocked", "error"):
        print("\n=== FINAL RESULT ===")
        print(json.dumps(poll, indent=2))
        break
else:
    print("\n=== TIMED OUT - partial result ===")

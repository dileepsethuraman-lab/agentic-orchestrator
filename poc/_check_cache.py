import json, hashlib, diskcache

request = {
    "serviceId": "MSISDN-VAR_MSISDN_1",
    "action": "activate",
    "characteristic": [
        {"name": "customerSegment", "value": "retail"},
        {"name": "slaTier", "value": "bronze"},
        {"name": "productId", "value": "mobile-voice"},
        {"name": "msisdn", "value": "VAR_MSISDN_1"},
        {"name": "imsi", "value": "VAR_MSISDN_2"}
    ]
}
key_str = json.dumps(request, sort_keys=True)
cache_key = f"orch:plan:{hashlib.sha256(key_str.encode()).hexdigest()[:16]}"

cache = diskcache.Cache("/opt/data/telecom-orchestrator/cache")
value = cache.get(cache_key)
print(f"CACHE_KEY: {cache_key}")
print(f"CACHE_HIT: {value is not None}")
if value:
    if isinstance(value, dict):
        print(f"VALUE_KEYS: {list(value.keys())}")
        print(f"WORKFLOWS: {value.get('workflows', 'N/A')}")
    else:
        print(f"VALUE (str): {str(value)[:300]}")

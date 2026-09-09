import requests
import json

agents = ['soros', 'buffett', 'druckenmiller', 'tudor-jones', 'lynch']
all_ok = True

# Individual agents
for a in agents:
    r = requests.get(f'http://localhost:8001/api/v1/legendary/{a}/EURUSD', timeout=15)
    if r.status_code == 200:
        d = r.json()
        print(f'  [OK] {a}: {d["signal"]} (confidence={d["confidence"]})')
    else:
        print(f'  [XX] {a}: HTTP {r.status_code} - {r.text[:100]}')
        all_ok = False

# Combined analyze endpoint
r = requests.get('http://localhost:8001/api/v1/legendary/analyze/EURUSD', timeout=15)
if r.status_code == 200:
    d = r.json()
    print(f'\n  Combined consensus: {d["consensus"]} (buy={d["buy_votes"]}, sell={d["sell_votes"]}, hold={d["hold_votes"]})')
else:
    print(f'\n  [XX] Combined: HTTP {r.status_code} - {r.text[:100]}')
    all_ok = False

# Agents list
r = requests.get('http://localhost:8001/api/v1/legendary/agents', timeout=15)
if r.status_code == 200:
    d = r.json()
    print(f'  Agent count: {d["count"]}')
else:
    print(f'  [XX] Agent list: HTTP {r.status_code}')

# Existing modules
for m in ['seykota', 'turtle-soup', 'pyramiding']:
    r = requests.get(f'http://localhost:8001/api/v1/legendary/{m}/EURUSD', timeout=15)
    print(f'  {"[OK]" if r.status_code == 200 else "[XX]"} {m}: HTTP {r.status_code}')

print(f'\n  {"ALL PASSED" if all_ok else "SOME FAILED"}')

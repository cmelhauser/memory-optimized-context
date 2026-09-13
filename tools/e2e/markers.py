"""Exit 0 if each of the 160 turns of the fixture's long transcript reached the Reflector in exactly
one call. Usage: markers.py LOGFILE (a JSON line per call, with its prompt)."""
import json
import sys

prompts = [json.loads(line)["prompt"] for line in open(sys.argv[1])]
seen = [sum(f"M{i:03d} " in p for p in prompts) for i in range(160)]
carrying = sum(any(f"M{i:03d} " in p for i in range(160)) for p in prompts)
bad = [i for i, n in enumerate(seen) if n != 1]
print(f"     {len(prompts)} Reflector calls, {carrying} carried transcript turns; turns missing or repeated: {bad[:5]}")
sys.exit(1 if bad or carrying < 4 else 0)

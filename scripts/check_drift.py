import json
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "rebrief.cli", "scan", ".", "-f", "json", "-o", "-"],
    capture_output=True,
    text=True,
    cwd=".",
)
text = result.stdout
start = text.find("{")
payload = json.loads(text[start:])
drift = payload["summary"]["doc_drift"]
print(f"Score: {drift['freshness_score']}% ({drift['freshness_label']})")
print(f"Components: {drift['components']}")
print(f"Items: {len(drift['items'])}")
for kind in ("path", "stack", "env"):
    items = [i for i in drift["items"] if i["kind"] == kind]
    print(f"\n{kind.upper()} ({len(items)}):")
    for item in items[:20]:
        print(f"  [{item['severity']}] {item['message'][:120]}")
    if len(items) > 20:
        print(f"  ... and {len(items) - 20} more")

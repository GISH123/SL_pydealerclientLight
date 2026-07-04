import pathlib

for f in pathlib.Path(".").rglob("*.py"):
    with open(f, "r", encoding="utf-8", errors="ignore") as fp:
        for i, line in enumerate(fp, 1):
            if any(ord(c) > 127 for c in line):
                print(f"{f}:{i}: {line.strip()}")
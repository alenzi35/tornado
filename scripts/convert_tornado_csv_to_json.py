import csv
import json
import os

INPUT = "data/tornado_samples.csv"
OUTPUT = "data/tornado_samples.json"

samples = []

with open(INPUT, newline="") as f:
    reader = csv.DictReader(f)

    for row in reader:
        sample = {
            "mlcape": float(row["mlcape"]),
            "mlcin": float(row["mlcin"]),
            "srh01": float(row["srh01"])
        }
        samples.append(sample)

print(f"Loaded {len(samples)} tornado samples")

os.makedirs("data", exist_ok=True)

with open(OUTPUT, "w") as f:
    json.dump(samples, f)

print(f"Saved → {OUTPUT}")

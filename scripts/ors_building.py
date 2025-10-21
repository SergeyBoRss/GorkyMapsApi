import time
import argparse
import sys
from pathlib import Path
import pandas as pd
import requests
from tqdm import tqdm

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils.config import ORS_KEY

API_URL = "https://api.openrouteservice.org/v2/matrix/foot-walking"
BATCH_LIMIT = 59


def load_points(csv_path: str):
    df = pd.read_csv(csv_path)

    required = ["id", "lon", "lat"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    ids = df["id"].astype(str).tolist()
    coords = df[["lon", "lat"]].astype(float).values.tolist()
    return ids, coords


def build_matrix(coords):
    n = len(coords)
    result = [[None] * n for _ in range(n)]

    for i0 in tqdm(range(0, n, BATCH_LIMIT), desc="rows"):
        sub_i = coords[i0 : i0 + BATCH_LIMIT]
        for j0 in range(0, n, BATCH_LIMIT):
            sub_j = coords[j0 : j0 + BATCH_LIMIT]

            locations = sub_i + sub_j
            sources = list(range(0, len(sub_i)))
            destinations = list(range(len(sub_i), len(sub_i) + len(sub_j)))

            body = {
                "locations": locations,
                "destinations": destinations,
                "sources": sources,
                "metrics": ["duration"],
            }

            headers = {
                "Authorization": ORS_KEY,
                "Content-Type": "application/json",
            }

            resp = requests.post(API_URL, headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"ORS error {resp.status_code}: {resp.text}")

            durations = resp.json()["durations"]
            for ii, row in enumerate(durations):
                for jj, val in enumerate(row):
                    result[i0 + ii][j0 + jj] = val
            time.sleep(1)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Input CSV with lon/lat")
    ap.add_argument("--out", default="duration_s.csv", help="Output file name")
    args = ap.parse_args()

    if ORS_KEY is None:
        raise EnvironmentError("Set ORS_KEY environment variable first!")

    ids, coords = load_points(args.csv)
    print(f"Loaded {len(coords)} points from {args.csv}")

    matrix = build_matrix(coords)

    out_df = pd.DataFrame(matrix, index=ids, columns=ids)
    out_df.to_csv(args.out, float_format="%.1f")

    print(f"Duration matrix saved to {args.out}")


if __name__ == "__main__":
    main()

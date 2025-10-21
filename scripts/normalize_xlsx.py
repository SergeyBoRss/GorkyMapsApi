import argparse
import pathlib
import pandas as pd
import re
import sys

WKT_RE = r"POINT\s*\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Путь к XLSX/CSV")
    ap.add_argument("--sheet", default="cultural_sites_202509191434", help="Имя листа Excel")
    ap.add_argument("--output", required=True, help="Путь к points.csv")
    args = ap.parse_args()

    in_path = pathlib.Path(args.input)
    out_csv = pathlib.Path(args.output)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if in_path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(in_path, sheet_name=args.sheet)
    else:
        df = pd.read_csv(in_path)

    expected = [
        "id",
        "address",
        "coordinate",
        "description",
        "title",
        "category_id",
        "url",
        "time",
        "tag"
    ]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        print(f"[error] Нет обязательных колонок: {missing}", file=sys.stderr)
        sys.exit(2)

    lonlat = df["coordinate"].astype(str).str.extract(WKT_RE, flags=re.IGNORECASE)
    lonlat.columns = ["lon", "lat"]
    lonlat = lonlat.astype(float)

    valid = lonlat["lon"].between(-180.0, 180.0) & lonlat["lat"].between(-90.0, 90.0)

    out = (
        pd.DataFrame(
            {
                "id": df["id"],
                "title": df["title"],
                "address": df["address"],
                "description": df["description"],
                "category_id": df["category_id"],
                "url": df["url"],
                "lon": lonlat["lon"],
                "lat": lonlat["lat"],
                "time": df["time"],
                "tag": df["tag"],
            }
        )[valid]
        .drop_duplicates(subset=["id"])
        .reset_index(drop=True)
    )

    out.to_csv(out_csv, index=False)

    print(f"[ok] rows: {len(out)} -> {out_csv}")


if __name__ == "__main__":
    main()

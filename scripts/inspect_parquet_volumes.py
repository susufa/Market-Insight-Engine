"""
Inspect all parquet files in data/production/CN_A/1d:
- check rows, columns, source interfaces
- check volume unit ratio: amount / (volume * close)
"""
from pathlib import Path
import pyarrow.parquet as pq

def main():
    p_dir = Path("data/production/CN_A/1d")
    print("Inspecting Parquet files in:", p_dir)
    for p in sorted(p_dir.glob("*.parquet")):
        df = pq.read_table(p).to_pandas()
        vwap_ratio = (df["amount"] / (df["volume"] * df["close"])).mean()
        sources = df["source_interface"].unique().tolist() if "source_interface" in df.columns else ["N/A"]
        min_v = df["volume"].min()
        max_v = df["volume"].max()
        print(f"File: {p.name}")
        print(f"  Rows: {len(df)}")
        print(f"  Sources: {sources}")
        print(f"  VWAP Ratio (amount / (volume*close)): {vwap_ratio:.4f}")
        print(f"  Volume Range: [{min_v:,.0f}, {max_v:,.0f}]")
        print(f"  Sample TS: {df['ts'].min()} to {df['ts'].max()}")
        print("-" * 50)

if __name__ == "__main__":
    main()

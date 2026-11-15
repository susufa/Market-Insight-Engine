"""
Verify exact columns and values returned by AKShare functions:
- stock_zh_a_hist (EastMoney)
- stock_zh_a_daily (Sina)
- stock_hk_hist (EastMoney HK)
"""
import akshare as ak
import pandas as pd

def test_sources():
    print("Testing ak.stock_zh_a_daily (Sina) for 600519...")
    try:
        df_sina = ak.stock_zh_a_daily(symbol="sh600519", adjust="")
        print("Sina df shape:", df_sina.shape)
        print("Sina columns:", df_sina.columns.tolist())
        latest_sina = df_sina.iloc[-1]
        print("Sina latest row:\n", latest_sina)
        sina_ratio = latest_sina['amount'] / (latest_sina['volume'] * latest_sina['close'])
        print(f"Sina amount / (volume * close) = {sina_ratio:.4f}")
    except Exception as e:
        print("Sina error:", e)

    print("\n" + "="*50 + "\n")
    print("Testing ak.stock_zh_a_hist (EastMoney) for 600519...")
    try:
        df_em = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20231201", end_date="20231229", adjust="")
        print("EastMoney df shape:", df_em.shape)
        print("EastMoney columns:", df_em.columns.tolist())
        latest_em = df_em.iloc[-1]
        print("EastMoney latest row:\n", latest_em)
        em_ratio = latest_em['成交额'] / (latest_em['成交量'] * latest_em['收盘'])
        print(f"EastMoney 成交额 / (成交量 * 收盘) = {em_ratio:.4f}")
    except Exception as e:
        print("EastMoney error:", e)

    print("\n" + "="*50 + "\n")
    print("Testing ak.stock_hk_hist (EastMoney HK) for 00700...")
    try:
        df_hk = ak.stock_hk_hist(symbol="00700", period="daily", start_date="20231201", end_date="20231229", adjust="")
        print("HK df shape:", df_hk.shape)
        print("HK columns:", df_hk.columns.tolist())
        latest_hk = df_hk.iloc[-1]
        print("HK latest row:\n", latest_hk)
        hk_ratio = latest_hk['成交额'] / (latest_hk['成交量'] * latest_hk['收盘'])
        print(f"HK 成交额 / (成交量 * 收盘) = {hk_ratio:.4f}")
    except Exception as e:
        print("HK error:", e)

if __name__ == "__main__":
    test_sources()

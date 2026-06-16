import pickle
import pandas as pd

with open("raw_data_cache.pkl", "rb") as f:
    cache = pickle.load(f)

close_df = cache['close_df']
sma50_matrix = close_df.rolling(window=50, min_periods=30).mean()

print("AAPL close tail:")
print(close_df['AAPL'].tail(15))

print("\nAAPL SMA50 tail with min_periods=30:")
print(sma50_matrix['AAPL'].tail(15))

print("\nNumber of non-NaN values in AAPL SMA50:", sma50_matrix['AAPL'].notna().sum())

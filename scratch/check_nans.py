import pickle
import pandas as pd

with open("raw_data_cache.pkl", "rb") as f:
    cache = pickle.load(f)

close_df = cache['close_df']
print("Original close_df shape:", close_df.shape)
print("NaNs per column in original close_df:")
print(close_df.isna().sum())

df_ffill = close_df.ffill()
print("\nAfter ffill, NaNs per column:")
print(df_ffill.isna().sum())

df_dropna = df_ffill.dropna()
print("\nAfter dropna, shape:", df_dropna.shape)

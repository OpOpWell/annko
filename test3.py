import pandas as pd

df = pd.read_csv(
    "GE-1_出来形.csv",
    encoding="cp932"
)

print(df.columns)

print(df.head())
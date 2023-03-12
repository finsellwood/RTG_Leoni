import pandas as pd
import matplotlib.pyplot as plt

file = pd.read_csv("data/market_data1.csv")
df = pd.DataFrame(file)

df_A = df[df["Side"]=="A"]
df_B = df[df["Side"]=="B"]

df_A_prices = df_A[df_A["Instrument"]==0].groupby(by=["Time"])["Price"].max().to_frame(name="Price").reset_index()
df_B_prices = df_B[df_B["Instrument"]==0].groupby(by=["Time"])["Price"].min().to_frame(name="Price").reset_index()

print(df_A_prices["Time"].is_unique)

plt.plot(df_A_prices["Time"],df_A_prices["Price"])
plt.plot(df_B_prices["Time"],df_B_prices["Price"])

plt.show()


"""
l = [[1, 2, 3],
     [1, None, 4],
     [2, 1, 3],
     [1, 2, 2]]
df = pd.DataFrame(l, columns=["a", "b", "c"])
print(df.groupby(by=["b"])["c"].min())
"""

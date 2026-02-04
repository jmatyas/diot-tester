from matplotlib import pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns

ident = "tektronix_mso4104_c020807"

files = [f"{ident}_chan1.csv"] #, f"{ident}_chan2.csv"]
dfs = [pd.read_csv(f) for f in files]
df = pd.concat(dfs)
sns.lineplot(data=df, x="time", y="voltage", hue="label")
df_grouped = df.groupby("label")
# plt.figure()
print(df.describe())
for label in df_grouped.groups.keys():
    mean_v = df_grouped.get_group(label)["voltage"].mean()
    print(f"Mean voltage for {label}: {mean_v:.3f} V")
    # df.loc[df["label"] == label, "voltage"] -= mean_v


labels = df["label"].unique()

for label in labels:
    spectrum = np.fft.fft(df[df["label"] == label]["voltage"].to_numpy())
    # spectrum = spectrum[:len(spectrum)//2]
    npts = len(spectrum)
    print(df["time"].to_numpy()[1] - df["time"].to_numpy()[0])
    freq = np.fft.fftfreq(npts, d=(df["time"].to_numpy()[1] - df["time"].to_numpy()[0]))
    plt.figure()
    plt.semilogx(freq, 20 * np.log10(np.abs(spectrum)))
    plt.title(f"Spectrum of {label}")

plt.savefig("tst.png")
# plt.show()
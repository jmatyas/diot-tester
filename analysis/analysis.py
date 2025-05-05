import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

DIRECTORY = "results"

file = ""
file_example = "example_measurement.csv"

path = f"analysis/{file_example}" if file == "" else f"../{DIRECTORY}/{file}"

df = pd.read_csv(f"{path}", header=[0])
timestamps = df["elapsed_time"].unique()
powers = df[df["elapsed_time"] == timestamps[0]].groupby("card_serial", dropna=True)[
    "load_power"
]
print(powers.sum())

# ------------------------------------------------------------------------------
sns.set_theme(style="darkgrid", palette="colorblind")

# drop entries with channel == "16"
df_lower_ch_count = df[df["channel"] != 16]

card_serials = df_lower_ch_count["card_serial"].unique()
for card_serial in card_serials:
    card_df = df_lower_ch_count[df_lower_ch_count["card_serial"] == card_serial]
    if any(card_df["steady_state"] == True):
        print(f"Card serial {card_serial} has achieved steady-state...")
        # continue
    plt.figure(figsize=(12, 6))
    sns.lineplot(
        data=card_df,
        x="elapsed_time",
        y="temperature",
        hue="channel",
        palette="colorblind",
    )
    plt.title(f"Temperature vs Time for Card Serial: {card_serial}")
    plt.xlabel("Time")
    plt.ylabel("Temperature")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.grid(True)
plt.show()

# ------------------------------------------------------------------------------
for card_serial in card_serials:
    card_df = df_lower_ch_count[df_lower_ch_count["card_serial"] == card_serial]
    plt.figure(figsize=(12, 6))
    sns.lineplot(
        data=card_df,
        x="elapsed_time",
        y="temp_rate_per_min",
        hue="channel",
        palette="colorblind",
    )
    # sns.lineplot(data=card_df, x="elapsed_time", y="temp_rate_per_min")
    plt.title(f"Temperature Rate per Minute vs Time for Card Serial: {card_serial}")
    plt.xlabel("Time")
    plt.ylabel("Temperature")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.grid(True)
plt.show()

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def extract_slot_temperatures(df):
    """
    Extract max temperature and delta T per slot (up to 9 slots).
    Returns lists: slotnumber, maxtemp_on_slot, delta_t_on_slot, power
    """
    last_time = df["elapsed_time"].max()
    df_steady = df[df["elapsed_time"] == last_time]
    card_serials = df_steady["card_serial"].unique()

    slotnumber = []
    maxtemp_on_slot = []
    delta_t_on_slot = []

    for idx, card in enumerate(card_serials):
        if idx >= 9:
            break

        df_card = df_steady[(df_steady["card_serial"] == card)
                            & (df_steady["channel"] <= 18)]
        df_card_relevant = df_card[df_card["channel"] <= 16] #exclude backplane thermometers
        min_temp = df_card_relevant["temperature"].min()
        max_temp = df_card_relevant["temperature"].max()
        delta_t = max_temp - min_temp

        slotnumber.append(idx)
        maxtemp_on_slot.append(max_temp)
        delta_t_on_slot.append(delta_t)

    power = df_card["load_power"].sum()
    return slotnumber, maxtemp_on_slot, delta_t_on_slot, power


def plot_temperature_metrics(filelist, labels=None):
    """
    Plot two charts (max temperature and ΔT per slot) for multiple CSV files.
    Each line corresponds to one file.
    """
    if labels is None:
        labels = [Path(f).stem for f in filelist]

    plt.figure(figsize=(10, 5))
    for fpath, label in zip(filelist, labels):
        print(f"Processing file: {fpath}")
        df = pd.read_csv(fpath)
        slotnumber, maxtemp_on_slot, delta_t_on_slot, power = extract_slot_temperatures(
            df)
        plt.plot(slotnumber, maxtemp_on_slot, marker='o',
                 label=f'{label} ({power:.1f}W)')
    plt.xlabel("DIOT slot number")
    plt.ylabel("Max temperature [°C]")
    plt.title("Max temperature per slot")
    plt.grid(True)
    plt.legend()
    plt.savefig("Maxtemperatures per slot.png")
    plt.close()

    plt.figure(figsize=(10, 5))
    for fpath, label in zip(filelist, labels):
        df = pd.read_csv(fpath)
        slotnumber, maxtemp_on_slot, delta_t_on_slot, power = extract_slot_temperatures(
            df)
        plt.plot(slotnumber, delta_t_on_slot, marker='o',
                 label=f'{label} ({power:.1f}W)')
    plt.xlabel("DIOT slot number")
    plt.ylabel("ΔT [°C]")
    plt.title("ΔT per slot")
    plt.grid(True)
    plt.legend()
    plt.savefig("DeltaT per slot.png")
    plt.close()


# ======= Main code =======

fpath1 = r'C:\Users\Konrad Norowski\Desktop\DIOT testing\020625\results\SCHROFF\step_0_20W0_20250521_151216.csv'
fpath2 = r'C:\Users\Konrad Norowski\Desktop\DIOT testing\020625\results\CUSTOM_80\step_0_20W0_20250520_181621.csv'
fpath3 = r'C:\Users\Konrad Norowski\Desktop\DIOT testing\020625\results\CUSTOM_100\step_0_20W0_20250527_160236.csv'


filelist = [fpath1, fpath2, fpath3]
labels = ["SCHROFF", "CUSTOM 80", "CUSTOM 100"]  # for legend

plot_temperature_metrics(filelist, labels)

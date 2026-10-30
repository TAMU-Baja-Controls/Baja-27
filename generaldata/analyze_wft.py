import csv
import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
except ImportError:
    print("ERROR: matplotlib is not installed.")
    print("Install it with:")
    print("    py -m pip install matplotlib")
    sys.exit(1)


CHANNELS = [
    "Fx_N", "Fy_N", "Fz_N",
    "Mx_Nm", "My_Nm", "Mz_Nm",
    "Velocity_RPM", "Position_deg",
    "Ax_g", "Ay_g", "Az_g",
]

PLOT_GROUPS = [
    (
        "forces",
        "Wheel Forces",
        ["Fx_N", "Fy_N", "Fz_N"],
        "Force (N)",
    ),
    (
        "moments",
        "Wheel Moments",
        ["Mx_Nm", "My_Nm", "Mz_Nm"],
        "Moment (Nm)",
    ),
    (
        "velocity",
        "Wheel Velocity",
        ["Velocity_RPM"],
        "Velocity (RPM)",
    ),
    (
        "position",
        "Wheel Position",
        ["Position_deg"],
        "Position (deg)",
    ),
    (
        "accelerations",
        "Wheel Accelerations",
        ["Ax_g", "Ay_g", "Az_g"],
        "Acceleration (g)",
    ),
]


def read_wft_csv(csv_path):
    times = []
    values = {name: [] for name in CHANNELS}

    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("CSV has no header.")

        required = ["time_s"] + CHANNELS
        missing = [name for name in required if name not in reader.fieldnames]

        if missing:
            raise ValueError(
                "CSV is missing required column(s): " + ", ".join(missing)
            )

        for row in reader:
            times.append(float(row["time_s"]))

            for name in CHANNELS:
                values[name].append(float(row[name]))

    if not times:
        raise ValueError("CSV contains no WFT samples.")

    return times, values


def calculate_stats(values):
    stats = {}

    for name, data in values.items():
        count = len(data)

        if count == 0:
            continue

        minimum = min(data)
        maximum = max(data)
        mean = sum(data) / count

        # Population standard deviation without requiring numpy.
        variance = sum((x - mean) ** 2 for x in data) / count
        std_dev = variance ** 0.5

        peak_abs = max(abs(minimum), abs(maximum))

        stats[name] = {
            "count": count,
            "min": minimum,
            "max": maximum,
            "mean": mean,
            "std_dev": std_dev,
            "peak_abs": peak_abs,
        }

    return stats


def write_stats(stats_path, csv_path, times, stats):
    duration = times[-1] - times[0]

    if duration > 0:
        sample_rate = (len(times) - 1) / duration
    else:
        sample_rate = 0.0

    with open(stats_path, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(["WFT RUN ANALYSIS"])
        writer.writerow([])
        writer.writerow(["Source CSV", csv_path.name])
        writer.writerow(["Samples", len(times)])
        writer.writerow(["Duration (s)", f"{duration:.6f}"])
        writer.writerow(["Approx Sample Rate (Hz)", f"{sample_rate:.3f}"])
        writer.writerow([])

        writer.writerow([
            "Channel",
            "Count",
            "Minimum",
            "Maximum",
            "Mean",
            "Std Dev",
            "Peak Absolute",
        ])

        for name in CHANNELS:
            s = stats[name]
            writer.writerow([
                name,
                s["count"],
                f"{s['min']:.6f}",
                f"{s['max']:.6f}",
                f"{s['mean']:.6f}",
                f"{s['std_dev']:.6f}",
                f"{s['peak_abs']:.6f}",
            ])


def make_plot(times, values, channels, title, ylabel, output_path):
    # One figure per plot group; no subplot grid.
    fig, ax = plt.subplots(figsize=(12, 6))

    for channel in channels:
        ax.plot(times, values[channel], label=channel)

    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)

    if len(channels) > 1:
        ax.legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def analyze_file(input_filename):
    csv_path = Path(input_filename).resolve()

    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    run_folder = csv_path.parent
    plots_folder = run_folder / "plots"
    plots_folder.mkdir(exist_ok=True)

    # WFT0019_wft.csv -> WFT0019
    run_name = csv_path.stem
    if run_name.lower().endswith("_wft"):
        run_name = run_name[:-4]

    stats_path = run_folder / f"{run_name}_analysis.csv"

    print("=" * 60)
    print("WFT RUN ANALYSIS")
    print("=" * 60)
    print(f"Input:       {csv_path}")
    print(f"Run folder:  {run_folder}")
    print(f"Plots:       {plots_folder}")

    times, values = read_wft_csv(csv_path)
    stats = calculate_stats(values)

    duration = times[-1] - times[0]
    sample_rate = (len(times) - 1) / duration if duration > 0 else 0.0

    print(f"Samples:     {len(times):,}")
    print(f"Duration:    {duration:.3f} s")
    print(f"Sample rate: {sample_rate:.2f} Hz")

    write_stats(stats_path, csv_path, times, stats)

    for filename, title, channels, ylabel in PLOT_GROUPS:
        output_path = plots_folder / f"{run_name}_{filename}.png"

        make_plot(
            times,
            values,
            channels,
            title,
            ylabel,
            output_path,
        )

        print(f"Created:     {output_path.name}")

    print()
    print("Key ranges:")

    for name in CHANNELS:
        s = stats[name]
        print(
            f"  {name:<14} "
            f"{s['min']:>10.3f} to {s['max']:>10.3f}"
        )

    print()
    print(f"Analysis CSV: {stats_path}")
    print(f"Plots folder: {plots_folder}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("    py analyze_wft.py runs\\WFT0019\\WFT0019_wft.csv")
        print("    py analyze_wft.py runs\\WFT0019\\WFT0019_wft.csv runs\\WFT0020\\WFT0020_wft.csv")
        print("    py analyze_wft.py runs\\*\\*_wft.csv")
        sys.exit(1)

    files = sys.argv[1:]

    print("=" * 60)
    print(f"WFT ANALYSIS BATCH: {len(files)} file(s)")
    print("=" * 60)

    successful = 0
    failed = 0

    for index, filename in enumerate(files, start=1):
        print()
        print("#" * 60)
        print(f"FILE {index} OF {len(files)}: {filename}")
        print("#" * 60)

        try:
            analyze_file(filename)
            successful += 1
        except Exception as error:
            failed += 1
            print(f"ERROR: {error}")
            print("Continuing with remaining files...")

    print()
    print("=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Files requested: {len(files)}")
    print(f"Successful:      {successful}")
    print(f"Failed:          {failed}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

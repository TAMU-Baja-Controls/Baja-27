import argparse
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# CT3 DBC Signal Definitions:
# (can_id_dec, signal_name, start_byte, scale, offset, unit)
CT3_DBC_MAP = [
    # BO_ 33 (0x21) RF_A
    (33, "RF_X_Force",        0, 0.274424979248047, 0.0, "lbf"),
    (33, "RF_Y_Force",        2, 0.137212489624023, 0.0, "lbf"),
    (33, "RF_Z_Force",        4, 0.274424979248047, 0.0, "lbf"),
    (33, "RF_MX_Moment",      6, 0.135051663024902, 0.0, "lb-ft"),
    # BO_ 34 (0x22) RF_B
    (34, "RF_MY_Moment",      0, 0.135051663024902, 0.0, "lb-ft"),
    (34, "RF_MZ_Moment",      2, 0.135051663024902, 0.0, "lb-ft"),
    (34, "RF_Velocity",       4, 0.06103515625,     0.0, "rpm"),
    (34, "RF_Position",       6, 0.010986328125,    0.0, "degrees"),
    # BO_ 35 (0x23) RF_C
    (35, "RF_X_Acceleration", 0, 0.0030517578125,   0.0, "g"),
    (35, "RF_Y_Acceleration", 2, 0.0030517578125,   0.0, "g"),
    (35, "RF_Z_Acceleration", 4, 0.0030517578125,   0.0, "g"),
]


def parse_can_id(series: pd.Series) -> np.ndarray:
    """Convert hex ('0x21', '21h') or integer ('33', 33) CAN IDs into an int64 array."""
    if pd.api.types.is_numeric_dtype(series):
        return series.to_numpy(dtype=np.int64, na_value=-1)

    # Map unique CAN ID strings for fast vectorized conversion
    unique_vals = series.unique()
    mapping = {}
    for val in unique_vals:
        if pd.isna(val):
            mapping[val] = -1
            continue
        s = str(val).strip().lower()
        if s.startswith("0x"):
            mapping[val] = int(s, 16)
        elif s.endswith("h"):
            mapping[val] = int(s[:-1], 16)
        else:
            try:
                mapping[val] = int(s, 10)
            except ValueError:
                mapping[val] = int(s, 16)

    return series.map(mapping).to_numpy(dtype=np.int64)


def ensure_byte_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure data_0 .. data_7 numeric columns exist, parsing data_hex if needed."""
    byte_cols = [f"data_{i}" for i in range(8)]
    if all(col in df.columns for col in byte_cols):
        for col in byte_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                u_vals = df[col].unique()
                b_map = {}
                for v in u_vals:
                    if pd.isna(v):
                        b_map[v] = 0
                    else:
                        s = str(v).strip().lower()
                        b_map[v] = int(s, 16) if s.startswith("0x") else int(s)
                df[col] = df[col].map(b_map).astype(np.uint8)
        return df

    if "data_hex" in df.columns:
        hex_split = df["data_hex"].astype(str).str.strip().str.split(expand=True)
        for i in range(8):
            u_bytes = hex_split[i].unique()
            b_map = {b: int(str(b).strip(), 16) for b in u_bytes if pd.notna(b)}
            df[f"data_{i}"] = hex_split[i].map(b_map).fillna(0).astype(np.uint8)
        return df

    raise ValueError("Input CSV must contain either 'data_0'..'data_7' or 'data_hex'.")


def decode_int16_le(lsb: np.ndarray, msb: np.ndarray) -> np.ndarray:
    """Decode two unsigned byte arrays into a 16-bit signed Little-Endian float array."""
    lsb_u16 = np.asarray(lsb, dtype=np.uint16)
    msb_u16 = np.asarray(msb, dtype=np.uint16)
    raw_u16 = lsb_u16 | (msb_u16 << 8)
    return raw_u16.view(np.int16).astype(np.float64)


def rotate_xz_plane(vx: np.ndarray, vz: np.ndarray, theta_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate (X, Z) vectors in the wheel rotation plane by theta_deg."""
    rad = np.deg2rad(theta_deg)
    c, s = np.cos(rad), np.sin(rad)
    vx_new = vx * c - vz * s
    vz_new = vx * s + vz * c
    return vx_new, vz_new


def estimate_zero_angle_offset(merged: pd.DataFrame, mode: str = "gravity") -> float:
    """
    Estimate the X-Z zero-angle shift from active stationary frames
    (where |RF_Velocity| < 0.5 rpm and gravity acceleration > 0.2 g).
    """
    accel_mag = np.hypot(merged["RF_X_Acceleration"], merged["RF_Z_Acceleration"])
    static_mask = (merged["RF_Velocity"].abs() < 0.5) & (accel_mag > 0.2)
    cal_df = merged[static_mask] if static_mask.sum() > 100 else merged[accel_mag > 0.2]

    if mode == "gravity":
        theta_deg = np.degrees(
            np.arctan2(cal_df["RF_X_Acceleration"].mean(), cal_df["RF_Z_Acceleration"].mean())
        )
    elif mode == "static_force":
        theta_deg = np.degrees(
            np.arctan2(cal_df["RF_X_Force"].mean(), cal_df["RF_Z_Force"].mean())
        )
    else:
        theta_deg = 0.0

    return float(theta_deg)


def decode_wft_can_csv(
    csv_path: str,
    align_mode: str = "gravity",
    theta_override: float | None = None,
    invert_x: bool = False,
    export_decoded_csv: bool = True,
) -> dict:
    """Decode raw CT3 WFT CAN frames, apply X-Z coordinate correction, and export CSV."""
    df = pd.read_csv(csv_path)
    df = ensure_byte_columns(df)
    df["can_id_dec"] = parse_can_id(df["can_id"])

    if "time_s" in df.columns:
        df["time_s"] = pd.to_numeric(df["time_s"], errors="coerce")
        time_col = "time_s"
    elif "timestamp_us" in df.columns:
        ts = pd.to_numeric(df["timestamp_us"], errors="coerce").to_numpy(dtype=np.float64)
        df["time_s"] = (ts - ts[0]) * 1e-6
        time_col = "time_s"
    else:
        df["time_s"] = np.arange(len(df), dtype=np.float64)
        time_col = "time_s"

    frames = {}
    for msg_id in (33, 34, 35):
        sub = df[df["can_id_dec"] == msg_id].copy().reset_index(drop=True)
        if sub.empty:
            raise ValueError(f"No CAN frames found with ID {msg_id} (0x{msg_id:02X}) in {csv_path}")
        for cid, sig_name, start_byte, scale, offset, _ in CT3_DBC_MAP:
            if cid == msg_id:
                lsb = sub[f"data_{start_byte}"].to_numpy(dtype=np.uint16)
                msb = sub[f"data_{start_byte + 1}"].to_numpy(dtype=np.uint16)
                sub[sig_name] = decode_int16_le(lsb, msb) * scale + offset
        frames[msg_id] = sub

    f33 = frames[33][[time_col, "RF_X_Force", "RF_Y_Force", "RF_Z_Force", "RF_MX_Moment"]]
    f34 = frames[34][[time_col, "RF_MY_Moment", "RF_MZ_Moment", "RF_Velocity", "RF_Position"]]
    f35 = frames[35][[time_col, "RF_X_Acceleration", "RF_Y_Acceleration", "RF_Z_Acceleration"]]

    merged = pd.merge_asof(
        f33.sort_values(time_col),
        f34.sort_values(time_col),
        on=time_col,
        direction="nearest",
    )
    merged = pd.merge_asof(
        merged,
        f35.sort_values(time_col),
        on=time_col,
        direction="nearest",
    )

    # Determine rotation angle theta_0
    if theta_override is not None:
        theta_deg = float(theta_override)
    elif align_mode in ("gravity", "static_force"):
        theta_deg = estimate_zero_angle_offset(merged, mode=align_mode)
    else:
        theta_deg = 0.0

    print(f"[INFO] Applying X-Z plane rotation: theta_0 = {theta_deg:.2f} deg (mode='{align_mode}')")

    # Apply X-Z plane rotation to Forces, Moments, and Accelerations
    merged["RF_X_Force_corr"], merged["RF_Z_Force_corr"] = rotate_xz_plane(
        merged["RF_X_Force"].to_numpy(dtype=np.float64),
        merged["RF_Z_Force"].to_numpy(dtype=np.float64),
        theta_deg,
    )
    merged["RF_MX_Moment_corr"], merged["RF_MZ_Moment_corr"] = rotate_xz_plane(
        merged["RF_MX_Moment"].to_numpy(dtype=np.float64),
        merged["RF_MZ_Moment"].to_numpy(dtype=np.float64),
        theta_deg,
    )
    merged["RF_X_Acceleration_corr"], merged["RF_Z_Acceleration_corr"] = rotate_xz_plane(
        merged["RF_X_Acceleration"].to_numpy(dtype=np.float64),
        merged["RF_Z_Acceleration"].to_numpy(dtype=np.float64),
        theta_deg,
    )

    if invert_x:
        merged["RF_X_Force_corr"] *= -1.0
        merged["RF_MX_Moment_corr"] *= -1.0
        merged["RF_X_Acceleration_corr"] *= -1.0

    if export_decoded_csv:
        base, _ = os.path.splitext(csv_path)
        out_csv = f"{base}_decoded_transformed.csv"
        merged.to_csv(out_csv, index=False)
        print(f"[INFO] Saved synchronized & transformed telemetry to: {out_csv}")

    return {"merged": merged, "time_col": time_col, "theta_deg": theta_deg}


def plot_forces(decoded_data: dict, output_image: str = "wft_forces_transformed.png"):
    """Plot coordinate-transformed Force X, Y, and Z channels."""
    merged = decoded_data["merged"]
    t = merged[decoded_data["time_col"]]
    theta_deg = decoded_data["theta_deg"]

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)

    axes[0].plot(
        t,
        merged["RF_X_Force_corr"],
        color="#d62728",
        linewidth=0.7,
        label=rf"Transformed $F_x'$ ($\theta_0 = {theta_deg:.2f}^\circ$)",
    )
    axes[0].set_ylabel("Force X (lbf)")
    axes[0].set_title(
        rf"CT3 Wheel Force Transducer — Transformed Forces ($F_x', F_y, F_z'$, $\theta_0 = {theta_deg:.2f}^\circ$)",
        fontsize=13,
        fontweight="bold",
    )
    axes[0].grid(True, linestyle="--", alpha=0.5)
    axes[0].legend(loc="upper right")

    axes[1].plot(t, merged["RF_Y_Force"], color="#2ca02c", linewidth=0.7, label="RF_Y_Force ($F_y$)")
    axes[1].set_ylabel("Force Y (lbf)")
    axes[1].grid(True, linestyle="--", alpha=0.5)
    axes[1].legend(loc="upper right")

    axes[2].plot(
        t,
        merged["RF_Z_Force_corr"],
        color="#1f77b4",
        linewidth=0.7,
        label=rf"Transformed $F_z'$ ($\theta_0 = {theta_deg:.2f}^\circ$)",
    )
    axes[2].set_ylabel("Force Z (lbf)")
    axes[2].grid(True, linestyle="--", alpha=0.5)
    axes[2].legend(loc="upper right")

    axes[3].plot(t, merged["RF_X_Force_corr"], color="#d62728", linewidth=0.6, alpha=0.85, label="Longitudinal $F_x'$")
    axes[3].plot(t, merged["RF_Y_Force"], color="#2ca02c", linewidth=0.6, alpha=0.85, label="Lateral $F_y$")
    axes[3].plot(t, merged["RF_Z_Force_corr"], color="#1f77b4", linewidth=0.6, alpha=0.85, label="Vertical $F_z'$")
    axes[3].set_ylabel("Force (lbf)")
    axes[3].set_xlabel("Time (s)")
    axes[3].set_title("Combined Transformed Force Overlay ($F_x', F_y, F_z'$)", fontsize=11, fontweight="bold")
    axes[3].grid(True, linestyle="--", alpha=0.5)
    axes[3].legend(loc="upper right", ncol=3)

    plt.tight_layout()
    plt.savefig(output_image, dpi=150)
    print(f"[INFO] Saved transformed force plot to: {output_image}")
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decode CT3 WFT Raw CAN CSV and apply X-Z angle transformation.")
    parser.add_argument("csv_file", nargs="?", default="WFT0000_3ftDrop_raw_can.csv", help="Path to raw CAN CSV file")
    parser.add_argument(
        "--align",
        choices=["gravity", "static_force", "none"],
        default="gravity",
        help="Auto-alignment reference method (default: gravity)",
    )
    parser.add_argument(
        "--theta-deg",
        type=float,
        default=None,
        help="Manual X-Z rotation angle in degrees (overrides --align)",
    )
    parser.add_argument("--invert-x", action="store_true", help="Flip sign of longitudinal X axis after rotation")
    parser.add_argument("--out-plot", default="wft_forces_transformed.png", help="Output plot filename")
    parser.add_argument("--no-export", action="store_true", help="Skip exporting decoded CSV")
    args = parser.parse_args()

    result = decode_wft_can_csv(
        args.csv_file,
        align_mode=args.align,
        theta_override=args.theta_deg,
        invert_x=args.invert_x,
        export_decoded_csv=not args.no_export,
    )
    plot_forces(result, output_image=args.out_plot)
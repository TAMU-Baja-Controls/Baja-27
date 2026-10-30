import struct
import csv
import sys
import shutil
from pathlib import Path
from collections import Counter

# ============================================================
# RAW LOGGER RECORD FORMAT
# Must match the ESP32 logger struct
# ============================================================

RECORD_FORMAT = "<IIBBH8s"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)  # 20 bytes


# ============================================================
# CT3 / WFT CAN IDs
# ============================================================

CT3_A_ID = 0x21
CT3_B_ID = 0x22
CT3_C_ID = 0x23

FORCE_SCALE = 0.30517578125
MOMENT_SCALE = 0.30517578125
VELOCITY_SCALE = 0.06103515625
POSITION_SCALE = 0.010986328125
ACCEL_SCALE = 0.0030517578125


# ============================================================
# ACCELERATED DAQ CAN IDs
# ============================================================

ACCEL_RPM_ID = 0x200
ACCEL_GPS_ID = 0x201
ACCEL_IMU_ID = 0x202


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _i16_le(data, offset):
    return struct.unpack_from("<h", data, offset)[0]


def _u16_le(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def _u16_be(data, offset):
    return int.from_bytes(
        data[offset:offset + 2],
        byteorder="big",
        signed=False
    )


def _i16_be(data, offset):
    return int.from_bytes(
        data[offset:offset + 2],
        byteorder="big",
        signed=True
    )


def _u32_be(data, offset):
    return int.from_bytes(
        data[offset:offset + 4],
        byteorder="big",
        signed=False
    )


# ============================================================
# CT3 / WFT DECODER
# ============================================================

def decode_ct3(can_id, data, dlc):

    if dlc < 8:
        return None

    if can_id == CT3_A_ID:
        return {
            "Fx_N": _i16_le(data, 0) * FORCE_SCALE,
            "Fy_N": _i16_le(data, 2) * FORCE_SCALE,
            "Fz_N": _i16_le(data, 4) * FORCE_SCALE,
            "Mx_Nm": _i16_le(data, 6) * MOMENT_SCALE,
        }

    if can_id == CT3_B_ID:
        return {
            "My_Nm": _i16_le(data, 0) * MOMENT_SCALE,
            "Mz_Nm": _i16_le(data, 2) * MOMENT_SCALE,
            "Velocity_RPM": _i16_le(data, 4) * VELOCITY_SCALE,
            "Position_deg": _u16_le(data, 6) * POSITION_SCALE,
        }

    if can_id == CT3_C_ID:
        return {
            "Ax_g": _i16_le(data, 0) * ACCEL_SCALE,
            "Ay_g": _i16_le(data, 2) * ACCEL_SCALE,
            "Az_g": _i16_le(data, 4) * ACCEL_SCALE,
        }

    return None


# ============================================================
# ACCELERATED DAQ DECODER
# ============================================================

def decode_accel_daq(can_id, data, dlc):

    # --------------------------------------------------------
    # 0x200
    # Primary RPM
    # Secondary RPM
    # Accelerated DAQ ESP32 timestamp
    # --------------------------------------------------------

    if can_id == ACCEL_RPM_ID and dlc >= 8:

        primary_rpm = _u16_be(data, 0)
        secondary_rpm = _u16_be(data, 2)
        node_timestamp_ms = _u32_be(data, 4)

        return {
            "primary_rpm": primary_rpm,
            "secondary_rpm": secondary_rpm,
            "node_timestamp_ms": node_timestamp_ms,
        }

    # --------------------------------------------------------
    # 0x201
    # RaceBox speed / GPS status
    # --------------------------------------------------------

    if can_id == ACCEL_GPS_ID and dlc >= 8:

        speed_raw = _u16_be(data, 0)

        return {
            "speed_kph": speed_raw / 10.0,
            "fix_status": data[2],
            "num_svs": data[3],
        }

    # --------------------------------------------------------
    # 0x202
    # RaceBox accelerometer
    # --------------------------------------------------------

    if can_id == ACCEL_IMU_ID and dlc >= 6:

        ax_raw = _i16_be(data, 0)
        ay_raw = _i16_be(data, 2)
        az_raw = _i16_be(data, 4)

        return {
            "racebox_ax_g": ax_raw / 1000.0,
            "racebox_ay_g": ay_raw / 1000.0,
            "racebox_az_g": az_raw / 1000.0,
        }

    return None


# ============================================================
# MAIN FILE DECODER
# ============================================================

def decode_file(input_filename):

    original_input_path = Path(input_filename).resolve()

    if not original_input_path.exists():
        raise FileNotFoundError(original_input_path)

    run_name = original_input_path.stem

    # --------------------------------------------------------
    # Create run folder
    # --------------------------------------------------------

    runs_folder = original_input_path.parent / "runs"
    runs_folder.mkdir(exist_ok=True)

    run_folder = runs_folder / run_name
    run_folder.mkdir(exist_ok=True)

    # Copy original BIN into run folder
    input_path = run_folder / original_input_path.name

    if original_input_path != input_path and not input_path.exists():
        shutil.copy2(original_input_path, input_path)

    # --------------------------------------------------------
    # Preserve CT3 DBC
    # --------------------------------------------------------

    dbc_destination = run_folder / "CT3.dbc"

    dbc_candidates = [
        original_input_path.parent / "CT3.dbc",
        Path(__file__).resolve().parent / "CT3.dbc",
    ]

    dbc_source = None

    for candidate in dbc_candidates:
        if candidate.exists():
            dbc_source = candidate
            break

    if dbc_source is not None:

        if dbc_source.resolve() != dbc_destination.resolve():
            shutil.copy2(dbc_source, dbc_destination)

        dbc_status = f"Copied: {dbc_destination}"

    else:

        dbc_status = (
            "WARNING: CT3.dbc was not found next to the BIN file "
            "or next to the decoder."
        )

    # --------------------------------------------------------
    # Output files
    # --------------------------------------------------------

    raw_output_path = run_folder / f"{run_name}_raw_can.csv"

    wft_output_path = run_folder / f"{run_name}_wft.csv"

    accel_output_path = (
        run_folder /
        f"{run_name}_accelerated_daq.csv"
    )

    summary_path = run_folder / f"{run_name}_summary.csv"

    # --------------------------------------------------------
    # File information
    # --------------------------------------------------------

    file_size = input_path.stat().st_size

    complete_records = file_size // RECORD_SIZE
    leftover_bytes = file_size % RECORD_SIZE

    print("=" * 60)
    print("BAJA CAN LOG DECODER")
    print("=" * 60)

    print(f"Input file:       {input_path}")
    print(f"File size:        {file_size:,} bytes")
    print(f"Complete records: {complete_records:,}")

    if leftover_bytes:

        print(
            f"WARNING: {leftover_bytes} incomplete byte(s) "
            f"at end of file will be ignored."
        )

    # ========================================================
    # STATISTICS
    # ========================================================

    id_counts = Counter()
    dlc_counts = Counter()

    first_absolute_timestamp = None
    last_absolute_timestamp = None
    previous_timestamp = None

    rollover_count = 0
    rollover_events = 0

    extended_count = 0
    rtr_count = 0

    records_written = 0

    # WFT statistics
    ct3_frames = 0
    ct3_sample_rows = 0
    incomplete_ct3_samples = 0

    sample_parts = {}
    sample_time_s = None
    sample_timestamp_us = None

    # Accelerated DAQ statistics
    accel_frames = 0
    rpm_frames = 0
    gps_frames = 0
    imu_frames = 0

    # ========================================================
    # OPEN FILES
    # ========================================================

    with open(input_path, "rb") as binary_file, \
         open(raw_output_path, "w", newline="") as raw_csv_file, \
         open(wft_output_path, "w", newline="") as wft_csv_file, \
         open(accel_output_path, "w", newline="") as accel_csv_file:

        raw_writer = csv.writer(raw_csv_file)
        wft_writer = csv.writer(wft_csv_file)
        accel_writer = csv.writer(accel_csv_file)

        # ----------------------------------------------------
        # RAW CAN CSV HEADER
        # ----------------------------------------------------

        raw_writer.writerow([
            "time_s",
            "timestamp_us",
            "can_id",
            "dlc",
            "extended",
            "rtr",
            "data_hex",
            "data_0",
            "data_1",
            "data_2",
            "data_3",
            "data_4",
            "data_5",
            "data_6",
            "data_7"
        ])

        # ----------------------------------------------------
        # WFT CSV HEADER
        # ----------------------------------------------------

        wft_writer.writerow([
            "time_s",
            "timestamp_us",
            "Fx_N",
            "Fy_N",
            "Fz_N",
            "Mx_Nm",
            "My_Nm",
            "Mz_Nm",
            "Velocity_RPM",
            "Position_deg",
            "Ax_g",
            "Ay_g",
            "Az_g"
        ])

        # ----------------------------------------------------
        # ACCELERATED DAQ CSV HEADER
        # ----------------------------------------------------

        accel_writer.writerow([
            "time_s",
            "timestamp_us",
            "can_id",
            "primary_rpm",
            "secondary_rpm",
            "node_timestamp_ms",
            "speed_kph",
            "fix_status",
            "num_svs",
            "racebox_ax_g",
            "racebox_ay_g",
            "racebox_az_g"
        ])

        # ====================================================
        # READ EVERY RAW CAN RECORD
        # ====================================================

        while True:

            record = binary_file.read(RECORD_SIZE)

            if len(record) < RECORD_SIZE:
                break

            (
                timestamp_us,
                can_id,
                dlc,
                flags,
                reserved,
                data
            ) = struct.unpack(RECORD_FORMAT, record)

            # ------------------------------------------------
            # micros() rollover
            # ------------------------------------------------

            if previous_timestamp is not None:

                if timestamp_us < previous_timestamp:
                    rollover_count += 1
                    rollover_events += 1

            previous_timestamp = timestamp_us

            absolute_timestamp = (
                timestamp_us +
                rollover_count * (2 ** 32)
            )

            if first_absolute_timestamp is None:
                first_absolute_timestamp = absolute_timestamp

            last_absolute_timestamp = absolute_timestamp

            time_s = (
                absolute_timestamp -
                first_absolute_timestamp
            ) / 1_000_000.0

            # ------------------------------------------------
            # Flags
            # ------------------------------------------------

            extended = bool(flags & 0x01)
            rtr = bool(flags & 0x02)

            if extended:
                extended_count += 1

            if rtr:
                rtr_count += 1

            # ------------------------------------------------
            # Statistics
            # ------------------------------------------------

            id_counts[can_id] += 1
            dlc_counts[dlc] += 1

            # ------------------------------------------------
            # Raw CAN CSV
            # ------------------------------------------------

            valid_length = min(dlc, 8)

            data_hex = " ".join(
                f"{byte:02X}"
                for byte in data[:valid_length]
            )

            raw_writer.writerow([
                f"{time_s:.6f}",
                timestamp_us,
                f"0x{can_id:X}",
                dlc,
                int(extended),
                int(rtr),
                data_hex,
                *data
            ])

            records_written += 1

            # =================================================
            # CT3 / WFT DECODING
            # =================================================

            if (
                can_id in (CT3_A_ID, CT3_B_ID, CT3_C_ID)
                and not rtr
                and dlc >= 8
            ):

                decoded = decode_ct3(
                    can_id,
                    data,
                    dlc
                )

                if decoded is not None:

                    ct3_frames += 1

                    # Frame A starts a new WFT sample
                    if can_id == CT3_A_ID:

                        if sample_parts:
                            incomplete_ct3_samples += 1

                        sample_parts = {}

                        sample_time_s = time_s
                        sample_timestamp_us = timestamp_us

                    # Ignore B/C before first A
                    if sample_time_s is not None:

                        sample_parts.update(decoded)

                        required = (
                            "Fx_N",
                            "Fy_N",
                            "Fz_N",
                            "Mx_Nm",
                            "My_Nm",
                            "Mz_Nm",
                            "Velocity_RPM",
                            "Position_deg",
                            "Ax_g",
                            "Ay_g",
                            "Az_g"
                        )

                        if all(
                            name in sample_parts
                            for name in required
                        ):

                            wft_writer.writerow([
                                f"{sample_time_s:.6f}",
                                sample_timestamp_us,

                                f"{sample_parts['Fx_N']:.6f}",
                                f"{sample_parts['Fy_N']:.6f}",
                                f"{sample_parts['Fz_N']:.6f}",

                                f"{sample_parts['Mx_Nm']:.6f}",
                                f"{sample_parts['My_Nm']:.6f}",
                                f"{sample_parts['Mz_Nm']:.6f}",

                                f"{sample_parts['Velocity_RPM']:.6f}",
                                f"{sample_parts['Position_deg']:.6f}",

                                f"{sample_parts['Ax_g']:.6f}",
                                f"{sample_parts['Ay_g']:.6f}",
                                f"{sample_parts['Az_g']:.6f}",
                            ])

                            ct3_sample_rows += 1

                            sample_parts = {}
                            sample_time_s = None
                            sample_timestamp_us = None

            # =================================================
            # ACCELERATED DAQ DECODING
            # =================================================

            if (
                can_id in (
                    ACCEL_RPM_ID,
                    ACCEL_GPS_ID,
                    ACCEL_IMU_ID
                )
                and not rtr
            ):

                decoded = decode_accel_daq(
                    can_id,
                    data,
                    dlc
                )

                if decoded is not None:

                    accel_frames += 1

                    primary_rpm = ""
                    secondary_rpm = ""
                    node_timestamp_ms = ""

                    speed_kph = ""
                    fix_status = ""
                    num_svs = ""

                    racebox_ax_g = ""
                    racebox_ay_g = ""
                    racebox_az_g = ""

                    if can_id == ACCEL_RPM_ID:

                        rpm_frames += 1

                        primary_rpm = decoded["primary_rpm"]
                        secondary_rpm = decoded["secondary_rpm"]
                        node_timestamp_ms = decoded["node_timestamp_ms"]

                    elif can_id == ACCEL_GPS_ID:

                        gps_frames += 1

                        speed_kph = f"{decoded['speed_kph']:.3f}"
                        fix_status = decoded["fix_status"]
                        num_svs = decoded["num_svs"]

                    elif can_id == ACCEL_IMU_ID:

                        imu_frames += 1

                        racebox_ax_g = (
                            f"{decoded['racebox_ax_g']:.4f}"
                        )

                        racebox_ay_g = (
                            f"{decoded['racebox_ay_g']:.4f}"
                        )

                        racebox_az_g = (
                            f"{decoded['racebox_az_g']:.4f}"
                        )

                    accel_writer.writerow([
                        f"{time_s:.6f}",
                        timestamp_us,
                        f"0x{can_id:X}",

                        primary_rpm,
                        secondary_rpm,
                        node_timestamp_ms,

                        speed_kph,
                        fix_status,
                        num_svs,

                        racebox_ax_g,
                        racebox_ay_g,
                        racebox_az_g
                    ])

    # ========================================================
    # CALCULATE SUMMARY
    # ========================================================

    if (
        first_absolute_timestamp is not None
        and last_absolute_timestamp is not None
    ):

        duration_s = (
            last_absolute_timestamp -
            first_absolute_timestamp
        ) / 1_000_000.0

    else:

        duration_s = 0.0

    if duration_s > 0:

        average_frame_rate = (
            records_written /
            duration_s
        )

        wft_sample_rate = (
            ct3_sample_rows /
            duration_s
        )

        accel_rate = (
            accel_frames /
            duration_s
        )

        rpm_rate = (
            rpm_frames /
            duration_s
        )

        gps_rate = (
            gps_frames /
            duration_s
        )

        imu_rate = (
            imu_frames /
            duration_s
        )

    else:

        average_frame_rate = 0.0
        wft_sample_rate = 0.0

        accel_rate = 0.0
        rpm_rate = 0.0
        gps_rate = 0.0
        imu_rate = 0.0

    # ========================================================
    # SUMMARY CSV
    # ========================================================

    with open(summary_path, "w", newline="") as summary_file:

        writer = csv.writer(summary_file)

        writer.writerow(["BAJA CAN LOG SUMMARY"])
        writer.writerow([])

        writer.writerow(["File", input_path.name])
        writer.writerow(["File Size (bytes)", file_size])
        writer.writerow(["Record Size (bytes)", RECORD_SIZE])
        writer.writerow(["Complete CAN Records", records_written])
        writer.writerow(["Incomplete Bytes", leftover_bytes])

        writer.writerow([])

        writer.writerow([
            "Recording Duration (s)",
            f"{duration_s:.6f}"
        ])

        writer.writerow([
            "Recording Duration (min)",
            f"{duration_s / 60:.3f}"
        ])

        writer.writerow([
            "Average CAN Frames/sec",
            f"{average_frame_rate:.2f}"
        ])

        writer.writerow([])

        writer.writerow([
            "ESP32 micros() Rollovers",
            rollover_events
        ])

        writer.writerow([
            "Extended Frames",
            extended_count
        ])

        writer.writerow([
            "RTR Frames",
            rtr_count
        ])

        # ----------------------------------------------------
        # WFT summary
        # ----------------------------------------------------

        writer.writerow([])
        writer.writerow(["CT3 / WFT Decode"])

        writer.writerow([
            "Decoded CT3 Frames",
            ct3_frames
        ])

        writer.writerow([
            "Decoded WFT Samples",
            ct3_sample_rows
        ])

        writer.writerow([
            "Decoded WFT Samples/sec",
            f"{wft_sample_rate:.2f}"
        ])

        writer.writerow([
            "Incomplete CT3 Sample Sets",
            incomplete_ct3_samples
        ])

        # ----------------------------------------------------
        # Accelerated DAQ summary
        # ----------------------------------------------------

        writer.writerow([])
        writer.writerow(["Accelerated DAQ Decode"])

        writer.writerow([
            "Total Accelerated DAQ Frames",
            accel_frames
        ])

        writer.writerow([
            "Accelerated DAQ Frames/sec",
            f"{accel_rate:.2f}"
        ])

        writer.writerow([
            "RPM Frames",
            rpm_frames
        ])

        writer.writerow([
            "RPM Frames/sec",
            f"{rpm_rate:.2f}"
        ])

        writer.writerow([
            "RaceBox GPS Frames",
            gps_frames
        ])

        writer.writerow([
            "RaceBox GPS Frames/sec",
            f"{gps_rate:.2f}"
        ])

        writer.writerow([
            "RaceBox IMU Frames",
            imu_frames
        ])

        writer.writerow([
            "RaceBox IMU Frames/sec",
            f"{imu_rate:.2f}"
        ])

        # ----------------------------------------------------
        # CAN IDs
        # ----------------------------------------------------

        writer.writerow([])
        writer.writerow([
            "CAN ID",
            "Frame Count",
            "Average Frames/sec"
        ])

        for can_id in sorted(id_counts):

            if duration_s > 0:
                rate = id_counts[can_id] / duration_s
            else:
                rate = 0

            writer.writerow([
                f"0x{can_id:X}",
                id_counts[can_id],
                f"{rate:.2f}"
            ])

        # ----------------------------------------------------
        # DLC
        # ----------------------------------------------------

        writer.writerow([])
        writer.writerow([
            "DLC",
            "Frame Count"
        ])

        for dlc in sorted(dlc_counts):

            writer.writerow([
                dlc,
                dlc_counts[dlc]
            ])

    # ========================================================
    # TERMINAL OUTPUT
    # ========================================================

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(
        f"Records decoded:     "
        f"{records_written:,}"
    )

    print(
        f"Duration:            "
        f"{duration_s:.3f} seconds"
    )

    print(
        f"Average CAN rate:    "
        f"{average_frame_rate:.1f} frames/sec"
    )

    print(
        f"Timestamp rollovers: "
        f"{rollover_events}"
    )

    print()

    print("CT3 / WFT:")

    print(
        f"  Decoded samples:   "
        f"{ct3_sample_rows:,}"
    )

    print(
        f"  Sample rate:       "
        f"{wft_sample_rate:.1f} samples/sec"
    )

    print()

    print("Accelerated DAQ:")

    print(
        f"  Total frames:      "
        f"{accel_frames:,}"
    )

    print(
        f"  RPM 0x200:         "
        f"{rpm_frames:,} "
        f"({rpm_rate:.1f} Hz)"
    )

    print(
        f"  GPS 0x201:         "
        f"{gps_frames:,} "
        f"({gps_rate:.1f} Hz)"
    )

    print(
        f"  IMU 0x202:         "
        f"{imu_frames:,} "
        f"({imu_rate:.1f} Hz)"
    )

    print()
    print("CAN IDs:")

    for can_id in sorted(id_counts):

        if duration_s > 0:
            rate = id_counts[can_id] / duration_s
        else:
            rate = 0

        print(
            f"  0x{can_id:X}: "
            f"{id_counts[can_id]:,} frames "
            f"({rate:.1f} frames/sec)"
        )

    print()

    print("=" * 60)
    print("FILES CREATED")
    print("=" * 60)

    print(f"Run folder:      {run_folder}")
    print(f"BIN copy:        {input_path}")
    print(f"DBC:             {dbc_status}")
    print(f"Raw CAN CSV:     {raw_output_path}")
    print(f"WFT CSV:         {wft_output_path}")
    print(f"Accelerated CSV: {accel_output_path}")
    print(f"Summary CSV:     {summary_path}")


# ============================================================
# COMMAND LINE
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("Usage:")
        print(
            "    py decode_wft_batch.py WFT0004.BIN"
        )

        print(
            "    py decode_wft_batch.py "
            "WFT0004.BIN WFT0005.BIN"
        )

        print(
            "    py decode_wft_batch.py *.BIN"
        )

        sys.exit(1)

    input_files = sys.argv[1:]

    print("=" * 60)
    print(
        f"BATCH DECODE: "
        f"{len(input_files)} file(s)"
    )
    print("=" * 60)

    successful = 0
    failed = 0

    for index, filename in enumerate(
        input_files,
        start=1
    ):

        print()

        print("#" * 60)

        print(
            f"FILE {index} OF "
            f"{len(input_files)}: "
            f"{filename}"
        )

        print("#" * 60)

        try:

            decode_file(filename)
            successful += 1

        except Exception as error:

            failed += 1

            print()
            print(
                f"ERROR decoding "
                f"{filename}:"
            )

            print(f"  {error}")

            print(
                "Continuing with "
                "remaining files..."
            )

    print()
    print("=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)

    print(
        f"Files requested: "
        f"{len(input_files)}"
    )

    print(
        f"Successful:      "
        f"{successful}"
    )

    print(
        f"Failed:          "
        f"{failed}"
    )

    if failed:
        sys.exit(1)

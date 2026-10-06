import struct
import csv
import sys
import shutil
from pathlib import Path
from collections import Counter

# Must match the ESP32 logger struct
RECORD_FORMAT = "<IIBBH8s"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)  # 20 bytes


# CT3 CAN IDs and DBC scale factors
CT3_A_ID = 0x21
CT3_B_ID = 0x22
CT3_C_ID = 0x23

FORCE_SCALE = 0.30517578125
MOMENT_SCALE = 0.30517578125
VELOCITY_SCALE = 0.06103515625
POSITION_SCALE = 0.010986328125
ACCEL_SCALE = 0.0030517578125

def _i16(data, offset):
    return struct.unpack_from("<h", data, offset)[0]

def _u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]

def decode_ct3(can_id, data, dlc):
    if dlc < 8:
        return None
    if can_id == CT3_A_ID:
        return {
            "Fx_N": _i16(data, 0) * FORCE_SCALE,
            "Fy_N": _i16(data, 2) * FORCE_SCALE,
            "Fz_N": _i16(data, 4) * FORCE_SCALE,
            "Mx_Nm": _i16(data, 6) * MOMENT_SCALE,
        }
    if can_id == CT3_B_ID:
        return {
            "My_Nm": _i16(data, 0) * MOMENT_SCALE,
            "Mz_Nm": _i16(data, 2) * MOMENT_SCALE,
            "Velocity_RPM": _i16(data, 4) * VELOCITY_SCALE,
            "Position_deg": _u16(data, 6) * POSITION_SCALE,
        }
    if can_id == CT3_C_ID:
        return {
            "Ax_g": _i16(data, 0) * ACCEL_SCALE,
            "Ay_g": _i16(data, 2) * ACCEL_SCALE,
            "Az_g": _i16(data, 4) * ACCEL_SCALE,
        }
    return None

def decode_file(input_filename):
    original_input_path = Path(input_filename).resolve()

    # One folder per run. Copy the original BIN so the source file remains protected.
    run_name = original_input_path.stem

    # Put every decoded test in a common runs/ directory.
    runs_folder = original_input_path.parent / "runs"
    runs_folder.mkdir(exist_ok=True)

    run_folder = runs_folder / run_name
    run_folder.mkdir(exist_ok=True)

    input_path = run_folder / original_input_path.name
    if original_input_path != input_path and not input_path.exists():
        shutil.copy2(original_input_path, input_path)

    # Preserve the CT3 DBC with every run so the CAN decoding definition
    # used for that test stays with the raw data.
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

    output_path = run_folder / f"{run_name}_raw_can.csv"
    wft_output_path = run_folder / f"{run_name}_wft.csv"
    summary_path = run_folder / f"{run_name}_summary.csv"

    file_size = input_path.stat().st_size
    complete_records = file_size // RECORD_SIZE
    leftover_bytes = file_size % RECORD_SIZE

    print("=" * 55)
    print("WFT CAN LOG DECODER")
    print("=" * 55)
    print(f"Input file:       {input_path}")
    print(f"File size:        {file_size:,} bytes")
    print(f"Complete records: {complete_records:,}")

    if leftover_bytes:
        print(
            f"WARNING: {leftover_bytes} incomplete byte(s) "
            f"at end of file will be ignored."
        )

    # Statistics
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

    # CT3/WFT decoded sample state
    ct3_frames = 0
    ct3_sample_rows = 0
    incomplete_ct3_samples = 0
    sample_parts = {}
    sample_time_s = None
    sample_timestamp_us = None

    with open(input_path, "rb") as binary_file, \
         open(output_path, "w", newline="") as csv_file, \
         open(wft_output_path, "w", newline="") as wft_csv_file:

        writer = csv.writer(csv_file)
        wft_writer = csv.writer(wft_csv_file)
        wft_writer.writerow([
            "time_s", "timestamp_us",
            "Fx_N", "Fy_N", "Fz_N", "Mx_Nm",
            "My_Nm", "Mz_Nm", "Velocity_RPM", "Position_deg",
            "Ax_g", "Ay_g", "Az_g"
        ])

        writer.writerow([
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

            # -----------------------------
            # Handle micros() rollover
            # -----------------------------

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

            # -----------------------------
            # Flags
            # -----------------------------

            extended = bool(flags & 0x01)
            rtr = bool(flags & 0x02)

            if extended:
                extended_count += 1

            if rtr:
                rtr_count += 1

            # -----------------------------
            # Statistics
            # -----------------------------

            id_counts[can_id] += 1
            dlc_counts[dlc] += 1

            # -----------------------------
            # Payload
            # -----------------------------

            valid_length = min(dlc, 8)

            data_hex = " ".join(
                f"{byte:02X}"
                for byte in data[:valid_length]
            )

            writer.writerow([
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

            # Decode CT3 messages into one engineering-unit row per A/B/C sample set.
            if can_id in (CT3_A_ID, CT3_B_ID, CT3_C_ID) and not rtr and dlc >= 8:
                decoded = decode_ct3(can_id, data, dlc)
                if decoded is not None:
                    ct3_frames += 1

                    # Frame A starts a new CT3 sample.
                    if can_id == CT3_A_ID:
                        if sample_parts:
                            incomplete_ct3_samples += 1
                        sample_parts = {}
                        sample_time_s = time_s
                        sample_timestamp_us = timestamp_us

                    # Ignore B/C if capture began before the first A.
                    if sample_time_s is not None:
                        sample_parts.update(decoded)

                        required = (
                            "Fx_N", "Fy_N", "Fz_N", "Mx_Nm",
                            "My_Nm", "Mz_Nm", "Velocity_RPM", "Position_deg",
                            "Ax_g", "Ay_g", "Az_g"
                        )

                        if all(name in sample_parts for name in required):
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

    # -----------------------------------------
    # Calculate summary statistics
    # -----------------------------------------

    if (
        first_absolute_timestamp is not None
        and last_absolute_timestamp is not None
    ):
        duration_s = (
            last_absolute_timestamp -
            first_absolute_timestamp
        ) / 1_000_000.0
    else:
        duration_s = 0

    if duration_s > 0:
        average_frame_rate = records_written / duration_s
        wft_sample_rate = ct3_sample_rows / duration_s
    else:
        average_frame_rate = 0
        wft_sample_rate = 0

    # -----------------------------------------
    # Write summary CSV
    # -----------------------------------------

    with open(summary_path, "w", newline="") as summary_file:

        writer = csv.writer(summary_file)

        writer.writerow(["WFT CAN LOG SUMMARY"])
        writer.writerow([])

        writer.writerow(["File", input_path.name])
        writer.writerow(["File Size (bytes)", file_size])
        writer.writerow(["Record Size (bytes)", RECORD_SIZE])
        writer.writerow(["Complete CAN Records", records_written])
        writer.writerow(["Incomplete Bytes", leftover_bytes])

        writer.writerow([])

        writer.writerow(["Recording Duration (s)", f"{duration_s:.6f}"])
        writer.writerow(["Recording Duration (min)", f"{duration_s / 60:.3f}"])
        writer.writerow(["Average CAN Frames/sec", f"{average_frame_rate:.2f}"])

        writer.writerow([])

        writer.writerow(["ESP32 micros() Rollovers", rollover_events])
        writer.writerow(["Extended Frames", extended_count])
        writer.writerow(["RTR Frames", rtr_count])

        writer.writerow([])
        writer.writerow(["CT3 / WFT Decode"])
        writer.writerow(["Decoded CT3 Frames", ct3_frames])
        writer.writerow(["Decoded WFT Samples", ct3_sample_rows])
        writer.writerow(["Decoded WFT Samples/sec", f"{wft_sample_rate:.2f}"])
        writer.writerow(["Incomplete CT3 Sample Sets", incomplete_ct3_samples])
        writer.writerow(["Expected WFT Samples/sec", "500.00"])
        writer.writerow(["Expected Total CAN Frames/sec", "1500.00"])

        writer.writerow([])
        writer.writerow(["CAN ID", "Frame Count", "Average Frames/sec"])

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

        writer.writerow([])
        writer.writerow(["DLC", "Frame Count"])

        for dlc in sorted(dlc_counts):
            writer.writerow([
                dlc,
                dlc_counts[dlc]
            ])

    # -----------------------------------------
    # Terminal output
    # -----------------------------------------

    print()
    print("=" * 55)
    print("SUMMARY")
    print("=" * 55)

    print(f"Records decoded:     {records_written:,}")
    print(f"Duration:            {duration_s:.3f} seconds")
    print(f"Duration:            {duration_s / 60:.2f} minutes")
    print(f"Average CAN rate:    {average_frame_rate:.1f} frames/sec")
    print(f"Timestamp rollovers: {rollover_events}")
    print(f"Extended frames:     {extended_count:,}")
    print(f"RTR frames:          {rtr_count:,}")

    print()
    print("CT3 / WFT:")
    print(f"  Decoded samples:   {ct3_sample_rows:,}")
    print(f"  Sample rate:       {wft_sample_rate:.1f} samples/sec")
    print(f"  Expected:          ~500 samples/sec")
    print(f"  Expected CAN rate: ~1500 frames/sec")

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
    print("DLC distribution:")

    for dlc in sorted(dlc_counts):
        print(
            f"  DLC {dlc}: "
            f"{dlc_counts[dlc]:,} frames"
        )

    print()
    print("=" * 55)
    print("FILES CREATED")
    print("=" * 55)
    print(f"Run folder:  {run_folder}")
    print(f"BIN copy:    {input_path}")
    print(f"DBC:         {dbc_status}")
    print(f"Raw CAN CSV: {output_path}")
    print(f"WFT CSV:     {wft_output_path}")
    print(f"Summary CSV: {summary_path}")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:")
        print("    py decode_wft_batch.py WFT0016.BIN")
        print("    py decode_wft_batch.py WFT0016.BIN WFT0017.BIN WFT0018.BIN")
        print("    py decode_wft_batch.py *.BIN")
        sys.exit(1)

    input_files = sys.argv[1:]

    print("=" * 60)
    print(f"BATCH DECODE: {len(input_files)} file(s)")
    print("=" * 60)

    successful = 0
    failed = 0

    for index, filename in enumerate(input_files, start=1):
        print()
        print("#" * 60)
        print(f"FILE {index} OF {len(input_files)}: {filename}")
        print("#" * 60)

        try:
            decode_file(filename)
            successful += 1
        except Exception as error:
            failed += 1
            print()
            print(f"ERROR decoding {filename}:")
            print(f"  {error}")
            print("Continuing with remaining files...")

    print()
    print("=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)
    print(f"Files requested: {len(input_files)}")
    print(f"Successful:      {successful}")
    print(f"Failed:          {failed}")

    if failed:
        sys.exit(1)

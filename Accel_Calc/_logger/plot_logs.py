#!/usr/bin/env python3
"""
plot_logs.py - a single-file CSV log plotter.

FOLDER LAYOUT
    MyFolder/
        plot_logs.py      <- this file
        Logs/
            run1.csv
            run2.csv
            subfolder/run3.csv   (subfolders are searched too)

RUN
    python plot_logs.py

REQUIREMENTS
    Python 3.8+
    matplotlib          ->  pip install matplotlib
    tkinter             ->  ships with Python on Windows/macOS.
                            On Debian/Ubuntu: sudo apt install python3-tk

WHAT IT DOES
    Reads every .csv under ./Logs, offers every column of every file in an
    X dropdown and four Y dropdowns, and plots the selected Y series
    against X.  Y series 2, 3 and 4 have their own show/hide check boxes,
    so you can plot one to four curves at a time.

    Each Y series gets its OWN Y axis, so series with wildly different
    magnitudes stay readable.  The first axis sits on the left, the second
    on the right, and the third and fourth are stacked outside those two.
    Each axis - its spine, ticks and label - is drawn in the colour of the
    series that owns it.  Tick "Share one Y axis" to drop every series onto
    a single common axis and range instead.

    There is no legend, because it covers the curves.  Each Y row instead
    names its own colour, in that colour, next to the dropdown.

AXIS BOUNDS
    Every axis owns its own "auto" tick box plus min / max entry boxes: the
    X axis on the top row, then one row per Y series.  There is only ever
    one X axis, so the X row always drives the whole plot.

    While "auto" is ticked, that row's two boxes mirror whatever is on
    screen - including toolbar pans and zooms - so un-ticking the box hands
    you the current view to edit.  Clearing one box leaves that single
    limit automatic, e.g. min 0 with an empty max pins the bottom and lets
    the top follow the data.

    Because the bounds are per series, Y1 can be pinned to 0..100 while Y2
    scales itself.  In "Share one Y axis" mode the Y1 row drives the single
    shared axis and the other Y rows grey out.

HOW MISSING / BAD DATA IS TREATED
    A cell becomes "missing" (NaN) if it is blank, whitespace, or one of:
    na, n/a, nan, null, none, -, --, ?, #n/a, #div/0!, inf, -inf
    ...or if it simply is not a number.
    A pair of points is drawn only when BOTH x and y are valid numbers.
    Invalid pairs are left as gaps rather than being stitched over, so a
    line plot shows a break where data is missing instead of a fake
    straight segment. The status bar always reports how many points were
    dropped.

    Clock-style strings (HH:MM:SS.sss or MM:SS.sss) are converted to
    seconds. This is the only value transformation the program performs.
"""

import csv
import io
import math
import re
import sys
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

LOGS_DIRNAME = "Logs"
NAN = float("nan")

# Lower-cased strings that mean "no data".
MISSING_TOKENS = {
    "", "na", "n/a", "n.a.", "nan", "null", "none", "nil",
    "-", "--", "---", "?", "#n/a", "#na", "#value!", "#div/0!", "#ref!",
    "inf", "-inf", "+inf", "infinity", "-infinity",
}

# HH:MM:SS.sss  or  MM:SS.sss
TIME_RE = re.compile(r"^(?:(\d{1,3}):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")

ROW_INDEX_LABEL = "(row index)"

# How many Y series can be plotted at once, and the colour of each slot.
# Slot colours are fixed so a series keeps its colour when another one is
# switched off.
N_Y_SERIES = 4
SERIES_COLORS = ("#1f77b4", "#d62728", "#2ca02c", "#9467bd")

# Spelled out beside each dropdown in that slot's colour, so the plot needs
# no legend covering the curves.  The name is there as well as the colour so
# the swatch still works if the colours are hard to tell apart.
SERIES_COLOR_NAMES = ("blue", "red", "green", "purple")

# Where the n-th drawn Y axis goes: which side of the plot, and how many
# steps outward from that side.  Alternating sides keeps the plot area as
# wide as possible instead of pushing four axes off one edge.
AXIS_PLACEMENT = (("left", 0), ("right", 0), ("left", 1), ("right", 1))

# Figure margins, in points.  Offset spines are positioned in points too,
# so reserving room for them means simple arithmetic - and it is why this
# file sets the margins by hand instead of calling tight_layout(), which
# does not account for spines pushed outward.
SPINE_GAP_PTS = 58.0      # room for one Y axis: ticks, numbers and label
EDGE_PAD_PTS = 14.0       # breathing room outside the outermost axis
BOTTOM_PAD_PTS = 46.0     # X ticks + X label
TOP_PAD_PTS = 34.0        # title


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------

def to_number(raw):
    """Convert one CSV cell to a float, or NaN if it is not usable data."""
    if raw is None:
        return NAN
    text = raw.strip()
    if text.lower() in MISSING_TOKENS:
        return NAN

    # Strip a trailing/leading unit-free wrapper like quotes.
    text = text.strip('"').strip("'").strip()
    if text.lower() in MISSING_TOKENS:
        return NAN

    try:
        value = float(text)
    except ValueError:
        match = TIME_RE.match(text)
        if match:
            hours = float(match.group(1) or 0.0)
            minutes = float(match.group(2))
            seconds = float(match.group(3))
            return hours * 3600.0 + minutes * 60.0 + seconds
        return NAN

    if math.isnan(value) or math.isinf(value):
        return NAN
    return value


def shorten(text, limit=60):
    """Trim a plot label so several long column names still fit on screen."""
    return text if len(text) <= limit else text[:limit - 3] + "..."


def read_text(path):
    """Read a file as text, tolerating BOMs and non-UTF-8 bytes."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("latin-1", errors="replace")


def sniff_delimiter(text):
    """Guess the delimiter from the first few lines; default to comma."""
    sample = "\n".join(text.splitlines()[:25])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def unique_names(header):
    """Turn a header row into a list of unique, non-empty column names."""
    names = []
    counts = {}
    for i, cell in enumerate(header):
        name = cell.strip() or "column_{}".format(i + 1)
        if name in counts:
            counts[name] += 1
            name = "{}.{}".format(name, counts[name])
        else:
            counts[name] = 0
        names.append(name)
    return names


def load_csv(path):
    """
    Parse one CSV file.

    Returns (columns, n_rows) where columns is {name: [float, ...]},
    or (None, 0) if the file has no usable header/data.
    """
    text = read_text(path)
    if not text.strip():
        return None, 0

    delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)

    header = None
    for row in reader:
        if any(cell.strip() for cell in row):
            header = row
            break
    if not header:
        return None, 0

    names = unique_names(header)
    columns = {name: [] for name in names}
    n_rows = 0

    for row in reader:
        if not any(cell.strip() for cell in row):
            continue  # skip blank lines
        for i, name in enumerate(names):
            columns[name].append(to_number(row[i]) if i < len(row) else NAN)
        n_rows += 1

    return columns, n_rows


def scan_logs(folder):
    """
    Read every .csv under `folder` (recursively).

    Returns (datasets, errors):
        datasets: {display_name: {"columns": {...}, "rows": int}}
        errors:   [(display_name, message), ...]
    """
    datasets = {}
    errors = []
    if not folder.is_dir():
        return datasets, errors

    paths = sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in (".csv", ".txt", ".tsv")
    )

    for path in paths:
        label = path.relative_to(folder).as_posix()
        try:
            columns, rows = load_csv(path)
        except Exception as exc:  # keep one bad file from killing the app
            errors.append((label, "{}: {}".format(type(exc).__name__, exc)))
            continue
        if not columns:
            errors.append((label, "empty or no header row"))
            continue
        if rows == 0:
            errors.append((label, "header only, no data rows"))
            continue
        datasets[label] = {"columns": columns, "rows": rows}

    return datasets, errors


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

class LogPlotter(tk.Tk):

    def __init__(self, logs_dir):
        super().__init__()
        self.logs_dir = logs_dir
        self.title("CSV Log Plotter - {}".format(logs_dir))
        self.geometry("1220x780")
        self.minsize(900, 560)

        self.datasets = {}
        self.choices = {}        # dropdown label -> (file_label, column_name)
        self.load_errors = []
        self.load_warning = ""   # stays visible across plots

        self.extra_axes = []     # twinned Y axes, rebuilt on every draw
        self.slot_axes = {}      # Y slot index -> the axes its bound row owns
        self.sync_targets = []   # (axes, "x"/"y", auto_var, bound_vars, name)
        self.axis_counts = (1, 0)   # Y axes on the (left, right) edge
        self._drawing = False    # ignore limit callbacks while we redraw

        self._build_ui()
        self.reload()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self):
        controls = ttk.Frame(self, padding=(10, 10, 10, 4))
        controls.pack(side=tk.TOP, fill=tk.X)

        # Row 0: the single X axis, its bounds, and Reload.
        ttk.Label(controls, text="X axis:").grid(row=0, column=0, sticky="w")
        self.x_var = tk.StringVar()
        self.x_box = ttk.Combobox(controls, textvariable=self.x_var,
                                  state="readonly", width=42)
        self.x_box.grid(row=0, column=1, padx=(6, 12), sticky="we")

        self.x_auto = tk.BooleanVar(value=True)
        self.x_bound_vars, self.x_bound_entries = self._build_bound_row(
            controls, 0, self.x_auto, self._on_x_auto_toggle, pady=(0, 0))
        self.x_bound_entries.pop("check")   # the X row is always available

        ttk.Button(controls, text="Reload", command=self.reload).grid(
            row=0, column=4, padx=(12, 0), sticky="e")

        # Rows 1..N: one per Y series.  Series 1 is always on; the rest are
        # switched on by their check box.  Each row carries the bounds for
        # its own Y axis.
        self.y_vars = []
        self.y_boxes = []
        self.y_enabled = []
        self.y_auto = []
        self.y_auto_checks = []
        self.y_bound_vars = []
        self.y_bound_entries = []
        for i in range(N_Y_SERIES):
            row = i + 1
            var = tk.StringVar()
            enabled = tk.BooleanVar(value=(i == 0))
            if i == 0:
                ttk.Label(controls, text="Y axis 1:").grid(
                    row=row, column=0, sticky="w", pady=(6, 0))
            else:
                ttk.Checkbutton(
                    controls, text="Y axis {}:".format(i + 1),
                    variable=enabled,
                    command=lambda idx=i: self._on_y_toggle(idx),
                ).grid(row=row, column=0, sticky="w", pady=(6, 0))

            box = ttk.Combobox(controls, textvariable=var, width=42,
                               state="readonly" if i == 0 else "disabled")
            box.grid(row=row, column=1, padx=(6, 12), pady=(6, 0), sticky="we")
            box.bind("<<ComboboxSelected>>", lambda _e: self.draw())

            ttk.Label(controls,
                      text="—— {}".format(SERIES_COLOR_NAMES[i]),
                      foreground=SERIES_COLORS[i]).grid(
                          row=row, column=2, sticky="w", padx=(0, 14),
                          pady=(6, 0))

            auto = tk.BooleanVar(value=True)
            bound_vars, bound_entries = self._build_bound_row(
                controls, row, auto,
                lambda idx=i: self._on_y_auto_toggle(idx))

            self.y_vars.append(var)
            self.y_boxes.append(box)
            self.y_enabled.append(enabled)
            self.y_auto.append(auto)
            self.y_auto_checks.append(bound_entries.pop("check"))
            self.y_bound_vars.append(bound_vars)
            self.y_bound_entries.append(bound_entries)

        options = ttk.Frame(controls)
        options.grid(row=N_Y_SERIES + 1, column=0, columnspan=5, sticky="w",
                     pady=(10, 0))

        ttk.Label(options, text="Style:").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value="line")
        style_box = ttk.Combobox(options, textvariable=self.style_var,
                                 state="readonly", width=14,
                                 values=("line", "points", "line + points"))
        style_box.pack(side=tk.LEFT, padx=(6, 18))

        self.sort_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Sort by X", variable=self.sort_var,
                        command=self.draw).pack(side=tk.LEFT, padx=(0, 18))

        self.grid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="Grid", variable=self.grid_var,
                        command=self.draw).pack(side=tk.LEFT, padx=(0, 18))

        self.shared_y_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Share one Y axis (uses the Y1 bounds)",
                        variable=self.shared_y_var,
                        command=self._on_shared_toggle).pack(side=tk.LEFT)

        controls.columnconfigure(1, weight=1)

        self.x_box.bind("<<ComboboxSelected>>", lambda _e: self.draw())
        style_box.bind("<<ComboboxSelected>>", lambda _e: self.draw())

        # Status / warning lines
        status_frame = ttk.Frame(self, padding=(12, 0))
        status_frame.pack(side=tk.TOP, fill=tk.X)
        self.status_var = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=self.status_var,
                  foreground="#333333").pack(side=tk.LEFT)

        self.warn_var = tk.StringVar(value="")
        self.warn_label = tk.Label(self, textvariable=self.warn_var,
                                   fg="#8a5a00", bg="#fff4d6", anchor="w",
                                   padx=10, pady=4)

        # Plot area
        plot_frame = ttk.Frame(self)
        self.plot_frame = plot_frame
        plot_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True,
                        padx=8, pady=(6, 8))

        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.axes = self.figure.add_subplot(111)
        self.default_spine_color = matplotlib.rcParams["axes.edgecolor"]
        self.default_tick_color = matplotlib.rcParams["ytick.color"]
        self.default_tick_label_color = matplotlib.rcParams["ytick.labelcolor"]
        if self.default_tick_label_color == "inherit":
            self.default_tick_label_color = self.default_tick_color
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Margins are in points, so they have to be recomputed whenever the
        # window changes size.
        self.canvas.mpl_connect("resize_event", self._layout_axes)
        self._layout_axes()

        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        NavigationToolbar2Tk(self.canvas, toolbar_frame).update()

        self._refresh_bound_states()

    def _build_bound_row(self, parent, row, auto_var, command, pady=(6, 0)):
        """
        Build one axis' "auto / min / max" trio in column 2 of `parent`.

        Returns ({"min": var, "max": var},
                 {"min": entry, "max": entry, "check": checkbutton}).
        """
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=3, sticky="w", pady=pady)

        check = ttk.Checkbutton(frame, text="auto", variable=auto_var,
                                command=command)
        check.pack(side=tk.LEFT, padx=(0, 10))

        bound_vars = {}
        widgets = {"check": check}
        for key, text in (("min", "min:"), ("max", "max:")):
            ttk.Label(frame, text=text).pack(side=tk.LEFT, padx=(0, 3))
            var = tk.StringVar(value="")
            entry = ttk.Entry(frame, textvariable=var, width=10,
                              state="disabled")
            entry.pack(side=tk.LEFT, padx=(0, 10))
            entry.bind("<Return>", lambda _e: self.draw())
            entry.bind("<FocusOut>", lambda _e: self.draw())
            bound_vars[key] = var
            widgets[key] = entry
        return bound_vars, widgets

    # -- Data loading ------------------------------------------------------

    def reload(self):
        previous_x = self.x_var.get()
        previous_y = [var.get() for var in self.y_vars]

        self.datasets, self.load_errors = scan_logs(self.logs_dir)

        self.choices = {}
        labels = []
        for file_label, dataset in self.datasets.items():
            for column in dataset["columns"]:
                label = "{}  :  {}".format(file_label, column)
                self.choices[label] = (file_label, column)
                labels.append(label)

        x_values = [ROW_INDEX_LABEL] + labels
        self.x_box["values"] = x_values
        for box in self.y_boxes:
            box["values"] = labels

        if not labels:
            self.x_var.set("")
            for var in self.y_vars:
                var.set("")
            self._clear_plot("No data found.")
            if not self.logs_dir.is_dir():
                self.status_var.set(
                    "Folder not found: {}".format(self.logs_dir))
                messagebox.showwarning(
                    "Logs folder missing",
                    "No folder named '{}' next to this script.\n\n"
                    "Expected: {}\n\nCreate it, add your CSV files, "
                    "then press Reload.".format(LOGS_DIRNAME, self.logs_dir))
            else:
                self.status_var.set(
                    "No readable CSV files in {}".format(self.logs_dir))
            self._show_errors()
            return

        self.x_var.set(previous_x if previous_x in x_values else x_values[0])
        for i, var in enumerate(self.y_vars):
            if previous_y[i] in labels:
                var.set(previous_y[i])
            else:
                # Give the switched-off slots a sensible starting column so
                # ticking their box plots something straight away.
                var.set(labels[min(i, len(labels) - 1)])

        self.status_var.set(
            "Loaded {} file(s), {} column(s) from {}".format(
                len(self.datasets), len(labels), self.logs_dir))
        self._show_errors()
        self.draw()

    def _show_errors(self):
        if self.load_errors:
            summary = "; ".join(
                "{} ({})".format(name, msg) for name, msg in self.load_errors[:3])
            if len(self.load_errors) > 3:
                summary += "; +{} more".format(len(self.load_errors) - 3)
            self.load_warning = "Skipped {} file(s): {}".format(
                len(self.load_errors), summary)
        else:
            self.load_warning = ""
        self._warn("")

    # -- Axis controls -----------------------------------------------------

    def _slot_is_live(self, index):
        """True when Y slot `index` owns an axis the user can bound."""
        if self.shared_y_var.get():
            return index == 0        # one axis, driven by the Y1 row
        return index == 0 or self.y_enabled[index].get()

    def _on_y_toggle(self, index):
        """Show/hide one of the optional Y series."""
        self.y_boxes[index].configure(
            state="readonly" if self.y_enabled[index].get() else "disabled")
        self._refresh_bound_states()
        self.draw()

    def _on_shared_toggle(self):
        self._refresh_bound_states()
        self.draw()

    def _on_x_auto_toggle(self):
        if not self.x_auto.get():
            # Hand the user the bounds the automatic scaler just produced.
            self._store_limits(self.axes, "x", self.x_bound_vars)
        self._refresh_bound_states()
        self.draw()

    def _on_y_auto_toggle(self, index):
        if not self.y_auto[index].get():
            axes = self.slot_axes.get(index)
            if axes is not None:
                self._store_limits(axes, "y", self.y_bound_vars[index])
        self._refresh_bound_states()
        self.draw()

    def _refresh_bound_states(self):
        """Grey out every bound box that cannot affect the current plot."""
        state = "disabled" if self.x_auto.get() else "normal"
        for entry in self.x_bound_entries.values():
            entry.configure(state=state)

        for i in range(N_Y_SERIES):
            live = self._slot_is_live(i)
            self.y_auto_checks[i].configure(
                state="normal" if live else "disabled")
            state = "normal" if (live and not self.y_auto[i].get()) else "disabled"
            for entry in self.y_bound_entries[i].values():
                entry.configure(state=state)

    def _connect_limit_callbacks(self, axes_list):
        """
        Follow toolbar pans/zooms so the bound boxes always show what is
        currently on screen.  Axes.clear() throws the callback registry
        away, so this has to run again after every clear.
        """
        self.axes.callbacks.connect("xlim_changed", self._on_limits_changed)
        for axes in axes_list:
            axes.callbacks.connect("ylim_changed", self._on_limits_changed)

    def _on_limits_changed(self, _axes):
        if not self._drawing:
            self._sync_auto_entries()

    def _sync_auto_entries(self):
        """Copy the plot's limits into every box that is still automatic."""
        for axes, which, auto_var, bound_vars, _name in self.sync_targets:
            if auto_var.get():
                self._store_limits(axes, which, bound_vars)

    def _store_limits(self, axes, which, bound_vars):
        low, high = getattr(axes, "get_{}lim".format(which))()
        bound_vars["min"].set("{:.6g}".format(low))
        bound_vars["max"].set("{:.6g}".format(high))

    def _parse_bound(self, bound_var, name, notes):
        """Read one bound box; None means 'leave this limit automatic'."""
        text = bound_var.get().strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            notes.append("{} '{}' is not a number - that limit was left "
                         "automatic.".format(name, text))
            return None
        if math.isnan(value) or math.isinf(value):
            notes.append("{} must be a finite number - that limit was left "
                         "automatic.".format(name))
            return None
        return value

    def _apply_manual_bounds(self, notes):
        """Push every non-automatic min/max onto the axis that owns it."""
        for axes, which, auto_var, bound_vars, name in self.sync_targets:
            if auto_var.get():
                continue
            low_name = "{} min".format(name)
            high_name = "{} max".format(name)
            low = self._parse_bound(bound_vars["min"], low_name, notes)
            high = self._parse_bound(bound_vars["max"], high_name, notes)
            if low is None and high is None:
                continue

            current_low, current_high = getattr(
                axes, "get_{}lim".format(which))()
            new_low = current_low if low is None else low
            new_high = current_high if high is None else high
            if new_low == new_high:
                notes.append("{} and {} are equal - that axis was left "
                             "automatic.".format(low_name, high_name))
                continue
            getattr(axes, "set_{}lim".format(which))(new_low, new_high)

    # -- Axis layout -------------------------------------------------------

    def _reset_axes(self, count):
        """
        Tear down the previous twins and hand back `count` stacked Y axes.

        The first one is the host subplot (left edge); the rest are twinx
        axes whose spines are pushed outward so they do not overlap.
        """
        for axes in self.extra_axes:
            axes.remove()
        self.extra_axes = []

        self.axes.clear()
        # Axes.clear() resets neither spine colour/visibility nor the tick
        # colours set through tick_params(), so a previous multi-axis plot
        # would leave the host tinted.  Undo all of that by hand.
        self.axes.yaxis.tick_left()
        self.axes.yaxis.set_label_position("left")
        for spine in self.axes.spines.values():
            spine.set_visible(True)
            spine.set_color(self.default_spine_color)
        self.axes.tick_params(axis="y", color=self.default_tick_color,
                              labelcolor=self.default_tick_label_color)

        axes_list = [self.axes]
        for _ in range(count - 1):
            twin = self.axes.twinx()
            twin.grid(False)
            self.extra_axes.append(twin)
            axes_list.append(twin)

        n_left = n_right = 0
        for position, axes in enumerate(axes_list):
            side, level = AXIS_PLACEMENT[position]
            if side == "left":
                n_left += 1
            else:
                n_right += 1

            if axes is not self.axes:
                axes.yaxis.set_ticks_position(side)
                axes.yaxis.set_label_position(side)
                axes.yaxis.set_offset_position(side)
                for name, spine in axes.spines.items():
                    spine.set_visible(name == side)
            if level:
                axes.spines[side].set_position(("outward",
                                                level * SPINE_GAP_PTS))

        if count > 1:
            # The innermost right axis draws its own spine there.
            self.axes.spines["right"].set_visible(False)

        self.axis_counts = (n_left, n_right)
        self._connect_limit_callbacks(axes_list)
        self._layout_axes()
        return axes_list

    def _color_axis(self, position, axes, color):
        """Paint one Y axis in the colour of the series that owns it."""
        side = AXIS_PLACEMENT[position][0]
        axes.spines[side].set_color(color)
        axes.tick_params(axis="y", colors=color)
        axes.yaxis.label.set_color(color)

    def _layout_axes(self, _event=None):
        """
        Reserve room on each edge for the Y axes stacked against it.

        tight_layout() measures the artists it knows about and misses
        spines moved with set_position(("outward", ...)), so the margins
        are computed from the same point offsets used to place them.
        """
        n_left, n_right = self.axis_counts
        width_pts = max(self.figure.get_size_inches()[0] * 72.0, 1.0)
        height_pts = max(self.figure.get_size_inches()[1] * 72.0, 1.0)

        left = (EDGE_PAD_PTS + SPINE_GAP_PTS * max(n_left, 1)) / width_pts
        right = 1.0 - (EDGE_PAD_PTS + SPINE_GAP_PTS * n_right) / width_pts
        bottom = BOTTOM_PAD_PTS / height_pts
        top = 1.0 - TOP_PAD_PTS / height_pts

        # A tiny window must still leave a valid (non-inverted) plot area.
        if right - left < 0.2:
            middle = (left + right) / 2.0
            left, right = max(0.0, middle - 0.1), min(1.0, middle + 0.1)
        if top - bottom < 0.2:
            middle = (top + bottom) / 2.0
            bottom, top = max(0.0, middle - 0.1), min(1.0, middle + 0.1)

        self.figure.subplots_adjust(left=left, right=right,
                                    bottom=bottom, top=top)

    # -- Plotting ----------------------------------------------------------

    def _series(self, label):
        file_label, column = self.choices[label]
        return self.datasets[file_label]["columns"][column], file_label, column

    def _warn(self, message):
        parts = [p for p in (self.load_warning, message) if p]
        message = "  |  ".join(parts)
        self.warn_var.set(message)
        if message:
            self.warn_label.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(4, 0),
                                 before=self.plot_frame)
        else:
            self.warn_label.pack_forget()

    def _clear_plot(self, message):
        self._drawing = True
        try:
            self.slot_axes = {}
            self.sync_targets = []
            self._reset_axes(1)
            self.axes.text(0.5, 0.5, message, ha="center", va="center",
                           transform=self.axes.transAxes, color="#777777")
            self.axes.set_xticks([])
            self.axes.set_yticks([])
        finally:
            self._drawing = False
        self.canvas.draw_idle()

    def _pair(self, x_values, y_values):
        """
        Align one X/Y pair of columns.

        Invalid pairs become NaN so that line plots show gaps instead of
        connecting across missing data.  Returns (xs, ys, n, valid).
        """
        n = min(len(x_values), len(y_values))
        xs, ys = [], []
        valid = 0
        for i in range(n):
            xv, yv = x_values[i], y_values[i]
            if math.isnan(xv) or math.isnan(yv):
                xs.append(NAN)
                ys.append(NAN)
            else:
                xs.append(xv)
                ys.append(yv)
                valid += 1

        if self.sort_var.get():
            pairs = sorted((x, y) for x, y in zip(xs, ys)
                           if not math.isnan(x) and not math.isnan(y))
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]

        return xs, ys, n, valid

    def _active_y_labels(self, notes):
        """The (slot index, dropdown label) pairs that should be plotted."""
        active = []
        for index, var in enumerate(self.y_vars):
            if index and not self.y_enabled[index].get():
                continue
            label = var.get()
            if label in self.choices:
                active.append((index, label))
            elif index:
                notes.append("Y axis {} is switched on but has no column "
                             "selected.".format(index + 1))
        return active

    def _build_sync_targets(self, shared, prepared, axes_list):
        """
        Decide which bound row drives which axis.

        Sharing collapses everything onto the host axes, so only the Y1 row
        is meaningful; otherwise each plotted series owns its own axis.
        """
        self.slot_axes = {}
        if shared:
            self.slot_axes[0] = axes_list[0]
        else:
            for position, entry in enumerate(prepared):
                self.slot_axes[entry["slot"]] = axes_list[position]

        self.sync_targets = [
            (self.axes, "x", self.x_auto, self.x_bound_vars, "X")]
        for slot, axes in sorted(self.slot_axes.items()):
            name = "Y" if shared else "Y {}".format(slot + 1)
            self.sync_targets.append(
                (axes, "y", self.y_auto[slot], self.y_bound_vars[slot], name))

    def draw(self):
        x_label = self.x_var.get()

        notes = []
        active = self._active_y_labels(notes)
        if not active:
            self._clear_plot("Select a Y column.")
            self._warn(" | ".join(notes))
            return
        if x_label != ROW_INDEX_LABEL and x_label not in self.choices:
            self._clear_plot("Select an X column.")
            return

        use_row_index = (x_label == ROW_INDEX_LABEL)
        if use_row_index:
            x_column, x_title = "row index", "row index"
            x_values, x_file = None, None
        else:
            x_values, x_file, x_column = self._series(x_label)
            x_title = "{}  [{}]".format(x_column, x_file)

        # Pair everything up first: how many axes are needed depends on how
        # many series actually survive the pairing.
        prepared = []
        total_rows = 0
        mixed_files = set()
        for slot, label in active:
            y_values, y_file, y_column = self._series(label)
            if use_row_index:
                series_x = [float(i) for i in range(len(y_values))]
            else:
                series_x = x_values
                if x_file != y_file:
                    mixed_files.add(y_file)
                if len(series_x) != len(y_values):
                    notes.append(
                        "Y axis {} column lengths differ ({} X rows vs {} Y "
                        "rows); using the first {} of each.".format(
                            slot + 1, len(series_x), len(y_values),
                            min(len(series_x), len(y_values))))

            xs, ys, n, valid = self._pair(series_x, y_values)
            total_rows = max(total_rows, n)
            if valid == 0:
                notes.append(
                    "Y axis {} ({}) has no row where both columns hold a "
                    "valid number.".format(slot + 1, y_column))
                continue
            prepared.append({"slot": slot, "xs": xs, "ys": ys, "n": n,
                             "valid": valid, "column": y_column,
                             "file": y_file})

        if not prepared:
            self._clear_plot("No rows where both columns hold a valid number.")
            self.status_var.set(
                "0 of {:,} rows plottable - every pair had missing or "
                "non-numeric data.".format(total_rows))
            self._warn(" | ".join(notes))
            return

        style = self.style_var.get()
        if style == "points":
            fmt, kwargs = ".", {"markersize": 3, "linestyle": "none"}
        elif style == "line + points":
            fmt, kwargs = "-", {"marker": ".", "markersize": 3, "linewidth": 1.0}
        else:
            fmt, kwargs = "-", {"linewidth": 1.0}

        shared = self.shared_y_var.get()
        self._drawing = True
        try:
            axes_list = self._reset_axes(1 if shared else len(prepared))

            for position, entry in enumerate(prepared):
                axes = axes_list[0] if shared else axes_list[position]
                color = SERIES_COLORS[entry["slot"]]
                axes.plot(entry["xs"], entry["ys"], fmt, color=color, **kwargs)
                if not shared:
                    axes.set_ylabel(shorten("{}  [{}]".format(
                        entry["column"], entry["file"]), 42))
                    if len(prepared) > 1:
                        self._color_axis(position, axes, color)

            columns = [entry["column"] for entry in prepared]
            if shared:
                if len(prepared) == 1:
                    self.axes.set_ylabel("{}  [{}]".format(
                        prepared[0]["column"], prepared[0]["file"]))
                else:
                    # One axis holding several series can only name them
                    # all; the colour swatches beside the dropdowns say
                    # which curve is which.
                    self.axes.set_ylabel(shorten(", ".join(columns)))

            self.axes.set_xlabel(x_title)
            self.axes.set_title(shorten("{} vs {}".format(
                ", ".join(columns), x_column), 80))
            self.axes.grid(self.grid_var.get(), alpha=0.3)

            # Settle the automatic limits before reading them, so that a row
            # with only one manual box keeps a true automatic other half.
            for axes in axes_list:
                axes.autoscale_view()

            self._build_sync_targets(shared, prepared, axes_list)
            self._apply_manual_bounds(notes)
            self._sync_auto_entries()
        finally:
            self._drawing = False

        self.canvas.draw_idle()

        if mixed_files:
            notes.append(
                "X and Y come from different files ({} and {}). They are "
                "paired by row number only - this is meaningful only if the "
                "rows correspond.".format(x_file, ", ".join(sorted(mixed_files))))

        if len(prepared) == 1:
            valid, n = prepared[0]["valid"], prepared[0]["n"]
            message = "Plotted {:,} of {:,} rows.".format(valid, n)
            dropped = n - valid
            if dropped:
                message += ("  {:,} dropped (missing or non-numeric in X or "
                            "Y).".format(dropped))
        else:
            message = "Plotted {} series on {}: {}.".format(
                len(prepared),
                "one shared Y axis" if shared else "separate Y axes",
                ";  ".join("{} = {:,} of {:,} rows".format(
                    entry["column"], entry["valid"], entry["n"])
                    for entry in prepared))
        total_valid = sum(entry["valid"] for entry in prepared)
        if total_valid > 50000:
            message += "  Large series - zooming may be slow."
        self.status_var.set(message)
        self._warn(" | ".join(notes))


def main():
    script_dir = Path(__file__).resolve().parent
    logs_dir = script_dir / LOGS_DIRNAME
    app = LogPlotter(logs_dir)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

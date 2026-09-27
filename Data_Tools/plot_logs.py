#!/usr/bin/env python3
"""
plot_logs.py - a single-file CSV log plotter.

RUN
    python plot_logs.py                        then click "Open CSV..."
    python plot_logs.py run1.csv model.csv     opens these straight away

    On Windows you can also drag CSV files onto plot_logs.py in Explorer.

REQUIREMENTS
    Python 3.8+
    matplotlib          ->  pip install matplotlib
    tkinter             ->  ships with Python on Windows/macOS.
                            On Debian/Ubuntu: sudo apt install python3-tk

OPENING FILES
    "Open CSV..." (Ctrl+O) opens the system file browser.  Pick one file or
    several at once (Ctrl/Shift-click), and open it again to add more.  Every
    open file is listed in the Files panel with its size and folder, and
    each one has:
        X column  - what this file's curves are plotted against
        X offset  - added to this file's X values, to line two runs up
        Reload    - read this file from disk again
        Remove    - take it out of the analysis
    "Reload all" (F5) reads every file again and "Remove all" closes them.
    Opening a file that is already open just reloads it.

    Files stay open until you remove them.  Each file is checked once a
    second, and one that has changed on disk is marked "Changed on disk".
    If "Reload automatically" is ticked it is reloaded straight away
    instead, which lets you watch a log that is still being written.  If a
    reload fails (the file was deleted, is half written, or is locked) the
    last good data stays on screen and the file's row says why.

    Two open files with the same name are told apart by their folder, e.g.
    Dirt26_1/main_loop_log.csv and Dirt27_1/main_loop_log.csv.

COMPARING FILES
    Each file has its own X column, so a dyno log with time_s and a model
    log with timestep share one X axis.  Rows from different files are never
    paired with each other: each curve is one file's Y column against that
    same file's X column.  Use a file's X offset to shift it along X until
    the runs line up.

    With "Line style per file" ticked, the 1st file's curves are solid, the
    2nd file's dashed, the 3rd's dotted and the 4th's dash-dot.  In "points"
    mode the files use different markers instead.  The mark beside each
    file name shows which is which.

Y AXES
    "Y axes" (1-10) sets how many Y rows are shown.  Each row picks a file,
    then a column from that file.  When you switch a row to another file,
    it keeps the column if the new file has one with the same name
    (ignoring case), so plotting "ratio" from the dyno and then the model is
    one click.  Hidden rows keep their choices, so lowering the number and
    raising it again brings them back.

    By default each row gets its OWN Y axis, so series with very different
    magnitudes stay readable.  Axes go on alternate sides, left then right,
    each new pair stacked further out.  Each axis - its spine, ticks and
    label - is drawn in the colour of the series that owns it.

    Setting a row's "Axis" to an earlier row ("same as Y1", ...) puts both
    series on ONE axis with one scale.  Use it to overlay a measured value
    and the model's value of the same quantity.  An axis that carries
    several series is drawn in black and its label lists all of them.
    "Share one Y axis" puts every series on a single axis.

    There is no legend, because it covers the curves.  Instead each Y row's
    name (Y1, Y2, ...) is drawn in its curve's colour.

AXIS BOUNDS
    Every axis has its own "auto" tick box plus min / max boxes: the X axis
    on the X row, then one row per Y axis.  There is only ever one X axis,
    shared by every file.

    While "auto" is ticked, that row's two boxes mirror whatever is on
    screen - including toolbar pans and zooms - so un-ticking the box hands
    you the current view to edit.  Clearing one box leaves that single
    limit automatic, e.g. min 0 with an empty max pins the bottom and lets
    the top follow the data.

    Because bounds belong to axes, Y1 can be pinned to 0..100 while Y2
    scales itself.  A row that shares another row's axis uses that row's
    bounds, and its own boxes grey out.  In "Share one Y axis" mode the Y1
    row drives the single shared axis.

LAYOUT
    The controls sit above the plot in a panel that scrolls with the mouse
    wheel.  Click the "Files" or "Plot" heading to collapse that section,
    and click it again to open it; the plot grows into the room it frees.
    Drag the divider between the controls and the plot to give either one
    more room; double-click the divider (or collapse / open a section) to
    return to automatic sizing.

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
    seconds.  Apart from that and the X offset, values are plotted as read.
"""

import csv
import io
import math
import os
import re
import sys
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

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

FILE_TYPES = (("CSV / log files", "*.csv *.tsv *.txt"), ("All files", "*.*"))

# How often open files are checked for changes on disk.
POLL_MS = 1000

# How many Y series can be plotted at once, and the colour of each slot.
# Slot colours are fixed so a series keeps its colour when the number of
# rows changes.
MAX_Y_AXES = 10
SERIES_COLORS = ("#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
                 "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf")

# How the n-th open file's curves are drawn when "Line style per file" is
# on: (matplotlib linestyle, marker, glyph for line modes, glyph for points
# mode).  A fifth file starts the cycle again.
FILE_STYLES = (
    ("-", ".", "———", "• • •"),
    ("--", "x", "– – –", "× × ×"),
    (":", "+", "·······", "+ + +"),
    ("-.", "^", "–·–·–", "▴ ▴ ▴"),
)

# The "Axis" dropdown value for a row that owns its own Y axis.  The other
# values are "same as Y1", "same as Y2", ...
OWN_AXIS = "own"
SAME_AS_PREFIX = "same as Y"

# Figure margins, in points.  Offset spines are positioned in points too,
# so reserving room for them means simple arithmetic - and it is why this
# file sets the margins by hand instead of calling tight_layout(), which
# does not account for spines pushed outward.
SPINE_GAP_PTS = 58.0      # room for one Y axis: ticks, numbers and label
EDGE_PAD_PTS = 14.0       # breathing room outside the outermost axis
BOTTOM_PAD_PTS = 46.0     # X ticks + X label
TOP_PAD_PTS = 34.0        # title

# While the controls panel sizes itself, it may take at most this share of
# the window's height; beyond that it scrolls.
MAX_CONTROLS_FRACTION = 0.55

MUTED = "#777777"
ERROR_COLOR = "#b00020"
CHANGED_COLOR = "#a05a00"


def axis_placement(position):
    """
    Where the n-th drawn Y axis goes: which side of the plot, and how many
    steps outward from that side.  Alternating sides keeps the plot area as
    wide as possible instead of pushing every axis off one edge.
    """
    return ("left" if position % 2 == 0 else "right"), position // 2


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


def shorten_left(text, limit=60):
    """Trim from the front, keeping the end of a long folder path."""
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


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


def read_dataset(path):
    """
    Load one CSV for the app, never raising.

    Returns ((columns, n_rows), "") on success, or (None, reason).
    """
    try:
        columns, rows = load_csv(path)
    except FileNotFoundError:
        return None, "file not found"
    except PermissionError:
        return None, "permission denied - is it open in another program?"
    except OSError as exc:
        return None, "could not read: {}".format(exc.strerror or exc)
    except Exception as exc:  # keep one bad file from killing the app
        return None, "{}: {}".format(type(exc).__name__, exc)
    if not columns:
        return None, "empty or no header row"
    if rows == 0:
        return None, "header only, no data rows"
    return (columns, rows), ""


def file_stamp(path):
    """(modification time, size) of a file, or None if it cannot be seen."""
    try:
        info = path.stat()
    except OSError:
        return None
    return info.st_mtime_ns, info.st_size


def path_key(path):
    """A file's identity, so opening the same file twice is spotted."""
    return os.path.normcase(str(path))


# --------------------------------------------------------------------------
# Data holders
# --------------------------------------------------------------------------

class LoadedFile:
    """One CSV the user opened, with the settings in its Files-panel row."""

    def __init__(self, file_id, path, master):
        self.id = file_id
        self.path = path
        self.label = path.name        # made unique by LogPlotter._relabel_files
        self.columns = {}             # name -> [float, ...]
        self.names = []               # column names in file order
        self.rows = 0
        self.stamp = None             # file_stamp() when last read
        self.disk_stamp = None        # file_stamp() at the latest check
        self.error = ""               # why the last read failed, if it did
        self.x_var = tk.StringVar(master=master)
        self.offset_var = tk.StringVar(master=master)
        self.widgets = {}             # its row in the Files panel

    def load(self):
        """(Re)read the file.  On failure keep the old data; return why."""
        # Stamp before reading, so a write that lands mid-read is still
        # seen as a change afterwards.
        stamp = file_stamp(self.path)
        data, error = read_dataset(self.path)
        self.stamp = self.disk_stamp = stamp
        if error:
            self.error = error
            return error
        self.columns, self.rows = data
        self.names = list(self.columns)
        self.error = ""
        return ""


class YRow:
    """
    The widgets and settings of one Y series row.

    file_id is the LoadedFile.id the row plots from (None for no file).
    The file dropdown only displays that file's label, because labels can
    change when other files with the same name are opened or removed.
    """

    def __init__(self):
        self.file_id = None
        self.file_var = None
        self.file_box = None
        self.column_var = None
        self.column_box = None
        self.axis_var = None
        self.axis_box = None
        self.auto = None
        self.auto_check = None
        self.bound_vars = None
        self.bound_entries = None
        self.widgets = ()             # everything hidden with the row


class ScrollFrame(ttk.Frame):
    """A vertically scrolling frame.  Put its contents in .inner."""

    def __init__(self, parent, **inner_options):
        super().__init__(parent)
        background = ttk.Style(self).lookup("TFrame", "background")
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                yscrollincrement=12)
        if background:
            self.canvas.configure(background=background)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL,
                                       command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = ttk.Frame(self.canvas, **inner_options)
        self._window = self.canvas.create_window(0, 0, window=self.inner,
                                                 anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # The contents always span the full width; only height scrolls.
        self.canvas.itemconfigure(self._window, width=event.width)

    def contains(self, widget):
        """True when `widget` sits inside the scrolling area."""
        path = str(widget)
        root = str(self.canvas)
        return path == root or path.startswith(root + ".")

    def scroll(self, event):
        """Scroll for one mouse-wheel event (Windows, macOS or X11)."""
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            return
        if event.num == 4:
            steps = -1
        elif event.num == 5:
            steps = 1
        elif event.delta:
            steps = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
        else:
            return
        self.canvas.yview_scroll(steps * 3, "units")


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

class LogPlotter(tk.Tk):

    def __init__(self, initial_paths=()):
        super().__init__()
        self.title("CSV Log Plotter")
        self.geometry("1400x920")
        self.minsize(1040, 620)

        self.files = []          # LoadedFile, in the order they were opened
        self._next_file_id = 1
        self.last_dir = Path.cwd()
        self.load_warning = ""   # from the last open; stays across plots

        self.y_rows = []
        self.y_count = 1

        self.extra_axes = []     # twinned Y axes, rebuilt on every draw
        self.slot_axes = {}      # owning Y slot index -> its axes
        self.sync_targets = []   # (axes, "x"/"y", auto_var, bound_vars, name)
        self.axis_counts = (1, 0)   # Y axes on the (left, right) edge
        self.plot_size_pts = (1.0, 1.0)   # plot area (width, height)
        self.label_texts = {"title": "", "x": "", "y": []}   # untrimmed
        self._drawing = False    # ignore limit callbacks while we redraw

        self._controls_user_sized = False
        self._fit_pending = False
        self._sash_at_press = None

        self._build_ui()
        if initial_paths:
            self.add_files(initial_paths)
        else:
            self._after_files_changed()
        self.after(POLL_MS, self._poll_files)

    # -- UI construction ---------------------------------------------------

    def _build_ui(self):
        self.bold_font = tkfont.nametofont("TkDefaultFont").copy()
        self.bold_font.configure(weight="bold")

        # Controls on top, plot below, with a draggable divider between.
        self.paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        self.paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.scroller = ScrollFrame(self.paned, padding=(10, 8, 10, 6))
        self.paned.add(self.scroller, weight=0)
        self._build_file_section(self.scroller.inner)
        self._build_plot_section(self.scroller.inner)

        bottom = ttk.Frame(self.paned)
        self.paned.add(bottom, weight=1)
        self._build_plot_area(bottom)

        # Size the controls pane to its contents until the user drags the
        # divider; double-clicking the divider hands sizing back.
        self.paned.bind("<Configure>", self._fit_controls, add="+")
        self.scroller.inner.bind("<Configure>", self._fit_controls, add="+")
        self.paned.bind("<ButtonPress-1>", self._on_sash_press)
        self.paned.bind("<ButtonRelease-1>", self._on_sash_release)
        self.paned.bind("<Double-Button-1>", self._on_sash_reset)

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, self._on_mousewheel, add="+")

        self.bind("<Control-o>", lambda _e: self.open_files())
        self.bind("<Control-O>", lambda _e: self.open_files())
        self.bind("<F5>", lambda _e: self.reload_all())

        self._show_y_rows()
        self._refresh_bound_states()

    def _build_section(self, parent, title, pady):
        """
        A labelled box whose heading collapses and opens it.  Returns the
        frame to put the section's contents in.
        """
        box = ttk.LabelFrame(parent, padding=(8, 4, 8, 6))
        box.pack(side=tk.TOP, fill=tk.X, pady=pady)
        header = ttk.Label(box, font=self.bold_font, cursor="hand2")
        box.configure(labelwidget=header)

        body = ttk.Frame(box)
        body.pack(side=tk.TOP, fill=tk.X)
        # pack leaves a master at its old size once its last child goes, so
        # a collapsed box keeps this sliver packed in place of the body.
        placeholder = ttk.Frame(box, height=1)

        section = {"title": title, "open": True, "header": header,
                   "body": body, "placeholder": placeholder}
        header.bind("<Button-1>", lambda _e: self._toggle_section(section))
        self._set_section_header(section)
        return body

    def _set_section_header(self, section):
        section["header"].configure(text="{}  {}".format(
            "▾" if section["open"] else "▸", section["title"]))

    def _toggle_section(self, section):
        section["open"] = not section["open"]
        if section["open"]:
            section["placeholder"].pack_forget()
            section["body"].pack(side=tk.TOP, fill=tk.X)
        else:
            section["body"].pack_forget()
            section["placeholder"].pack(side=tk.TOP, fill=tk.X)
        self._set_section_header(section)
        # Resize the controls to fit, so the plot takes the room freed.
        self._controls_user_sized = False
        self._fit_controls()

    def _build_file_section(self, parent):
        box = self._build_section(parent, "Files", 0)

        bar = ttk.Frame(box)
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(bar, text="Open CSV…", command=self.open_files).pack(
            side=tk.LEFT)
        self.reload_all_button = ttk.Button(bar, text="Reload all",
                                            command=self.reload_all)
        self.reload_all_button.pack(side=tk.LEFT, padx=(8, 0))
        self.remove_all_button = ttk.Button(bar, text="Remove all",
                                            command=self.remove_all)
        self.remove_all_button.pack(side=tk.LEFT, padx=(8, 0))

        self.auto_reload_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar, text="Reload automatically when a file changes on disk",
            variable=self.auto_reload_var,
            command=self._on_auto_reload_toggle,
        ).pack(side=tk.LEFT, padx=(18, 0))
        ttk.Label(bar, text="Ctrl+O  open      F5  reload all",
                  foreground=MUTED).pack(side=tk.RIGHT)

        self.file_grid = ttk.Frame(box)
        self.file_grid.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))

    def _build_plot_section(self, parent):
        box = self._build_section(parent, "Plot", (8, 0))

        options = ttk.Frame(box)
        options.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(options, text="Y axes:", font=self.bold_font).pack(
            side=tk.LEFT)
        self.count_var = tk.StringVar(value=str(self.y_count))
        spin = ttk.Spinbox(options, from_=1, to=MAX_Y_AXES, increment=1,
                           width=4, textvariable=self.count_var,
                           command=self._on_count_change)
        spin.pack(side=tk.LEFT, padx=(6, 4))
        spin.bind("<Return>", self._on_count_change)
        spin.bind("<FocusOut>", self._on_count_change)
        ttk.Label(options, text="(1–{})".format(MAX_Y_AXES),
                  foreground=MUTED).pack(side=tk.LEFT, padx=(0, 22))

        ttk.Label(options, text="Style:").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value="line")
        style_box = ttk.Combobox(options, textvariable=self.style_var,
                                 state="readonly", width=14,
                                 values=("line", "points", "line + points"))
        style_box.pack(side=tk.LEFT, padx=(6, 18))
        style_box.bind("<<ComboboxSelected>>", lambda _e: self._on_style_change())
        self._guard_wheel(style_box)

        self.sort_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Sort by X", variable=self.sort_var,
                        command=self.draw).pack(side=tk.LEFT, padx=(0, 18))

        self.grid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="Grid", variable=self.grid_var,
                        command=self.draw).pack(side=tk.LEFT, padx=(0, 18))

        self.per_file_style_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="Line style per file",
                        variable=self.per_file_style_var,
                        command=self._on_style_change).pack(
                            side=tk.LEFT, padx=(0, 18))

        self.shared_y_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Share one Y axis (uses the Y1 bounds)",
                        variable=self.shared_y_var,
                        command=self._on_shared_toggle).pack(side=tk.LEFT)

        # One grid for the X row and every Y row, so their columns line up.
        grid = ttk.Frame(box)
        grid.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        for column, text in enumerate(
                ("", "File", "Column", "Axis", "Bounds")):
            if text:
                ttk.Label(grid, text=text, foreground=MUTED).grid(
                    row=0, column=column, sticky="w", padx=(0, 10))

        ttk.Label(grid, text="X", font=self.bold_font).grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(4, 0))
        ttk.Label(grid, foreground=MUTED,
                  text="Each file's X column and offset are set in the "
                       "Files list above.").grid(
            row=1, column=1, columnspan=3, sticky="w", pady=(4, 0))
        self.x_auto = tk.BooleanVar(value=True)
        self.x_bound_vars, self.x_bound_entries = self._build_bound_row(
            grid, 1, self.x_auto, self._on_x_auto_toggle)
        # The X row is always available, and never hidden.
        self.x_bound_entries.pop("check")
        self.x_bound_entries.pop("frame")

        for index in range(MAX_Y_AXES):
            self.y_rows.append(self._build_y_row(grid, index, index + 2))

    def _build_y_row(self, grid, index, grid_row):
        row = YRow()
        name = ttk.Label(grid, text="Y{}".format(index + 1),
                         foreground=SERIES_COLORS[index], font=self.bold_font)

        row.file_var = tk.StringVar()
        row.file_box = ttk.Combobox(grid, textvariable=row.file_var,
                                    state="readonly", width=28)
        row.file_box.bind("<<ComboboxSelected>>",
                          lambda _e, i=index: self._on_y_file_selected(i))

        row.column_var = tk.StringVar()
        row.column_box = ttk.Combobox(grid, textvariable=row.column_var,
                                      state="readonly", width=34)
        row.column_box.bind("<<ComboboxSelected>>", lambda _e: self.draw())

        # Only earlier rows are offered, so sharing can never form a loop.
        row.axis_var = tk.StringVar(value=OWN_AXIS)
        row.axis_box = ttk.Combobox(
            grid, textvariable=row.axis_var, state="readonly", width=11,
            values=[OWN_AXIS] + ["{}{}".format(SAME_AS_PREFIX, j + 1)
                                 for j in range(index)])
        row.axis_box.bind("<<ComboboxSelected>>",
                          lambda _e: self._on_axis_change())

        row.auto = tk.BooleanVar(value=True)
        row.bound_vars, entries = self._build_bound_row(
            grid, grid_row, row.auto,
            lambda i=index: self._on_y_auto_toggle(i))
        row.auto_check = entries.pop("check")
        bound_frame = entries.pop("frame")
        row.bound_entries = entries

        for column, widget in enumerate((name, row.file_box, row.column_box,
                                         row.axis_box)):
            widget.grid(row=grid_row, column=column, sticky="w",
                        padx=(0, 10), pady=(4, 0))
        for box in (row.file_box, row.column_box, row.axis_box):
            self._guard_wheel(box)

        row.widgets = (name, row.file_box, row.column_box, row.axis_box,
                       bound_frame)
        return row

    def _build_bound_row(self, parent, row, auto_var, command):
        """
        Build one axis' "auto / min / max" trio in the Bounds column.

        Returns ({"min": var, "max": var},
                 {"min": entry, "max": entry, "check": checkbutton,
                  "frame": frame}).
        """
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=4, sticky="w", pady=(4, 0))

        check = ttk.Checkbutton(frame, text="auto", variable=auto_var,
                                command=command)
        check.pack(side=tk.LEFT, padx=(0, 10))

        bound_vars = {}
        widgets = {"check": check, "frame": frame}
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

    def _build_plot_area(self, parent):
        # Status / warning lines
        status_frame = ttk.Frame(parent, padding=(12, 4, 12, 0))
        status_frame.pack(side=tk.TOP, fill=tk.X)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var,
                                      foreground="#333333", justify=tk.LEFT)
        self.status_label.pack(side=tk.LEFT)

        self.warn_var = tk.StringVar(value="")
        self.warn_label = tk.Label(parent, textvariable=self.warn_var,
                                   fg="#8a5a00", bg="#fff4d6", anchor="w",
                                   justify=tk.LEFT, padx=10, pady=4)

        # Long messages wrap instead of running off the window.
        def wrap(event):
            width = max(200, event.width - 40)
            self.status_label.configure(wraplength=width)
            self.warn_label.configure(wraplength=width)
        parent.bind("<Configure>", wrap)

        # Plot area
        plot_frame = ttk.Frame(parent)
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

        # Pack the toolbar first so a short window squeezes the plot, not
        # the toolbar.
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        NavigationToolbar2Tk(self.canvas, toolbar_frame).update()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Margins are in points, so they have to be recomputed whenever the
        # plot changes size.
        self.canvas.mpl_connect("resize_event", self._layout_axes)
        self._layout_axes()

    # -- Controls panel sizing and scrolling -------------------------------

    def _sash_position(self):
        try:
            return self.paned.sashpos(0)
        except tk.TclError:
            return None

    def _on_sash_press(self, _event):
        self._sash_at_press = self._sash_position()

    def _on_sash_release(self, _event):
        # Only a real drag counts; a plain click (or double-click) does not.
        if self._sash_position() != self._sash_at_press:
            self._controls_user_sized = True

    def _on_sash_reset(self, _event):
        self._controls_user_sized = False
        self._fit_controls()

    def _fit_controls(self, _event=None):
        """Size the controls pane to its contents, once things settle."""
        if self._controls_user_sized or self._fit_pending:
            return
        self._fit_pending = True
        self.after_idle(self._do_fit_controls)

    def _do_fit_controls(self):
        self._fit_pending = False
        if self._controls_user_sized:
            return
        total = self.paned.winfo_height()
        if total < 100:
            return   # not laid out yet; the next <Configure> retries
        wanted = self.scroller.inner.winfo_reqheight() + 2
        position = max(60, min(wanted, int(total * MAX_CONTROLS_FRACTION)))
        if self._sash_position() != position:
            try:
                self.paned.sashpos(0, position)
            except tk.TclError:
                pass

    def _on_mousewheel(self, event):
        """Scroll the controls panel when the wheel turns over it."""
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return   # e.g. an open dropdown list, which scrolls itself
        if widget is None or not self.scroller.contains(widget):
            return
        if widget.winfo_class() == "TSpinbox":
            return   # the wheel steps the spinbox instead
        self.scroller.scroll(event)

    def _guard_wheel(self, box):
        """
        Make the wheel scroll the panel past a dropdown instead of silently
        changing the dropdown's value, which is ttk's default.
        """
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            box.bind(sequence, self._on_wheel_over_dropdown)

    def _on_wheel_over_dropdown(self, event):
        self._on_mousewheel(event)
        return "break"

    # -- Files -------------------------------------------------------------

    def _file_by_id(self, file_id):
        for f in self.files:
            if f.id == file_id:
                return f
        return None

    def _file_by_label(self, label):
        for f in self.files:
            if f.label == label:
                return f
        return None

    def _file_by_path(self, path):
        key = path_key(path)
        for f in self.files:
            if path_key(f.path) == key:
                return f
        return None

    def open_files(self):
        paths = filedialog.askopenfilenames(
            parent=self, title="Open CSV file(s)",
            initialdir=str(self.last_dir), filetypes=FILE_TYPES)
        # Some Tk builds hand back one brace-quoted string, not a tuple.
        paths = self.tk.splitlist(paths) if paths else ()
        if paths:
            self.add_files(paths)

    def add_files(self, raw_paths):
        """Open each path, or reload it if it is already open."""
        problems = []
        added = []
        for raw in raw_paths:
            path = Path(raw).expanduser()
            try:
                path = path.resolve()
            except OSError:
                pass

            existing = self._file_by_path(path)
            if existing is not None:
                # A failed reload is reported on the file's own row.
                if not existing.load():
                    problems.append("{} was already open - reloaded it".format(
                        existing.label))
                continue

            f = LoadedFile(self._next_file_id, path, self)
            error = f.load()
            if error:
                problems.append("Could not open {} ({})".format(path.name, error))
                continue
            self._next_file_id += 1
            f.x_var.set(f.names[0])     # usually the time column
            self.files.append(f)
            added.append(f)
            self.last_dir = path.parent

        for f in added:
            self._assign_default_columns(f)
        self.load_warning = "; ".join(problems)
        self._after_files_changed()

    def reload_files(self, files):
        """Read `files` again, keeping every selection that still applies."""
        for f in files:
            f.load()
            self._update_file_row(f)
        self._refresh_y_choices()
        self.draw()

    def reload_all(self):
        if self.files:
            self.load_warning = ""
            self.reload_files(list(self.files))

    def remove_file(self, f):
        if f in self.files:
            self.files.remove(f)
            self.load_warning = ""
            self._after_files_changed()

    def remove_all(self):
        self.files = []
        self.load_warning = ""
        self._after_files_changed()

    def _on_auto_reload_toggle(self):
        if self.auto_reload_var.get():
            stale = [f for f in self.files
                     if f.disk_stamp is not None and f.disk_stamp != f.stamp]
            if stale:
                self.reload_files(stale)

    def _poll_files(self):
        """Check each open file for changes on disk, once a second."""
        try:
            to_reload = []
            for f in self.files:
                stamp = file_stamp(f.path)
                if stamp == f.disk_stamp:
                    continue
                f.disk_stamp = stamp
                if (self.auto_reload_var.get() and stamp is not None
                        and stamp != f.stamp):
                    to_reload.append(f)
                else:
                    self._update_file_row(f)
            if to_reload:
                self.reload_files(to_reload)
        finally:
            self.after(POLL_MS, self._poll_files)

    def _relabel_files(self):
        """
        Name each file by the shortest tail of its path that no other open
        file shares: run1.csv, or Dirt27_1/main_loop_log.csv when two files
        are both called main_loop_log.csv.
        """
        for f in self.files:
            parts = f.path.parts
            depth = 1
            while depth < len(parts) and any(
                    other is not f and other.path.parts[-depth:] == parts[-depth:]
                    for other in self.files):
                depth += 1
            f.label = "/".join(parts[-depth:])

    def _after_files_changed(self):
        """Bring every view of the file list up to date after open/remove."""
        self._relabel_files()
        self._rebuild_file_panel()
        self._refresh_y_choices()
        self._refresh_file_glyphs()
        count = len(self.files)
        self.title("CSV Log Plotter" if not count else
                   "CSV Log Plotter - {} file{}".format(
                       count, "" if count == 1 else "s"))
        self.draw()
        self._fit_controls()

    def _rebuild_file_panel(self):
        for child in self.file_grid.winfo_children():
            child.destroy()
        state = "normal" if self.files else "disabled"
        self.reload_all_button.configure(state=state)
        self.remove_all_button.configure(state=state)

        if not self.files:
            ttk.Label(self.file_grid, foreground=MUTED,
                      text="No files open.  Click “Open CSV…” and pick one or "
                           "more files (Ctrl/Shift-click to select several)."
                      ).grid(row=0, column=0, sticky="w")
            return

        headers = ("", "File", "Size", "X column", "X offset", "", "", "",
                   "Folder")
        for column, text in enumerate(headers):
            if text:
                ttk.Label(self.file_grid, text=text, foreground=MUTED).grid(
                    row=0, column=column, sticky="w", padx=(0, 10))

        for grid_row, f in enumerate(self.files, start=1):
            w = {
                "glyph": ttk.Label(self.file_grid, width=8,
                                   foreground="#444444"),
                "name": ttk.Label(self.file_grid, text=shorten(f.label, 44),
                                  font=self.bold_font),
                "size": ttk.Label(self.file_grid),
                "x": ttk.Combobox(self.file_grid, textvariable=f.x_var,
                                  state="readonly", width=30),
                "offset": ttk.Entry(self.file_grid, textvariable=f.offset_var,
                                    width=9),
                "reload": ttk.Button(self.file_grid, text="Reload", width=7,
                                     command=lambda f=f: self.reload_files([f])),
                "remove": ttk.Button(self.file_grid, text="Remove", width=7,
                                     command=lambda f=f: self.remove_file(f)),
                "status": ttk.Label(self.file_grid),
                "folder": ttk.Label(self.file_grid, foreground=MUTED),
            }
            w["x"].bind("<<ComboboxSelected>>", lambda _e: self.draw())
            self._guard_wheel(w["x"])
            w["offset"].bind("<Return>", lambda _e: self.draw())
            w["offset"].bind("<FocusOut>", lambda _e: self.draw())

            for column, key in enumerate(("glyph", "name", "size", "x",
                                          "offset", "reload", "remove",
                                          "status", "folder")):
                w[key].grid(row=grid_row, column=column, sticky="w",
                            padx=(0, 4 if key == "reload" else 10),
                            pady=(3, 0))
            f.widgets = w
            self._update_file_row(f)

    def _update_file_row(self, f):
        """Refresh one file's size, X choices and on-disk status."""
        w = f.widgets
        if not w:
            return
        w["size"].configure(text="{:,} rows × {} cols".format(
            f.rows, len(f.names)))
        w["x"]["values"] = [ROW_INDEX_LABEL] + f.names
        w["folder"].configure(text=shorten_left(str(f.path.parent), 48))

        if f.error:
            text, color = ("Reload failed: {} - showing the last good "
                           "data".format(f.error)), ERROR_COLOR
        elif f.disk_stamp is None:
            text, color = ("Not found on disk - showing the last loaded "
                           "data"), ERROR_COLOR
        elif f.disk_stamp != f.stamp:
            text, color = "Changed on disk - click Reload", CHANGED_COLOR
        else:
            text, color = "", MUTED
        w["status"].configure(text=text, foreground=color)

    # -- Y rows ------------------------------------------------------------

    def _assign_default_columns(self, f):
        """Point every row that has no file yet at `f`, one column each."""
        candidates = [n for n in f.names if n != f.x_var.get()] or f.names
        for index, row in enumerate(self.y_rows):
            if row.file_id is None:
                row.file_id = f.id
                row.column_var.set(candidates[index % len(candidates)])

    def _matching_column(self, f, current, index):
        """The column of `f` a row should switch to when it switches file."""
        if current in f.columns:
            return current
        wanted = current.strip().lower()
        for name in f.names:
            if name.strip().lower() == wanted:
                return name
        candidates = [n for n in f.names if n != f.x_var.get()] or f.names
        return candidates[index % len(candidates)]

    def _refresh_y_choices(self):
        """
        Refill the Y dropdowns from the open files.  A row whose file was
        removed is cleared; a row whose column vanished on reload keeps it,
        so the series comes back if the column does.
        """
        labels = [f.label for f in self.files]
        for row in self.y_rows:
            row.file_box["values"] = labels
            f = self._file_by_id(row.file_id)
            if f is None:
                row.file_id = None
                row.file_var.set("")
                row.column_box["values"] = ()
                row.column_var.set("")
            else:
                row.file_var.set(f.label)
                row.column_box["values"] = f.names

    def _on_y_file_selected(self, index):
        row = self.y_rows[index]
        f = self._file_by_label(row.file_var.get())
        if f is None:
            return
        row.file_id = f.id
        row.column_box["values"] = f.names
        row.column_var.set(self._matching_column(f, row.column_var.get(), index))
        self.draw()

    def _on_count_change(self, _event=None):
        text = self.count_var.get().strip()
        try:
            count = int(float(text))
        except ValueError:
            count = self.y_count
        count = max(1, min(MAX_Y_AXES, count))
        self.count_var.set(str(count))
        if count == self.y_count:
            return
        self.y_count = count
        self._show_y_rows()
        self._refresh_bound_states()
        self.draw()
        self._fit_controls()

    def _show_y_rows(self):
        for index, row in enumerate(self.y_rows):
            for widget in row.widgets:
                if index < self.y_count:
                    widget.grid()
                else:
                    widget.grid_remove()

    def _file_style_index(self, f):
        """Which FILE_STYLES entry `f`'s curves use."""
        if f is None or not self.per_file_style_var.get() or f not in self.files:
            return 0
        return self.files.index(f) % len(FILE_STYLES)

    def _style_glyph(self, style_index):
        entry = FILE_STYLES[style_index]
        return entry[3] if self.style_var.get() == "points" else entry[2]

    def _refresh_file_glyphs(self):
        """Show each file's line style beside its name."""
        per_file = self.per_file_style_var.get()
        for f in self.files:
            if f.widgets:
                f.widgets["glyph"].configure(
                    text=self._style_glyph(self._file_style_index(f))
                    if per_file else "")

    def _on_style_change(self):
        self._refresh_file_glyphs()
        self.draw()

    # -- Axis controls -----------------------------------------------------

    def _axis_target(self, index):
        """The earlier row whose axis row `index` shares, or None."""
        text = self.y_rows[index].axis_var.get()
        if not text.startswith(SAME_AS_PREFIX):
            return None
        try:
            target = int(text[len(SAME_AS_PREFIX):]) - 1
        except ValueError:
            return None
        return target if 0 <= target < index else None

    def _axis_owner(self, index):
        """The row that owns the axis row `index` is drawn on."""
        target = self._axis_target(index)
        while target is not None:
            index = target
            target = self._axis_target(index)
        return index

    def _slot_is_live(self, index):
        """True when Y slot `index` owns an axis the user can bound."""
        if index >= self.y_count:
            return False
        if self.shared_y_var.get():
            return index == 0        # one axis, driven by the Y1 row
        return self._axis_owner(index) == index

    def _on_axis_change(self):
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
        if not self.y_rows[index].auto.get():
            axes = self.slot_axes.get(index)
            if axes is not None:
                self._store_limits(axes, "y", self.y_rows[index].bound_vars)
        self._refresh_bound_states()
        self.draw()

    def _refresh_bound_states(self):
        """Grey out every control that cannot affect the current plot."""
        state = "disabled" if self.x_auto.get() else "normal"
        for entry in self.x_bound_entries.values():
            entry.configure(state=state)

        shared = self.shared_y_var.get()
        for index, row in enumerate(self.y_rows):
            live = self._slot_is_live(index)
            row.auto_check.configure(state="normal" if live else "disabled")
            state = "normal" if (live and not row.auto.get()) else "disabled"
            for entry in row.bound_entries.values():
                entry.configure(state=state)
            if not live and row.auto.get():
                # Automatic boxes only mirror their axis; with no axis of
                # their own the old numbers would just mislead.
                for var in row.bound_vars.values():
                    var.set("")
            row.axis_box.configure(
                state="disabled" if (index == 0 or shared) else "readonly")

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

    def _parse_number(self, var, name, notes,
                      fallback="that limit was left automatic"):
        """Read one number box; None means empty or unusable."""
        text = var.get().strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            notes.append("{} '{}' is not a number - {}.".format(
                name, text, fallback))
            return None
        if math.isnan(value) or math.isinf(value):
            notes.append("{} must be a finite number - {}.".format(
                name, fallback))
            return None
        return value

    def _apply_manual_bounds(self, notes):
        """Push every non-automatic min/max onto the axis that owns it."""
        for axes, which, auto_var, bound_vars, name in self.sync_targets:
            if auto_var.get():
                continue
            low_name = "{} min".format(name)
            high_name = "{} max".format(name)
            low = self._parse_number(bound_vars["min"], low_name, notes)
            high = self._parse_number(bound_vars["max"], high_name, notes)
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
            side, level = axis_placement(position)
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
        self.label_texts = {"title": "", "x": "", "y": []}
        self._connect_limit_callbacks(axes_list)
        self._layout_axes()
        return axes_list

    def _color_axis(self, position, axes, color):
        """Paint one Y axis in the colour of the series that owns it."""
        side = axis_placement(position)[0]
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
        self.plot_size_pts = ((right - left) * width_pts,
                              (top - bottom) * height_pts)
        self._fit_labels()

    def _set_labels(self, title, x_label, y_labels):
        """Remember the full labels, then trim them to fit the plot."""
        self.label_texts = {"title": title, "x": x_label, "y": y_labels}
        self._fit_labels()

    def _fit_labels(self):
        """
        Trim the title and axis labels to the plot's current size, so long
        column and file names use all the room there is but never spill
        past the plot.  Runs again whenever the plot is resized.
        """
        width, height = self.plot_size_pts
        texts = self.label_texts
        # Average character widths, in points, of the default 12 pt title
        # and 10 pt axis labels, rounded up a little for safety.
        self.axes.set_title(shorten(texts["title"], max(20, int(width / 6.6))))
        self.axes.set_xlabel(shorten(texts["x"], max(20, int(width / 5.5))))
        for axes, text in texts["y"]:
            axes.set_ylabel(shorten(text, max(16, int(height / 5.5))))

    # -- Plotting ----------------------------------------------------------

    def _warn(self, message):
        parts = [self.load_warning]
        parts += ["{}: reload failed ({})".format(f.label, f.error)
                  for f in self.files if f.error]
        parts.append(message)
        message = "  |  ".join(p for p in parts if p)
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
                           transform=self.axes.transAxes, color=MUTED)
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

    def _active_rows(self, notes):
        """The (slot index, file, column) of every row that should plot."""
        active = []
        for index in range(self.y_count):
            row = self.y_rows[index]
            f = self._file_by_id(row.file_id)
            column = row.column_var.get()
            name = "Y{}".format(index + 1)
            if f is None:
                notes.append("{} has no file selected.".format(name))
            elif not column:
                notes.append("{} has no column selected.".format(name))
            elif column not in f.columns:
                notes.append("{}: column '{}' is no longer in {}.".format(
                    name, column, f.label))
            else:
                active.append((index, f, column))
        return active

    def _file_x(self, f, notes):
        """
        One file's X values with its offset applied, as
        (values, column name, offset), or None if they cannot be had.
        """
        name = f.x_var.get()
        if name == ROW_INDEX_LABEL:
            values = [float(i) for i in range(f.rows)]
        elif name in f.columns:
            values = f.columns[name]
        else:
            notes.append("{}: X column '{}' is no longer in the file - pick "
                         "another in the Files list.".format(f.label, name))
            return None

        offset = self._parse_number(f.offset_var, "{} X offset".format(f.label),
                                    notes, "the offset was ignored") or 0.0
        if offset:
            values = [v + offset for v in values]
        return values, name, offset

    def _line_kwargs(self, f):
        """matplotlib styling for one curve from file `f`."""
        linestyle, marker = FILE_STYLES[self._file_style_index(f)][:2]
        style = self.style_var.get()
        if style == "points":
            return {"linestyle": "none", "marker": marker, "markersize": 3}
        if style == "line + points":
            return {"linestyle": linestyle, "marker": marker,
                    "markersize": 3, "linewidth": 1.0}
        return {"linestyle": linestyle, "linewidth": 1.0}

    def _axis_label(self, entries):
        """Name the series on one Y axis, merging same-named columns."""
        files_by_column = {}
        for entry in entries:
            labels = files_by_column.setdefault(entry["column"], [])
            if entry["file"].label not in labels:
                labels.append(entry["file"].label)
        return ";  ".join("{}  [{}]".format(column, ", ".join(labels))
                          for column, labels in files_by_column.items())

    def _x_title(self, prepared, x_data):
        """(full X axis label, X column name(s) for the title)."""
        files = []
        for entry in prepared:
            if entry["file"] not in files:
                files.append(entry["file"])
        names = []
        parts = []
        for f in files:
            _values, name, offset = x_data[f.id]
            shown = "row index" if name == ROW_INDEX_LABEL else name
            if shown not in names:
                names.append(shown)
            part = "{}  [{}]".format(shown, f.label)
            if offset:
                part += "  {:+g}".format(offset)
            parts.append(part)
        return ";   ".join(parts), " / ".join(names)

    def _build_sync_targets(self, shared, owners, axes_list):
        """
        Decide which bound row drives which axis: each axis is driven by
        the row that owns it (Y1 when everything shares one axis).
        """
        self.slot_axes = dict(zip(owners, axes_list))
        self.sync_targets = [
            (self.axes, "x", self.x_auto, self.x_bound_vars, "X")]
        for owner, axes in zip(owners, axes_list):
            row = self.y_rows[owner]
            name = "Y" if shared else "Y{}".format(owner + 1)
            self.sync_targets.append(
                (axes, "y", row.auto, row.bound_vars, name))

    def draw(self):
        notes = []
        if not self.files:
            self._clear_plot("Open a CSV file to start:  Files  >  Open CSV…")
            self.status_var.set("No files open.")
            self._warn("")
            return

        active = self._active_rows(notes)
        if not active:
            self._clear_plot("Select a Y column.")
            self.status_var.set("")
            self._warn(" | ".join(notes))
            return

        # Pair everything up first: how many axes are needed depends on how
        # many series actually survive the pairing.  Each series is paired
        # with its own file's X column, never with another file's rows.
        x_data = {}              # file id -> _file_x() result
        prepared = []
        total_rows = 0
        for slot, f, column in active:
            if f.id not in x_data:
                x_data[f.id] = self._file_x(f, notes)
            if x_data[f.id] is None:
                continue
            xs, ys, n, valid = self._pair(x_data[f.id][0], f.columns[column])
            total_rows = max(total_rows, n)
            if valid == 0:
                notes.append(
                    "Y{} ({}) has no row where both X and Y hold a valid "
                    "number.".format(slot + 1, column))
                continue
            prepared.append({"slot": slot, "xs": xs, "ys": ys, "n": n,
                             "valid": valid, "column": column, "file": f})

        if not prepared:
            self._clear_plot("No rows where both columns hold a valid number.")
            if total_rows:
                self.status_var.set(
                    "0 of {:,} rows plottable - every pair had missing or "
                    "non-numeric data.".format(total_rows))
            else:
                self.status_var.set("Nothing to plot - see the notes below.")
            self._warn(" | ".join(notes))
            return

        # Group the series by the axis they are drawn on.  Axes are placed
        # in the order of the rows that own them.
        shared = self.shared_y_var.get()
        groups = {}
        for entry in prepared:
            owner = 0 if shared else self._axis_owner(entry["slot"])
            groups.setdefault(owner, []).append(entry)
        owners = sorted(groups)

        self._drawing = True
        try:
            axes_list = self._reset_axes(len(owners))

            y_labels = []
            for position, owner in enumerate(owners):
                axes = axes_list[position]
                members = groups[owner]
                for entry in members:
                    axes.plot(entry["xs"], entry["ys"],
                              color=SERIES_COLORS[entry["slot"]],
                              **self._line_kwargs(entry["file"]))
                y_labels.append((axes, self._axis_label(members)))
                # An axis carrying several series stays black: its label
                # names them, and the coloured row names say which curve is
                # which.
                if len(owners) > 1 and len(members) == 1:
                    self._color_axis(position, axes,
                                     SERIES_COLORS[members[0]["slot"]])

            columns = []
            for entry in prepared:
                if entry["column"] not in columns:
                    columns.append(entry["column"])
            x_label, x_names = self._x_title(prepared, x_data)
            self._set_labels("{} vs {}".format(", ".join(columns), x_names),
                             x_label, y_labels)
            self.axes.grid(self.grid_var.get(), alpha=0.3)

            # Settle the automatic limits before reading them, so that a row
            # with only one manual box keeps a true automatic other half.
            for axes in axes_list:
                axes.autoscale_view()

            self._build_sync_targets(shared, owners, axes_list)
            self._apply_manual_bounds(notes)
            self._sync_auto_entries()
        finally:
            self._drawing = False

        self.canvas.draw_idle()

        if len(prepared) == 1:
            valid, n = prepared[0]["valid"], prepared[0]["n"]
            message = "Plotted {:,} of {:,} rows.".format(valid, n)
            dropped = n - valid
            if dropped:
                message += ("  {:,} dropped (missing or non-numeric in X or "
                            "Y).".format(dropped))
        else:
            message = "Plotted {} series on {}:  {}.".format(
                len(prepared),
                "one Y axis" if len(owners) == 1
                else "{} Y axes".format(len(owners)),
                ";   ".join("Y{} {} = {:,} of {:,} rows".format(
                    entry["slot"] + 1, entry["column"], entry["valid"],
                    entry["n"])
                    for entry in prepared))
        total_valid = sum(entry["valid"] for entry in prepared)
        if total_valid > 50000:
            message += "  Large series - zooming may be slow."
        self.status_var.set(message)
        self._warn(" | ".join(notes))


def main(argv=None):
    paths = sys.argv[1:] if argv is None else argv
    app = LogPlotter(paths)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

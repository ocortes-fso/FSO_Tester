#!/usr/bin/env python3
"""
FSO Tester - new layout (v2).

Same buttons, same names, same behaviour as GUI/MasterUI_old.py, with a new look
that scales to any screen size.

    python3 GUI/MasterUI.py            # on the Pi (fullscreen)
    python  GUI/MasterUI.py --sim      # on a PC, with Simulator/stubs, windowed

HOW IT WORKS
------------
None of the test logic is copied. This file imports MasterUI_old (its widgets get
built but its mainloop is suppressed), hides MasterUI_old's own screens, builds new
screens, and puts every new widget back into MasterUI_old under the SAME global
name (MasterUI_old.BODY_STOP, MasterUI_old.ls, MasterUI_old.PV2_TOP, ...).

MasterUI_old's functions look their widgets up by global name each time they run,
so body_start(), body_stop_test(), propv2_estop(), a06_spin() and all the rest
drive these new widgets with no change to their code. Fix a bug in MasterUI_old.py
and it is fixed here too. MasterUI_old.py itself is not modified.

The only geometry MasterUI_old's functions do themselves is:
  * pack the page frames / Home / Back onto root  -> page frames stay on root
  * pack propv2_bar into propv2_side               -> propv2_side uses pack
  * pack spin_bar into status_container            -> status_container uses pack
Everything else here is free to use grid.

SCALING
-------
The layout was designed for the 800x480 5-inch panel. Every font, button
padding, slider thickness and the round emergency stops are multiplied by
min(width/800, height/480) and recomputed whenever the window changes size.
Buttons sit in grid cells with weights, so they also stretch to fill the space.
Fonts that MasterUI_old's functions set at run time (e.g. font=(None, 14) on the
body test results) are scaled as well - see ScaledLabel.

F11 toggles fullscreen, Escape leaves it.
"""

import os
import sys
import tkinter as tk
import tkinter.font as tkfont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SIM = "--sim" in sys.argv

if SIM:
    # Fake hardware first on the path, exactly like Simulator/preview.py.
    sys.path.insert(0, os.path.join(REPO, "Simulator", "stubs"))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

# --------------------------------------------------------------------------
# Import MasterUI_old without letting it start its own event loop
# --------------------------------------------------------------------------
_real_mainloop = ttk.Window.mainloop
ttk.Window.mainloop = lambda self, n=0: None

if SIM:
    _real_attributes = ttk.Window.attributes

    def _no_fullscreen(self, *args, **kwargs):
        if args and args[0] == "-fullscreen":
            return None
        return _real_attributes(self, *args, **kwargs)

    ttk.Window.attributes = _no_fullscreen

import MasterUI_old as M  # noqa: E402  (builds the old widgets, does not block)

ttk.Window.mainloop = _real_mainloop
if SIM:
    ttk.Window.attributes = _real_attributes

root = M.root
style = M.style
colors = style.colors

# Every widget global MasterUI_old had before the rebuild, so we can check at the
# end that each one was replaced.
_OLD_WIDGETS = {k: v for k, v in vars(M).items()
                if isinstance(v, tk.Misc) and v is not root}

# Hide MasterUI_old's own screens. They are not destroyed: anything that still
# holds a reference to one keeps working, it is just never shown.
for _w in root.pack_slaves():
    _w.pack_forget()
for _w in root.place_slaves():
    _w.place_forget()


# ==========================================================================
# Scaling
# ==========================================================================
BASE_W, BASE_H = 800, 480
_scale = 1.0
_DEFAULT_FAMILY = tkfont.nametofont("TkDefaultFont").actual("family")

_labels = []            # ScaledLabel instances
_hooks = []             # callables run after every rescale


def S(px):
    """A size designed for 800x480, at the current scale."""
    return max(1, int(round(px * _scale)))


def scaled_font(font):
    """(family, size, *styles) -> same font at the current scale."""
    if not isinstance(font, (tuple, list)) or len(font) < 2:
        return font
    family, size, *rest = font
    if family in (None, "none", "None", ""):
        family = _DEFAULT_FAMILY
    return (family, max(6, int(round(abs(size) * _scale))), *rest)


class ScaledLabel(ttk.Label):
    """
    A ttk.Label whose font follows the window scale.

    MasterUI_old's functions call label.config(font=(None, 14)) at run time; that
    size is stored as the label's base size and scaled, so results the test
    writes are just as readable on a 1080p monitor as on the 5-inch panel.

    wrap=True wraps the text to the width of the label's parent.
    """

    def __init__(self, master=None, font=(None, 14), wrap=False, wrap_pad=8, **kw):
        self._base_font = font
        super().__init__(master, font=scaled_font(font), **kw)
        _labels.append(self)
        if wrap:
            master.bind(
                "<Configure>",
                lambda e: tk.Misc.configure(self, wraplength=max(60, e.width - S(wrap_pad))),
                add="+",
            )

    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict) and "font" in cnf:
            kw.update(cnf)
            cnf = None
        if "font" in kw:
            self._base_font = kw["font"]
            kw["font"] = scaled_font(kw["font"])
        return super().configure(cnf, **kw)

    config = configure

    def _rescale(self):
        try:
            super().configure(font=scaled_font(self._base_font))
        except tk.TclError:
            pass


# Button styles: name -> (font size, padding x, padding y)
#
# The style NAMES that MasterUI_old's functions switch between (PropIdle, PropOn,
# A06Stop, ArmDanger, ...) are kept exactly as they were - only their size and
# look are set here. Rule from MasterUI_old still applies to any new name: it must
# contain exactly ONE ttkbootstrap widget word (so "Nav", never "Menu").
BUTTON_STYLES = {
    "Nav.TButton": (17, 10, 8),
    "Outline.TButton": (15, 14, 6),
    "success.TButton": (16, 8, 8),
    "danger.TButton": (16, 8, 8),
    "secondary.TButton": (16, 8, 8),
    "Arm.TButton": (17, 8, 6),
    "ArmDanger.TButton": (17, 8, 6),
    "ArmSuccess.TButton": (17, 8, 6),
    "Stop.TButton": (17, 8, 6),
    "PropIdle.TButton": (16, 6, 4),
    "PropBusy.TButton": (16, 6, 4),
    "PropOn.TButton": (16, 6, 4),
    "A06Small.TButton": (12, 4, 6),
    "A06SmallOn.TButton": (12, 4, 6),
    "A06Spin.TButton": (15, 6, 4),
    "A06Stop.TButton": (15, 6, 4),
    "A06Busy.TButton": (15, 6, 4),
}

BLUE, GREEN, RED, ORANGE = "#0d6efd", "#198754", "#dc3545", "#fd7e14"
_BUTTON_COLOURS = {
    "Nav.TButton": BLUE, "Arm.TButton": BLUE, "ArmDanger.TButton": RED,
    "ArmSuccess.TButton": GREEN, "Stop.TButton": RED,
    "PropIdle.TButton": BLUE, "PropBusy.TButton": ORANGE, "PropOn.TButton": GREEN,
    "A06Small.TButton": BLUE, "A06SmallOn.TButton": GREEN,
    "A06Spin.TButton": BLUE, "A06Stop.TButton": RED, "A06Busy.TButton": ORANGE,
}
for _name, _bg in _BUTTON_COLOURS.items():
    style.configure(_name, background=_bg, foreground="white", anchor="center",
                    justify="center")
    style.map(_name, background=[("disabled", "#3a3f44"), ("pressed", "#0a3a85"),
                                 ("active", _bg)],
              foreground=[("disabled", "#8a9099")])


def _rescale_styles():
    for name, (size, px, py) in BUTTON_STYLES.items():
        try:
            style.configure(name, font=scaled_font((None, size, "bold")),
                            padding=(S(px), S(py)))
        except tk.TclError:
            pass
    style.configure("TLabelframe.Label", font=scaled_font((None, 12, "bold")))
    style.configure("TProgressbar", thickness=S(14))


def apply_scale(new_scale):
    global _scale
    _scale = new_scale
    _rescale_styles()
    for lbl in list(_labels):
        lbl._rescale()
    for hook in _hooks:
        try:
            hook()
        except tk.TclError:
            pass


_rescale_job = None


def _on_root_configure(event):
    global _rescale_job
    if event.widget is not root:
        return
    if _rescale_job is not None:
        root.after_cancel(_rescale_job)
    _rescale_job = root.after(80, _check_scale)


def _check_scale():
    global _rescale_job
    _rescale_job = None
    w, h = root.winfo_width(), root.winfo_height()
    if w < 50 or h < 50:
        return
    s = max(0.55, min(w / BASE_W, h / BASE_H, 4.0))
    if abs(s - _scale) > 0.02:
        apply_scale(s)


root.bind("<Configure>", _on_root_configure, add="+")


# ==========================================================================
# Small building blocks
# ==========================================================================
def weights(frame, rows=(), cols=(), uniform=None):
    for r in rows:
        frame.rowconfigure(r, weight=1, uniform=uniform)
    for c in cols:
        frame.columnconfigure(c, weight=1, uniform=uniform)


def card(parent, title=None):
    """A bordered group with an optional title. Returns the inner frame."""
    if title:
        f = ttk.Labelframe(parent, text=f" {title} ", bootstyle=SECONDARY, padding=6)
    else:
        f = ttk.Frame(parent, padding=6)
    return f


class RoundEStop(tk.Canvas):
    """
    The round emergency stop, redrawn to fit its grid cell at any size.

    Same behaviour as MasterUI_old's: fires on PRESS (fastest response wins over
    guarding against a stray touch), paints itself dark while held, and is
    never disabled.
    """

    FILL, HELD, RING = "#b02a37", "#7d1d26", "#ff6b7a"

    def __init__(self, master, command, base_d=130):
        self._base_d = base_d
        super().__init__(master, width=S(base_d), height=S(base_d),
                         highlightthickness=0, bd=0, bg=colors.bg, cursor="hand2")
        self._command = command
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<ButtonRelease-1>", lambda e: self._paint(self.FILL))
        _hooks.append(self._resize)

    def _resize(self):
        self.configure(width=S(self._base_d), height=S(self._base_d))

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        d = max(40, min(w, h) - 6)
        x0, y0 = (w - d) / 2, (h - d) / 2
        self.create_oval(x0, y0, x0 + d, y0 + d, fill=self.FILL,
                         outline=self.RING, width=max(2, d // 40), tags="disc")
        self.create_text(w / 2, h / 2 - d * 0.07, text="STOP", fill="white",
                         font=(_DEFAULT_FAMILY, -int(d * 0.17), "bold"))
        self.create_text(w / 2, h / 2 + d * 0.12, text="EMERGENCY", fill="#ffd7db",
                         font=(_DEFAULT_FAMILY, -max(7, int(d * 0.075)), "bold"))

    def _paint(self, fill):
        self.itemconfigure("disc", fill=fill)
        root.update_idletasks()     # paint before the teardown blocks

    def _press(self, event=None):
        self._paint(self.HELD)
        self._command()


def throttle_slider(parent, command):
    """Same slider as MasterUI_old's (whole-us steps, no built-in value), scaled."""
    sc = tk.Scale(
        parent,
        from_=M.Manual_PWM_Test.SLIDER_MIN_US,
        to=M.Manual_PWM_Test.SLIDER_MAX_US,
        orient=HORIZONTAL, resolution=1, showvalue=0,
        length=S(300), width=S(46), sliderlength=S(48),
        bd=0, highlightthickness=0,
        troughcolor=colors.dark, bg=colors.info,
        activebackground=colors.primary,
        command=command,
    )
    _hooks.append(lambda: sc.configure(width=S(46), sliderlength=S(48)))
    return sc


# ==========================================================================
# Header bar (always visible) and the Home / Back buttons
# ==========================================================================
header = ttk.Frame(root, bootstyle=DARK, padding=(10, 3))
header.columnconfigure(1, weight=1)
header_app = ScaledLabel(header, text="FSO TESTER", font=(None, 13, "bold"))
header_app.configure(background=colors.dark, foreground=colors.info)
header_app.grid(row=0, column=0, sticky="w")
header_page = ScaledLabel(header, text="", font=(None, 13, "bold"), anchor="center")
header_page.configure(background=colors.dark, foreground="white")
header_page.grid(row=0, column=1, sticky="ew")
header_badge = ScaledLabel(header, text="SIMULATED HARDWARE" if SIM else "",
                           font=(None, 10, "bold"))
header_badge.configure(background=colors.dark, foreground=ORANGE)
header_badge.grid(row=0, column=2, sticky="e")

home_b = ttk.Button(root, text="Home", bootstyle=OUTLINE, command=M.home)
back_b = ttk.Button(root, text="Back", bootstyle=OUTLINE, command=M.show_body_from_back)


def _scaled_corner_pack(button):
    """
    MasterUI_old packs Home/Back with a fixed padx=20, pady=20 (or (6, 14)) - about
    60px of a 480px screen. Keep where it puts them (bottom-left) but use a
    margin that follows the scale, so the pages get that height back.
    """
    real_pack = button.pack_configure

    def pack(cnf=None, **kw):
        kw["padx"] = S(10)
        kw["pady"] = (S(2), S(6))
        return real_pack(cnf, **kw)

    button.pack = pack


_scaled_corner_pack(home_b)
_scaled_corner_pack(back_b)


# ==========================================================================
# Page frames (children of root - MasterUI_old packs them)
# ==========================================================================
PAD = 10
main = ttk.Frame(root, padding=PAD)
Lidar_f = ttk.Frame(root, padding=PAD)
Mag_f = ttk.Frame(root, padding=PAD)
Switch_plate_f = ttk.Frame(root, padding=PAD)
loom_f = ttk.Frame(root, padding=PAD)
Body_f = ttk.Frame(root, padding=PAD)
Volt_f = ttk.Frame(root, padding=PAD)
SBUS_f = ttk.Frame(root, padding=PAD)
SBUS_f_INF = ttk.Frame(root, padding=PAD)
Eth_f = ttk.Frame(root, padding=PAD)
Arm_f = ttk.Frame(root, padding=PAD)
PropV2_f = ttk.Frame(root, padding=(PAD, 4))
A06_f = ttk.Frame(root, padding=(PAD, 4))

PAGE_TITLES = {
    main: "MAIN MENU", Lidar_f: "LIDAR TEST", Mag_f: "MAGNETOMETER TEST",
    Switch_plate_f: "REAR SWITCH PLATE TEST", loom_f: "LOOM TEST",
    Body_f: "BODY TEST", Volt_f: "VOLTAGE TEST", SBUS_f: "IFV SBUS TEST",
    SBUS_f_INF: "SBUS TEST", Eth_f: "ETHERNET TEST", Arm_f: "ARM TEST",
    PropV2_f: "PROP TEST V2", A06_f: "Cv2_A06 TESTING",
}
for _f, _t in PAGE_TITLES.items():
    _f.bind("<Map>", lambda e, t=_t: header_page.configure(text=t), add="+")


# ==========================================================================
# MAIN MENU
# ==========================================================================
menu_row = ttk.Frame(main)
menu_row.pack(fill=BOTH, expand=TRUE)
weights(menu_row, rows=(0,), cols=(0, 1), uniform="menucol")


def _menu_group(col, title):
    g = ttk.Frame(menu_row, padding=(8, 0))
    g.grid(row=0, column=col, sticky="nsew")
    g.columnconfigure(0, weight=1)
    ScaledLabel(g, text=title, bootstyle=INFO, font=(None, 16, "bold")).grid(
        row=0, column=0, sticky="w")
    ttk.Separator(g, bootstyle=INFO).grid(row=1, column=0, sticky="ew", pady=(2, 6))
    weights(g, rows=(2, 3, 4, 5), uniform="menurow")
    return g


def _menu_button(parent, row, text, command):
    b = ttk.Button(parent, text=text, style="Nav.TButton", command=command)
    b.grid(row=row, column=0, sticky="nsew", pady=4)
    return b


menu_sub = _menu_group(0, "SUB-ASSEMBLIES")
b1 = _menu_button(menu_sub, 2, "Lidar Test", M.lidar)
b4 = _menu_button(menu_sub, 3, "Loom Test", M.loom)
b2 = _menu_button(menu_sub, 4, "Magnetometer Test", M.mag)
b3 = _menu_button(menu_sub, 5, "Rear Switch Plate Test", M.switch_plate)

menu_build = _menu_group(1, "BUILD TESTING")
b5 = _menu_button(menu_build, 2, "Body Test", M.body)
b6 = _menu_button(menu_build, 3, "Voltage Test", M.volt)
b9 = _menu_button(menu_build, 4, "Cv2_A06 Testing", M.cv2_a06)
b8 = _menu_button(menu_build, 5, "Prop TEST V2", M.prop_v2)

# Arm Test: built but not shown, same as MasterUI_old (removed from the menu there).
b7 = ttk.Button(main, text="Arm Test", style="Nav.TButton", command=M.arm)


# ==========================================================================
# Single-message pages: Lidar, Magnetometer, Switch plate, Ethernet, SBUS
# ==========================================================================
def _message_page(frame, text, font=(None, 24, "bold")):
    box = card(frame)
    box.pack(fill=BOTH, expand=TRUE)
    lbl = ScaledLabel(box, text=text, bootstyle=PRIMARY, font=font,
                      justify=CENTER, anchor=CENTER, wrap=True, wrap_pad=24)
    lbl.pack(fill=BOTH, expand=TRUE)
    return lbl


l2 = _message_page(Lidar_f, "Waiting for Lidar...")
l1 = _message_page(Mag_f, "Waiting for Magnetometer...")
l_sw = _message_page(Switch_plate_f, "Plug in Switch Plate to test...")
l3 = _message_page(Eth_f, "Pinging air unit...")
l_sbus = _message_page(SBUS_f, "Waiting for IFV SBUS signal...")
l_sbus_inf = _message_page(SBUS_f_INF, "Waiting for SBUS signal...")


# ==========================================================================
# BODY TEST
# ==========================================================================
weights(Body_f, rows=(0,))
Body_f.columnconfigure(0, weight=3, uniform="bodycol")
Body_f.columnconfigure(1, weight=2, uniform="bodycol")

body_left_container = card(Body_f, "RESULTS")
body_left_container.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
body_left_container.columnconfigure(0, weight=1)


def _result_block(row, title):
    head = ScaledLabel(body_left_container, text=title, bootstyle=INFO,
                       font=(None, 15, "bold"))
    head.grid(row=row, column=0, sticky="sw", padx=6)
    value = ScaledLabel(body_left_container, text="", bootstyle=SECONDARY,
                        font=(None, 14), wrap=True, wrap_pad=20)
    value.grid(row=row + 1, column=0, sticky="nw", padx=(18, 6))
    body_left_container.rowconfigure(row, weight=1)
    body_left_container.rowconfigure(row + 1, weight=1)
    return head, value


l4, ls = _result_block(0, "SERIAL")
l5, la = _result_block(2, "ANALOG PORT")
l6, lcan = _result_block(4, "CAN")
l7, lpwm = _result_block(6, "PWM")

lbody_lock = ScaledLabel(body_left_container, text="", bootstyle=SECONDARY,
                         font=(None, 13, "italic"), wrap=True, wrap_pad=20)
lbody_lock.grid(row=8, column=0, sticky="nw", padx=6, pady=(6, 0))
body_left_container.rowconfigure(8, weight=1)

body_btns = ttk.Frame(Body_f)
body_btns.grid(row=0, column=1, sticky="nsew")
body_btns.columnconfigure(0, weight=1)

BODY_START = ttk.Button(body_btns, text="Start Body Test", bootstyle=SUCCESS,
                        command=M.body_start)
BODY_STOP = ttk.Button(body_btns, text="Stop Body Test", bootstyle=DANGER,
                       command=M.body_stop_test)
eth1 = ttk.Button(body_btns, text="Ethernet Test", bootstyle=SECONDARY, command=M.Eth)
SB1 = ttk.Button(body_btns, text="SBUS Test", bootstyle=SECONDARY, command=M.SBUS_INF)
SB2 = ttk.Button(body_btns, text="IFV SBUS Test", bootstyle=SECONDARY, command=M.SBUS)
# Hidden in MasterUI_old too, until it does something.
Debug = ttk.Button(body_btns, text="Debug Mode", bootstyle=SECONDARY)

for _r, _b in enumerate((BODY_START, BODY_STOP)):
    _b.grid(row=_r, column=0, sticky="nsew", pady=4)
    body_btns.rowconfigure(_r, weight=1, uniform="bodybtn")
ttk.Separator(body_btns).grid(row=2, column=0, sticky="ew", pady=6)
for _r, _b in enumerate((eth1, SB1, SB2), start=3):
    _b.grid(row=_r, column=0, sticky="nsew", pady=4)
    body_btns.rowconfigure(_r, weight=1, uniform="bodybtn")

BODY_STOP.config(state="disabled")      # nothing running yet


# ==========================================================================
# VOLTAGE TEST
# ==========================================================================
volt_container = ttk.Frame(Volt_f)
volt_container.pack(fill=BOTH, expand=TRUE)
weights(volt_container, cols=(0, 1), uniform="volt")
weights(volt_container, rows=(0, 1))    # natural height first: SERIAL has 4 lines


def _volt_group(r, c, title, names):
    g = ttk.Frame(volt_container, padding=6, bootstyle=SECONDARY)
    g.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
    inner = ttk.Frame(g, padding=6)
    inner.pack(fill=BOTH, expand=TRUE)
    head = ScaledLabel(inner, text=title, bootstyle=INFO, font=(None, 17, "bold"))
    head.pack(anchor="w")
    out = [head]
    for n in names:
        lbl = ScaledLabel(inner, text=n, bootstyle=SECONDARY, font=(None, 15))
        lbl.pack(anchor="w", expand=TRUE)
        out.append(lbl)
    return out


l8, l9, l10, l11, l12 = _volt_group(0, 0, "3. SERIAL", ("V1:", "V2:", "V3:", "V4:"))
l13, l14, l15 = _volt_group(0, 1, "4. CAN/SBUS", ("V5:", "V6:"))
l16, l17, l18 = _volt_group(1, 0, "5. RC-OUT", ("V7:", "V8:"))
l19, l22 = _volt_group(1, 1, "6. PAYLOAD", ("V9:",))


# ==========================================================================
# LOOM TEST
# ==========================================================================
class ScaledLoomMatrix(M.LoomMatrix):
    """MasterUI_old's matrix (same show()/clear(), same red cells), scaled cells."""

    CELL_FONT = ("Courier", 13, "bold")
    HEAD_FONT = ("Courier", 9)

    def _make_label(self, text, font, bootstyle):
        return ScaledLabel(self, text=text, font=font, bootstyle=bootstyle,
                           width=2, anchor=CENTER)


# Matrix on the left with the whole page height (13 rows of cells), result and
# buttons on the right.
weights(loom_f, rows=(0,))
loom_f.columnconfigure(0, weight=3, uniform="loomcol")
loom_f.columnconfigure(1, weight=2, uniform="loomcol")

l21 = ScaledLoomMatrix(loom_f)
l21.grid(row=0, column=0)

loom_side = ttk.Frame(loom_f)
loom_side.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
loom_side.columnconfigure(0, weight=1)
l20 = ScaledLabel(loom_side, text="Ready to test", bootstyle=PRIMARY,
                  font=(None, 20, "bold"), justify=CENTER, anchor=CENTER,
                  wrap=True, wrap_pad=8)
l20.grid(row=0, column=0, sticky="ew", pady=(4, 2))
lloom_note = ScaledLabel(loom_side, text="", bootstyle=SECONDARY,
                         font=(None, 12, "italic"), justify=CENTER, anchor=CENTER,
                         wrap=True, wrap_pad=8)
lloom_note.grid(row=1, column=0, sticky="ew", pady=(0, 6))

loom_btns = ttk.Frame(loom_side)
loom_btns.grid(row=2, column=0, sticky="nsew")
loom_side.rowconfigure(2, weight=1)
weights(loom_btns, rows=(0, 1, 2), cols=(0,), uniform="loombtn")

LOOM_START = ttk.Button(loom_btns, text="Start", bootstyle=SUCCESS, command=M.loom_start)
LOOM_STOP = ttk.Button(loom_btns, text="Stop", bootstyle=DANGER, command=M.loom_stop_test)
LOOM_ONCE = ttk.Button(loom_btns, text="Run Once", bootstyle=SECONDARY, command=M.loom_once)
for _r, _b in enumerate((LOOM_START, LOOM_STOP, LOOM_ONCE)):
    _b.grid(row=_r, column=0, sticky="nsew", pady=4)

LOOM_STOP.config(state="disabled")      # nothing running yet


# ==========================================================================
# ARM TEST (not in the menu, same as MasterUI_old - kept so its timers work)
# ==========================================================================
weights(Arm_f, rows=(0,))
Arm_f.columnconfigure(0, weight=1, uniform="armcol")
Arm_f.columnconfigure(1, weight=2, uniform="armcol")
Arm_f.columnconfigure(2, weight=1, uniform="armcol")

status_container = ttk.Frame(Arm_f)            # pack inside: spin_bar is packed by MasterUI_old
status_container.grid(row=0, column=0, sticky="nsew")
status_dot = ScaledLabel(status_container, text="●", font=("Arial", 28, "bold"))
status_dot.pack(anchor="w")
status_text = ScaledLabel(status_container, text="SAFE", bootstyle=SECONDARY, font=(None, 17))
status_text.pack(anchor="w")
arm_reason = ScaledLabel(status_container, text="", bootstyle=SECONDARY,
                         font=(None, 13), justify="left", wrap=True)
arm_reason.pack(anchor="w", fill=X)
spin_label = ScaledLabel(status_container, text="", bootstyle=INFO, font=(None, 17))
spin_label.pack(anchor="w")
spin_bar = ttk.Progressbar(status_container, maximum=100, bootstyle=INFO, length=160)

arm_btns = ttk.Frame(Arm_f)
arm_btns.grid(row=0, column=1, sticky="nsew", padx=8)
arm_btns.columnconfigure(0, weight=1)
PWR = ttk.Button(arm_btns, text="POWER ON", style="Arm.TButton", command=M.toggle_power)
PWM_INIT = ttk.Button(arm_btns, text="Intialise PWM", style="Arm.TButton", command=M.INITIAL_PWM)
SPIN_ALL = ttk.Button(arm_btns, text="Spin ALL", style="Arm.TButton", command=M.SPIN)
SPIN_TOP = ttk.Button(arm_btns, text="Spin TOP", style="Arm.TButton", command=M.TOP_SPIN)
SPIN_BOT = ttk.Button(arm_btns, text="Spin BOT", style="Arm.TButton", command=M.BOT_SPIN)
LED_btn = ttk.Button(arm_btns, text="Turn LED On", style="Arm.TButton", command=M.TOGGLE_LED)
PROP = ttk.Button(arm_btns, text="Prop Test", style="Arm.TButton", command=M.PROP_SPIN)
for _r, _b in enumerate((PWR, PWM_INIT, SPIN_ALL, SPIN_TOP, SPIN_BOT, LED_btn, PROP)):
    _b.grid(row=_r, column=0, sticky="nsew", pady=2)
    arm_btns.rowconfigure(_r, weight=1, uniform="armbtn")

batt_container = ttk.Frame(Arm_f)
batt_container.grid(row=0, column=2, sticky="nsew")
lv = ScaledLabel(batt_container, text="Voltage:", bootstyle=SECONDARY, font=(None, 16))
lv.pack(anchor="e")
li = ScaledLabel(batt_container, text="Current:", bootstyle=SECONDARY, font=(None, 16))
li.pack(anchor="e")
lt = ScaledLabel(batt_container, text="Temperature:", bootstyle=SECONDARY, font=(None, 16))
lt.pack(anchor="e")
lpwm_status = ScaledLabel(batt_container, text="PWM1: --   PWM2: --", bootstyle=SECONDARY,
                          font=(None, 16))
lpwm_status.pack(anchor="e", pady=(10, 0))
STOP_btn = ttk.Button(batt_container, text="STOP", style="Stop.TButton", command=M.power_off)
STOP_btn.pack(fill=BOTH, expand=TRUE, pady=10)


# ==========================================================================
# Shared: right-hand status column + emergency stop (Prop V2 and A06)
# ==========================================================================
def _status_column(page):
    """Right column: status card on top (pack inside), E-STOP below."""
    right = ttk.Frame(page)
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
    right.columnconfigure(0, weight=1)
    right.rowconfigure(0, weight=0)
    right.rowconfigure(1, weight=1)
    side = ttk.Frame(right, padding=(6, 2))
    side.grid(row=0, column=0, sticky="new")
    return right, side


def _telemetry(side, prefix_pad=(0, 6)):
    v = ScaledLabel(side, text="Voltage:  --", bootstyle=SECONDARY, font=(None, 15))
    v.pack(anchor="w")
    i = ScaledLabel(side, text="Current:  --", bootstyle=SECONDARY, font=(None, 15))
    i.pack(anchor="w")
    w = ScaledLabel(side, text="Power:    --", bootstyle=SECONDARY, font=(None, 15))
    w.pack(anchor="w")
    t = ScaledLabel(side, text="Temp:     --", bootstyle=SECONDARY, font=(None, 15))
    t.pack(anchor="w")
    return v, i, w, t


# ==========================================================================
# PROP TEST V2
# ==========================================================================
weights(PropV2_f, rows=(0,))
PropV2_f.columnconfigure(0, weight=3, uniform="pv2col")
PropV2_f.columnconfigure(1, weight=2, uniform="pv2col")

pv2_right, propv2_side = _status_column(PropV2_f)

_pv2_state_row = ttk.Frame(propv2_side)
_pv2_state_row.pack(anchor="w", fill=X)
propv2_dot = ScaledLabel(_pv2_state_row, text="●", font=("Arial", 24, "bold"), foreground="white")
propv2_dot.pack(side=LEFT)
propv2_state_lbl = ScaledLabel(_pv2_state_row, text="NO POWER", bootstyle=SECONDARY,
                               font=(None, 20, "bold"))
propv2_state_lbl.pack(side=LEFT, padx=(6, 0))
propv2_detail_lbl = ScaledLabel(propv2_side, text="press Power On", bootstyle=INFO,
                                font=(None, 12), justify="left", wrap=True, wrap_pad=12)
propv2_detail_lbl.pack(anchor="w", fill=X, pady=(0, 6))
propv2_v_lbl, propv2_i_lbl, propv2_w_lbl, propv2_t_lbl = _telemetry(propv2_side)
propv2_pwm_lbl = ScaledLabel(propv2_side, text="PWM TOP: off    BOT: off", bootstyle=INFO,
                             font=(None, 14, "bold"))
propv2_pwm_lbl.pack(anchor="w", pady=(6, 0))
propv2_bar = ttk.Progressbar(propv2_side, maximum=100, bootstyle=INFO, length=220)
_hooks.append(lambda: propv2_bar.configure(length=S(220)))

PV2_ESTOP = RoundEStop(pv2_right, M.propv2_estop)
PV2_ESTOP.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

propv2_btns = ttk.Frame(PropV2_f)
propv2_btns.grid(row=0, column=0, sticky="nsew")
weights(propv2_btns, cols=(0, 1), uniform="pv2bcol")
weights(propv2_btns, rows=(1, 2, 3, 4), uniform="pv2brow")

propv2_title = ScaledLabel(propv2_btns, text="PROP TEST V2", bootstyle=PRIMARY,
                           font=(None, 20, "bold"))
propv2_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

PV2_PRECHARGE = ttk.Button(propv2_btns, text="Power On (FET)", style="PropIdle.TButton",
                           command=M.propv2_precharge)
PV2_POWEROFF = ttk.Button(propv2_btns, text="Power Off", style="PropIdle.TButton",
                          command=M.propv2_power_off)
PV2_LED = ttk.Button(propv2_btns, text="Turn LED On", style="PropIdle.TButton",
                     command=M.propv2_led)
PV2_TOP = ttk.Button(propv2_btns, text="TOP Test", style="PropIdle.TButton", command=M.propv2_top)
PV2_BOT = ttk.Button(propv2_btns, text="BOT Test", style="PropIdle.TButton", command=M.propv2_bot)
PV2_BOTH = ttk.Button(propv2_btns, text="Prop Test", style="PropIdle.TButton", command=M.propv2_both)
PV2_PULSE = ttk.Button(propv2_btns, text="Pulse Test", style="PropIdle.TButton",
                       command=M.propv2_pulse)

_g = dict(sticky="nsew", padx=3, pady=3)
PV2_PRECHARGE.grid(row=1, column=0, **_g)
PV2_POWEROFF.grid(row=1, column=1, **_g)
PV2_LED.grid(row=2, column=0, columnspan=2, **_g)
PV2_TOP.grid(row=3, column=0, **_g)
PV2_BOT.grid(row=3, column=1, **_g)
PV2_BOTH.grid(row=4, column=0, **_g)
PV2_PULSE.grid(row=4, column=1, **_g)


# ==========================================================================
# Cv2_A06 TESTING
# ==========================================================================
weights(A06_f, rows=(0,))
A06_f.columnconfigure(0, weight=3, uniform="a06col")
A06_f.columnconfigure(1, weight=2, uniform="a06col")

a06_right, a06_side = _status_column(A06_f)

_a06_state_row = ttk.Frame(a06_side)
_a06_state_row.pack(anchor="w", fill=X)
a06_dot = ScaledLabel(_a06_state_row, text="●", font=("Arial", 24, "bold"), foreground="white")
a06_dot.pack(side=LEFT)
a06_state_lbl = ScaledLabel(_a06_state_row, text="NO POWER", bootstyle=SECONDARY,
                            font=(None, 20, "bold"))
a06_state_lbl.pack(side=LEFT, padx=(6, 0))
a06_v_lbl, a06_i_lbl, a06_w_lbl, a06_t_lbl = _telemetry(a06_side)
a06_pwm_lbl = ScaledLabel(a06_side, text="PWM TOP: off    BOT: off", bootstyle=INFO,
                          font=(None, 14, "bold"))
a06_pwm_lbl.pack(anchor="w", pady=(6, 0))

A06_ESTOP = RoundEStop(a06_right, M.a06_estop)
A06_ESTOP.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

a06_main = ttk.Frame(A06_f)
a06_main.grid(row=0, column=0, sticky="nsew")
a06_main.columnconfigure(0, weight=1)

a06_head = ttk.Frame(a06_main)
a06_head.grid(row=0, column=0, sticky="ew")
a06_title = ScaledLabel(a06_head, text="Cv2_A06 TESTING", bootstyle=PRIMARY,
                        font=(None, 18, "bold"))
a06_title.pack(side=LEFT, anchor="s")
a06_subtitle = ScaledLabel(
    a06_head,
    text=f"TOP=GPIO{M.Manual_PWM_Test.PWM_TOP}  BOT=GPIO{M.Manual_PWM_Test.PWM_BOT}"
         f"  {M.Manual_PWM_Test.PWM_FREQ_HZ} Hz",
    bootstyle=SECONDARY, font=(None, 10),
)
a06_subtitle.pack(side=LEFT, anchor="s", padx=(12, 0), pady=(0, 2))

# The status message wraps; its box reserves two lines so a long message does
# not shove the sliders around, and is re-sized with the scale.
a06_detail_box = ttk.Frame(a06_main, height=38)
a06_detail_box.grid(row=1, column=0, sticky="ew")
a06_detail_box.pack_propagate(False)
_hooks.append(lambda: a06_detail_box.configure(height=S(38)))
a06_detail_lbl = ScaledLabel(a06_detail_box, text="press Power On", bootstyle=INFO,
                             font=(None, 11), justify="left", wrap=True, wrap_pad=4)
a06_detail_lbl.pack(anchor="w", fill=X)

a06_pwr_row = ttk.Frame(a06_main)
a06_pwr_row.grid(row=2, column=0, sticky="nsew", pady=(2, 2))
weights(a06_pwr_row, rows=(0,), cols=(0, 1, 2, 3), uniform="a06pwr")
A06_PWR_ON = ttk.Button(a06_pwr_row, text="Power On", style="A06Small.TButton",
                        command=M.a06_power_on)
A06_PWR_OFF = ttk.Button(a06_pwr_row, text="Power Off", style="A06Small.TButton",
                         command=M.a06_power_off)
A06_ARM = ttk.Button(a06_pwr_row, text="Init PWM", style="A06Small.TButton",
                     command=M.a06_arm_toggle)
A06_LED = ttk.Button(a06_pwr_row, text="Turn LED On", style="A06Small.TButton",
                     command=M.a06_led)
for _c, _b in enumerate((A06_PWR_ON, A06_PWR_OFF, A06_ARM, A06_LED)):
    _b.grid(row=0, column=_c, sticky="nsew", padx=(0 if _c == 0 else 3, 0))


def _a06_channel_box(row, title, spin_text, spin_cmd, slide_cmd):
    box = ttk.Labelframe(
        a06_main,
        text=(f" {title}  |  Spin {M.Manual_PWM_Test.SPIN_US}us x "
              f"{M.Manual_PWM_Test.SPIN_HOLD_S:.0f}s  |  Slider OFF..."
              f"{M.Manual_PWM_Test.SLIDER_MAX_US}us "),
        bootstyle=SECONDARY, padding=(6, 2),
    )
    box.grid(row=row, column=0, sticky="nsew", pady=(3, 0))
    box.columnconfigure(0, weight=1)
    box.columnconfigure(1, weight=1)
    box.rowconfigure(0, weight=1)
    spin = ttk.Button(box, text=spin_text, style="A06Spin.TButton", command=spin_cmd)
    spin.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=2)
    value = ScaledLabel(box, text="OFF  (0 us)", bootstyle=SECONDARY,
                        font=(None, 17, "bold"), anchor="e")
    value.grid(row=0, column=1, sticky="e", padx=4)
    slider = throttle_slider(box, slide_cmd)
    slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(4, 4))
    return box, spin, value, slider


A06_TOP_BOX, A06_TOP_SPIN, A06_TOP_VALUE, A06_TOP_SLIDER = _a06_channel_box(
    3, "TOP MOTOR", "TOP Spin", M.a06_spin_top, M.a06_top_slider_moved)
A06_BOT_BOX, A06_BOT_SPIN, A06_BOT_VALUE, A06_BOT_SLIDER = _a06_channel_box(
    4, "BOT MOTOR", "BOT Spin", M.a06_spin_bot, M.a06_bot_slider_moved)

# No `uniform` here on purpose: every row first gets its natural height, and
# only the SPARE height is shared out - so on the 5-inch panel nothing is
# squashed, and on a big screen the buttons and channel boxes grow.
a06_main.rowconfigure(2, weight=1)
a06_main.rowconfigure(3, weight=2)
a06_main.rowconfigure(4, weight=2)


# ==========================================================================
# Hand the new widgets to MasterUI_old under the same names
# ==========================================================================
_NEW = {k: v for k, v in dict(globals()).items()
        if isinstance(v, tk.Misc) and k in _OLD_WIDGETS}
for _name, _widget in _NEW.items():
    setattr(M, _name, _widget)

_missing = sorted(set(_OLD_WIDGETS) - set(_NEW))
if _missing:
    # A widget MasterUI_old has that this layout does not rebuild (e.g. added to
    # MasterUI_old after this file was written). It still exists, just hidden -
    # whatever MasterUI_old writes to it will not be on screen.
    print(f"[UI] not rebuilt, still using the hidden MasterUI_old widget: {_missing}")

# Starting states, the same ones MasterUI_old sets on its own widgets at import.
M.propv2_buttons_idle()
M.a06_reset_sliders()
M.a06_refresh_controls()


# ==========================================================================
# Show it
# ==========================================================================
def _toggle_fullscreen(event=None):
    root.attributes("-fullscreen", not root.attributes("-fullscreen"))


root.bind("<F11>", _toggle_fullscreen)
root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))

header.pack(side=TOP, fill=X)
main.pack(fill=BOTH, expand=TRUE)

if SIM:
    root.geometry("1024x600")
    print("-" * 70)
    print("SIMULATED HARDWARE - every voltage, current and GPIO here is fake.")
    print("-" * 70)

root.update_idletasks()
_check_scale()
apply_scale(_scale)

root.mainloop()

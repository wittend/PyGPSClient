"""
scatter_frame.py

Scatterplot frame class for PyGPSClient Application.

This generates a scatterplot of positions, centered on either
the cumulative average position or a fixed reference position.

The fixed reference position can be stored in the json
configuration file as `scatterlat_f`/`scatterlon_f`.

Created 23 March 2023

Completely rewritten by semuadmin 5 Nov 2024 to use bounding
box rather than polar coordinations, and allow right-click
fixed reference selection.

:author: Nathan Michaels, semuadmin
:copyright: 2024 SEMU Consulting
:license: BSD 3-Clause
"""

from tkinter import (
    HORIZONTAL,
    Checkbutton,
    E,
    Entry,
    Frame,
    IntVar,
    N,
    S,
    Scale,
    Spinbox,
    StringVar,
    W,
    font,
)

try:
    from statistics import pstdev

    HASSTATS = True
except (ImportError, ModuleNotFoundError):
    HASSTATS = False

from pygpsclient.globals import BGCOL, FGCOL, SQRT2, WIDGETU2, Area, Point
from pygpsclient.helpers import get_point_at_vector, in_bounds
from pygpsclient.skyview_frame import Canvas

MAXPOINTS = 100000  # equivalent to roughly 24 hours of data or 4.5MB
CTRAVG = "Average"
CTRFIX = "Fixed"
CRTS = (CTRAVG, CTRFIX)
PNTCOL = "orange"
FIXCOL = "green2"
AVG = "avg"


class ScatterViewFrame(Frame):
    """
    Scatterplot view frame class.
    """

    def __init__(self, app, *args, **kwargs):
        """
        Constructor.

        :param Frame app: reference to main tkinter application
        :param args: Optional args to pass to Frame parent class
        :param kwargs: Optional kwargs to pass to Frame parent class
        """
        self.__app = app
        self.__master = self.__app.appmaster
        config = self.__app.saved_config

        Frame.__init__(self, self.__master, *args, **kwargs)

        def_w, def_h = WIDGETU2

        self.width = kwargs.get("width", def_w)
        self.height = kwargs.get("height", def_h)
        self._lbl_font = font.Font(size=max(int(self.height / 40), 10))
        self._points = []
        self._center = None
        self._average = None
        self._stddev = None
        self._fixed = None
        self._bounds = None
        self._lastbounds = Area(0, 0, 0, 0)
        self._range = 0.0
        self._autorange = IntVar()
        self._centermode = StringVar()
        self._scale = IntVar()
        self._reflat = StringVar()
        self._reflon = StringVar()
        reflat = config.get("scatterlat_f", 0.0)
        reflon = config.get("scatterlon_f", 0.0)
        self._reflat.set("Reference Lat" if reflat == 0.0 else reflat)
        self._reflon.set("Reference Lon" if reflon == 0.0 else reflon)
        self._scale_factors = (
            5000,
            2000,
            1000,
            500,
            200,
            100,
            50,
            20,
            10,
            5,
            2,
            1,
            0.5,
            0.2,
            0.1,
            0.05,
            0.02,
            0.01,
        )  # scale factors represent plot radius in meters
        self._autorange.set(config.get("scatterautorange_b", 1))
        self._scale.set(config.get("scatterscale_n", 9))
        self._centermode.set(config.get("scattercenter_s", CTRAVG))
        if self._centermode.get() != CTRFIX:
            self._centermode.set(CTRAVG)
        self._body()
        self._attach_events()

    def _body(self):
        """Set up frame and widgets."""

        for i in range(4):
            self.grid_columnconfigure(i, weight=1, uniform="ent")
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.canvas = Canvas(self, width=self.width, height=self.height, bg=BGCOL)
        self._chk_autorange = Checkbutton(
            self,
            text="Autorange",
            fg=PNTCOL,
            bg=BGCOL,
            variable=self._autorange,
        )
        self._spn_center = Spinbox(
            self,
            values=CRTS,
            width=9,
            wrap=True,
            fg=PNTCOL,
            bg=BGCOL,
            textvariable=self._centermode,
        )
        self._scl_range = Scale(
            self,
            from_=0,
            to=len(self._scale_factors) - 1,
            orient=HORIZONTAL,
            bg=FGCOL,
            troughcolor=BGCOL,
            variable=self._scale,
            showvalue=False,
        )
        self._ent_reflat = Entry(
            self,
            textvariable=self._reflat,
            fg=FIXCOL,
            bg=BGCOL,
        )
        self._ent_reflon = Entry(
            self,
            textvariable=self._reflon,
            fg=FIXCOL,
            bg=BGCOL,
        )
        self.canvas.grid(column=0, row=0, columnspan=4, sticky=(N, S, E, W))
        self._chk_autorange.grid(column=0, row=1, sticky=(W, E))
        self._spn_center.grid(column=1, row=1, sticky=(W, E))
        self._scl_range.grid(column=2, row=1, columnspan=2, sticky=(W, E))
        self._ent_reflat.grid(column=0, row=2, columnspan=2, sticky=(W, E))
        self._ent_reflon.grid(column=2, row=2, columnspan=2, sticky=(W, E))

    def _attach_events(self):
        """
        Bind events to frame.
        """

        self.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Double-Button-1>", self._on_clear)
        self.canvas.bind("<Button-2>", self._on_recenter)  # mac
        self.canvas.bind("<Button-3>", self._on_recenter)  # win
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self._scale.trace_add("write", self._on_rescale)

    def _on_zoom(self, event):
        """
        Adjust scale using mousewheel.

        :param event: mousewheel event
        """

        sl = len(self._scale_factors) - 1
        sc = self._scale.get()
        if event.delta > 0:
            if sc < sl:
                self._scale.set(sc + 1)
        elif event.delta < 0:
            if sc > 0:
                self._scale.set(sc - 1)

    def _on_rescale(self, var, index, mode):  # pylint: disable=unused-argument
        """
        Rescale widget.
        """

        self._on_resize(None)

    def _on_resize(self, event):  # pylint: disable=unused-argument
        """
        Resize frame.

        :param Event event: resize event
        """

        self.width, self.height = self.get_size()
        self._init_frame()
        self._redraw()

    def _on_recenter(self, event):
        """
        Right click centers on cursor.

        :param Event event: right click event
        """

        pos = self._xy2ll((event.x, event.y))
        self._reflat.set(round(pos.lat, 9))
        self._reflon.set(round(pos.lon, 9))
        try:
            self._fixed = Point(float(self._reflat.get()), float(self._reflon.get()))
        except ValueError:
            pass

    def _on_clear(self, event):  # pylint: disable=unused-argument
        """ "
        Clear plot.

        :param Event event: double-click event
        """

        self._points = []
        self._init_frame()

    def _init_frame(self):
        """
        Initialize scatter plot.
        """

        width, height = self.get_size()
        self.canvas.delete("all")
        self.canvas.create_line(0, height / 2, width, height / 2, fill=FGCOL)
        self.canvas.create_line(width / 2, 0, width / 2, height, fill=FGCOL)

        if self._bounds is None:
            return

        maxr = min(height / 2, width / 2)
        for i in range(1, 5):
            self.canvas.create_circle(
                width / 2, height / 2, maxr * i / 4, outline=FGCOL, width=1
            )
            rng, unt = self.get_range_label()
            if rng >= 100:
                dp = 0
            elif rng >= 10:
                dp = 1
            elif rng >= 1:
                dp = 2
            else:
                dp = 3
            dist = f"{rng * i/4:.{dp}f}{unt}"
            txt_x = width / 2 + SQRT2 * maxr * i / 4
            txt_y = height / 2 + SQRT2 * maxr * i / 4
            self.canvas.create_text(
                txt_x, txt_y, text=dist, fill=FGCOL, font=self._lbl_font
            )
            for x, y, t in (
                (width / 2, 5, "N"),
                (width / 2, height - 5, "S"),
                (5, height / 2, "W"),
                (width - 5, height / 2, "E"),
            ):
                self.canvas.create_text(
                    x, y, text=t, fill=FGCOL, font=self._lbl_font, anchor=t.lower()
                )

    def _draw_average(self, lbl_font: font):
        """
        Draw the average position in the corner of the plot.

        :param font lbl_font: Font to use.
        """

        if self._average is None:
            return

        self.canvas.delete(AVG)

        fh = self._lbl_font.metrics("linespace")
        avg = f"Avg: {self._average.lat:.9f}, {self._average.lon:.9f}"
        self.canvas.create_text(
            5, 5, text=avg, fill=PNTCOL, font=lbl_font, anchor="nw", tags=AVG
        )
        if self._stddev is not None:
            std = f"Std: {self._stddev.lat:.3e}, {self._stddev.lon:.3e}"
            self.canvas.create_text(
                5, 5 + fh, text=std, fill=PNTCOL, font=lbl_font, anchor="nw", tags=AVG
            )

    def _draw_point(self, position: Point, color: str = PNTCOL, size: int = 2):
        """
        Draw a point on the scatterplot.

        :param Point position: The point to draw
        :param str color: point color as string e.g. "orange"
        :param int size: size of circle (2)
        """

        if not in_bounds(self._bounds, position):
            return

        x, y = self._ll2xy(position)
        self.canvas.create_circle(x, y, size, fill=color, outline=color)

    def _ll2xy(self, position: Point) -> tuple:
        """
        Convert lat/lon to canvas x/y.

        :param Point coordinate: lat/lon
        :return: x,y canvas coordinates
        :rtype: tuple
        """

        cw, ch = self.get_size()
        lw = self._bounds.lon2 - self._bounds.lon1
        lh = self._bounds.lat2 - self._bounds.lat1
        lwp = lw / cw  # # units longitude per x pixel
        lhp = lh / ch  # units latitude per y pixel

        x = (position.lon - self._bounds.lon1) / lwp
        y = ch - (position.lat - self._bounds.lat1) / lhp
        return x, y

    def _xy2ll(self, xy: tuple) -> Point:
        """
        Convert canvas x/y to lat/lon.

        :param tuple xy: canvas x/y coordinate
        :return: lat/lon
        :rtype: Point
        """

        cw, ch = self.get_size()
        lw = self._bounds.lon2 - self._bounds.lon1
        lh = self._bounds.lat2 - self._bounds.lat1
        cwp = cw / lw  # x pixels per unit longitude
        chp = ch / lh  # y pixels per unit latitude
        x, y = xy
        lon = self._bounds.lon1 + x / cwp
        lat = self._bounds.lat1 + (ch - y) / chp
        return Point(lat, lon)

    def _set_average(self):
        """
        Calculate the mean position of all the lat/lon pairs visible
        on the scatter plot. Note that this will make for some very
        weird results near poles.
        """

        num = len(self._points)
        ave_lat = sum(p.lat for p in self._points) / num
        ave_lon = sum(p.lon for p in self._points) / num
        self._average = Point(ave_lat, ave_lon)
        if HASSTATS:
            self._stddev = Point(
                pstdev(p.lat for p in self._points), pstdev(p.lon for p in self._points)
            )

    def _set_bounds(self, center: Point):
        """
        Set bounding box of canvas baed on center point and
        plot range.

        :param Point center: centre of bounding box
        """

        cw, ch = self.get_size()
        disth = self._scale_factors[self._scale.get()]
        distw = self._scale_factors[self._scale.get()] * cw / ch
        t = get_point_at_vector(center, disth, 0)
        r = get_point_at_vector(center, distw, 90)
        b = get_point_at_vector(center, disth, 180)
        l = get_point_at_vector(center, distw, 270)
        self._bounds = Area(b.lat, l.lon, t.lat, r.lon)
        self._range = disth

        if self._bounds != self._lastbounds:
            self._init_frame()
            self._lastbounds = self._bounds

    def get_range_label(self) -> tuple:
        """
        Set range value and units according to magnitude.

        :return: range, units
        :rtype: tuple
        """

        if self._range >= 1000:
            rng = self._range / 1000
            unt = "km"
        elif self._range >= 1:
            rng = self._range
            unt = "m"
        else:
            rng = self._range * 100
            unt = "cm"
        return rng, unt

    def _redraw(self):
        """
        Redraw all the points on the scatter plot.
        """

        if not self._points:
            return

        for pnt in self._points:
            self._draw_point(pnt)
        if self._fixed is not None:
            self._draw_point(self._fixed, FIXCOL, 3)

        self._draw_average(self._lbl_font)

    def update_frame(self):
        """
        Collect scatterplot data and update the plot.
        """

        lat, lon = self.__app.gnss_status.lat, self.__app.gnss_status.lon
        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            return  # Invalid values for lat/lon get ignored.
        pos = Point(lat, lon)
        if self.__app.gnss_status.fix == "NO FIX":
            return  # Don't plot when we don't have a fix.
        if self._points and pos == self._points[-1]:
            return  # Don't repeat exactly the last point.

        self._points.append(pos)
        if len(self._points) > MAXPOINTS:
            self._points.pop(0)

        self._set_average()

        middle = self._average
        try:
            self._fixed = Point(float(self._reflat.get()), float(self._reflon.get()))
            if self._centermode.get() == CTRFIX:
                middle = self._fixed
        except ValueError:
            self._fixed = None
            self._centermode.set(CTRAVG)

        self._set_bounds(middle)
        if self._autorange.get():
            self._do_autorange(middle)

        self._redraw()

    def _do_autorange(self, middle: Point):
        """
        Adjust range until all points in bounds.

        :param Point middle: center point of plot
        """

        out = True
        while out and self._scale.get() > 0:
            out = False
            for pt in self._points:
                if not in_bounds(self._bounds, pt):
                    out = True
                    break
            if out:
                self._scale.set(self._scale.get() - 1)
                self._set_bounds(middle)

    def get_size(self) -> tuple:
        """
        Get current canvas size.

        :return: window size (width, height)
        :rtype: tuple
        """

        self.update_idletasks()  # Make sure we know about resizing
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self._lbl_font = font.Font(size=max(int(height / 40), 10))
        return (width, height)

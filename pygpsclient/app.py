"""
PyGPSClient - Main tkinter application class.

Created on 12 Sep 2020

:author: semuadmin
:copyright: SEMU Consulting © 2020
:license: BSD 3-Clause
"""

from threading import Thread
from tkinter import Frame, N, S, E, W, PhotoImage, font

from pygpsclient.strings import (
    TITLE,
    MENUHIDESE,
    MENUSHOWSE,
    MENUHIDESB,
    MENUSHOWSB,
    MENUHIDECON,
    MENUSHOWCON,
    MENUHIDEMAP,
    MENUSHOWMAP,
    MENUHIDESATS,
    MENUSHOWSATS,
    INTROTXTNOPORTS,
)
from pygpsclient._version import __version__
from pygpsclient.about_dialog import AboutDialog
from pygpsclient.banner_frame import BannerFrame
from pygpsclient.console_frame import ConsoleFrame
from pygpsclient.file_handler import FileHandler
from pygpsclient.globals import ICON_APP, DISCONNECTED
from pygpsclient.graphview_frame import GraphviewFrame
from pygpsclient.map_frame import MapviewFrame
from pygpsclient.menu_bar import MenuBar
from pygpsclient.serial_handler import SerialHandler
from pygpsclient.ntrip_handler import NTRIPHandler
from pygpsclient.settings_frame import SettingsFrame
from pygpsclient.skyview_frame import SkyviewFrame
from pygpsclient.status_frame import StatusFrame
from pygpsclient.ubx_config_dialog import UBXConfigDialog
from pygpsclient.ntrip_client_dialog import NTRIPConfigDialog
from pygpsclient.nmea_handler import NMEAHandler
from pygpsclient.ubx_handler import UBXHandler

VERSION = __version__


class App(Frame):  # pylint: disable=too-many-ancestors
    """
    Main PyGPSClient GUI Application Class
    """

    def __init__(self, master, *args, **kwargs):
        """
        Set up main application and add frames

        :param tkinter.Tk master: reference to Tk root
        :param args: optional args to pass to Frame parent class
        :param kwargs: optional kwargs to pass to Frame parent class
        """

        self.__master = master

        Frame.__init__(self, self.__master, *args, **kwargs)

        self.__master.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.__master.title(TITLE)
        self.__master.iconphoto(True, PhotoImage(file=ICON_APP))

        # Set initial widget visibility
        self._show_settings = True
        self._show_ubxconfig = False
        self._show_status = True
        self._show_console = True
        self._show_map = True
        self._show_sats = True

        # Instantiate protocol handler classes
        self.file_handler = FileHandler(self)
        self.serial_handler = SerialHandler(self)
        self.nmea_handler = NMEAHandler(self)
        self.ubx_handler = UBXHandler(self)
        self.ntrip_handler = NTRIPHandler(self)
        self.dlg_ubxconfig = None
        self.dlg_ntripconfig = None
        self._ubx_config_thread = None
        self._ntrip_config_thread = None

        # Load web map api key if there is one
        self.api_key = self.file_handler.load_apikey()

        self._body()
        self._do_layout()
        self._attach_events()

        # Initialise widgets
        self.frm_satview.init_sats()
        self.frm_graphview.init_graph()
        self.frm_banner.update_conn_status(DISCONNECTED)

        # Dict containing latest GNSS readings from NMEA and/or UBX
        self._GNSS_status = {
            "utc": 0,
            "lat": 0.0,
            "lon": 0.0,
            "alt": 0.0,
            "speed": 0.0,
            "track": 0.0,
            "fix": 5,
            "siv": 0,
            "sip": 0,
            "pdop": 0.0,
            "hdop": 0.0,
            "vdop": 0.0,
            "hacc": 0.0,
            "vacc": 0.0,
            "sep": 0.0,
            "diffAge": 0,
            "diffStation": 0,
        }

    def _body(self):
        """
        Set up frame and widgets
        """

        # these grid weights are what gives the grid its
        # 'pack to window size' behaviour
        self.__master.grid_columnconfigure(0, weight=1)
        self.__master.grid_columnconfigure(1, weight=2)
        self.__master.grid_columnconfigure(2, weight=2)
        self.__master.grid_rowconfigure(0, weight=0)
        self.__master.grid_rowconfigure(1, weight=2)
        self.__master.grid_rowconfigure(2, weight=1)
        self._set_default_fonts()

        self.menu = MenuBar(self)
        self.frm_status = StatusFrame(self, borderwidth=2, relief="groove")
        self.frm_banner = BannerFrame(self, borderwidth=2, relief="groove")
        self.frm_settings = SettingsFrame(self, borderwidth=2, relief="groove")
        self.frm_console = ConsoleFrame(self, borderwidth=2, relief="groove")
        self.frm_mapview = MapviewFrame(self, borderwidth=2, relief="groove")
        self.frm_satview = SkyviewFrame(self, borderwidth=2, relief="groove")
        self.frm_graphview = GraphviewFrame(self, borderwidth=2, relief="groove")

        self.__master.config(menu=self.menu)

    def _do_layout(self):
        """
        Arrange widgets in main application frame
        """

        self.frm_banner.grid(
            column=0, row=0, columnspan=5, padx=2, pady=2, sticky=(N, S, E, W)
        )
        self._grid_console()
        self._grid_sats()
        self._grid_map()
        self._grid_status()
        self._grid_settings()

        if self.frm_settings.serial_settings().status == 3:  # NOPORTS
            self.set_status(INTROTXTNOPORTS, "red")

    def _attach_events(self):
        """
        Bind events to main application
        """

        self.__master.bind("<<ubx_read>>", self.serial_handler.on_read)
        self.__master.bind("<<ntrip_read>>", self.ntrip_handler.on_read)
        self.__master.bind("<<ubx_readfile>>", self.serial_handler.on_read)
        self.__master.bind("<<ubx_eof>>", self.serial_handler.on_eof)
        self.__master.bind_all("<Control-q>", self.on_exit)

    def _set_default_fonts(self):
        """
        Set default fonts for entire application
        """
        # pylint: disable=attribute-defined-outside-init

        self.font_vsm = font.Font(size=8)
        self.font_sm = font.Font(size=10)
        self.font_md = font.Font(size=12)
        self.font_md2 = font.Font(size=14)
        self.font_lg = font.Font(size=18)

    def toggle_settings(self):
        """
        Toggle Settings Frame on or off
        """

        self._show_settings = not self._show_settings
        self._grid_settings()

    def _grid_settings(self):
        """
        Set grid position of Settings Frame
        """

        if self._show_settings:
            self.frm_settings.grid(
                column=4, row=1, rowspan=2, padx=2, pady=2, sticky=(N, W, E)
            )
            self.menu.view_menu.entryconfig(0, label=MENUHIDESE)
        else:
            self.frm_settings.grid_forget()
            self.menu.view_menu.entryconfig(0, label=MENUSHOWSE)

    def toggle_status(self):
        """
        Toggle Status Bar on or off
        """

        self._show_status = not self._show_status
        self._grid_status()

    def _grid_status(self):
        """
        Position Status Bar in grid
        """

        if self._show_status:
            self.frm_status.grid(
                column=0, row=3, columnspan=5, padx=2, pady=2, sticky=(W, E)
            )
            self.menu.view_menu.entryconfig(1, label=MENUHIDESB)
        else:
            self.frm_status.grid_forget()
            self.menu.view_menu.entryconfig(1, label=MENUSHOWSB)

    def toggle_console(self):
        """
        Toggle Console frame on or off
        """

        self._show_console = not self._show_console
        self._grid_console()
        self._grid_sats()
        self._grid_map()

    def _grid_console(self):
        """
        Position Console Frame in grid
        """

        if self._show_console:
            self.frm_console.grid(
                column=0, row=1, columnspan=4, padx=2, pady=2, sticky=(N, S, E, W)
            )
            self.menu.view_menu.entryconfig(2, label=MENUHIDECON)
        else:
            self.frm_console.grid_forget()
            self.menu.view_menu.entryconfig(2, label=MENUSHOWCON)

    def toggle_sats(self):
        """
        Toggle Satview and Graphview frames on or off
        """

        self._show_sats = not self._show_sats
        self._grid_sats()
        self._grid_map()

    def _grid_sats(self):
        """
        Position Satview and Graphview Frames in grid
        """

        if self._show_sats:
            self.frm_satview.grid(column=0, row=2, padx=2, pady=2, sticky=(N, S, E, W))
            self.frm_graphview.grid(
                column=1, row=2, padx=2, pady=2, sticky=(N, S, E, W)
            )
            self.menu.view_menu.entryconfig(4, label=MENUHIDESATS)
        else:
            self.frm_satview.grid_forget()
            self.frm_graphview.grid_forget()
            self.menu.view_menu.entryconfig(4, label=MENUSHOWSATS)

    def toggle_map(self):
        """
        Toggle Map Frame on or off
        """

        self._show_map = not self._show_map
        self._grid_map()

    def _grid_map(self):
        """
        Position Map Frame in grid
        """

        if self._show_map:
            self.frm_mapview.grid(column=2, row=2, padx=2, pady=2, sticky=(N, S, E, W))
            self.menu.view_menu.entryconfig(3, label=MENUHIDEMAP)
        else:
            self.frm_mapview.grid_forget()
            self.menu.view_menu.entryconfig(3, label=MENUSHOWMAP)

    def set_connection(self, message, color="blue"):
        """
        Sets connection description in status bar.

        :param str message: message to be displayed in connection label
        :param str color: rgb color string

        """

        self.frm_status.set_connection(message, color)

    def set_status(self, message, color="black"):
        """
        Sets text of status bar

        :param str message: message to be displayed in status label
        :param str color: rgb color string

        """

        self.frm_status.set_status(message, color)

    def about(self):
        """
        Open About dialog
        """

        AboutDialog(self)

    def ubxconfig(self):
        """
        Start UBX Config dialog thread
        """

        if self._ubx_config_thread is None:
            self._ubx_config_thread = Thread(
                target=self._ubxconfig_thread, daemon=False
            )
            self._ubx_config_thread.start()

    def _ubxconfig_thread(self):
        """
        THREADED PROCESS UBX Configuration Dialog
        """

        self.dlg_ubxconfig = UBXConfigDialog(self)

    def stop_ubxconfig_thread(self):
        """
        Stop UBX Configuration dialog thread.
        """

        if self._ubx_config_thread is not None:
            self._ubx_config_thread = None
            self.dlg_ubxconfig = None

    def ntripconfig(self):
        """
        Start NTRIP Config dialog thread
        """

        if self._ntrip_config_thread is None:
            self._ntrip_config_thread = Thread(
                target=self._ntripconfig_thread, daemon=False
            )
            self._ntrip_config_thread.start()

    def _ntripconfig_thread(self):
        """
        THREADED PROCESS NTRIP Configuration Dialog
        """

        self.dlg_ntripconfig = NTRIPConfigDialog(self)

    def stop_ntripconfig_thread(self):
        """
        Stop UBX Configuration dialog thread.
        """

        if self._ntrip_config_thread is not None:
            self._ntrip_config_thread = None
            self.dlg_ntripconfig = None

    def get_master(self):
        """
        Returns application master (Tk)

        :return: reference to application master (Tk)
        """

        return self.__master

    def on_exit(self, *args, **kwargs):  # pylint: disable=unused-argument
        """
        Kill any running processes and quit application
        """

        self.serial_handler.stop_read_thread()
        self.serial_handler.stop_readfile_thread()
        self.stop_ubxconfig_thread()
        self.stop_ntripconfig_thread()
        self.serial_handler.disconnect()
        self.__master.destroy()

    @property
    def GNSS_status(self):
        """
        Getter for latest GNSS status.
        """

        return self._GNSS_status

    def set_GNSS_status(self, **kwargs):
        """
        Setter for latest GNSS status.

        :param object args: (kwarg) GNSS status parm e.g. lat, lon
        """

        for parm in kwargs:
            if parm in self._GNSS_status.keys():
                self._GNSS_status[parm] = kwargs[parm]

"""Application entry: tray icon, menu, persistence, CLI."""
import argparse
import os
import sys


def _prefer_xwayland():
    # Wayland does not let clients position windows or keep them at the bottom;
    # run through XWayland when possible.
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") \
            and os.environ.get("DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="desktop-rug", description="Desktop Rug - فرش دسکتاپ")
    ap.add_argument("--settings", help="settings JSON path (default: user config dir)")
    ap.add_argument("--image", help="use this rug image (PNG/JPG)")
    ap.add_argument("--reset", action="store_true", help="reset position/size/rotation")
    ap.add_argument("--folded", choices=["yes", "no"], help="start folded or flat")
    ap.add_argument("--demo-icons", help="fake hidden-icon positions 'x,y;x,y' (global px) for bump demo")
    ap.add_argument("--render-preview", metavar="OUT.png",
                    help="simulate + render an off-screen preview (wood desktop + rug) and exit")
    ap.add_argument("--preview-scenario", default="corner",
                    choices=["flat", "corner", "edge", "over", "double", "unfold", "bumps"],
                    help="what to simulate for --render-preview")
    ap.add_argument("--renderer", choices=["auto", "opengl", "software"], help="force a renderer")
    ap.add_argument("--stats", action="store_true", help="print renderer + fps to stdout")
    ap.add_argument("--geometry", help="cx,cy,w,h,angle (global logical px/deg)")
    ap.add_argument("--design", help="built-in rug design: " + ", ".join(d[0] for d in DESIGNS))
    g = ap.add_argument_group("install / autostart (no window is opened)")
    g.add_argument("--enable-autostart", action="store_true",
                   help="copy the app to the per-user install folder and start it at login")
    g.add_argument("--disable-autostart", action="store_true", help="stop starting at login (settings are kept)")
    g.add_argument("--quit-running", action="store_true", help="close a running Desktop Rug (saves its state)")
    g.add_argument("--uninstall", action="store_true",
                   help="disable autostart, close it, remove the installed copy and the settings")
    g.add_argument("--wallpaper", metavar="ID|FILE",
                   help="set the desktop wallpaper: " + ", ".join(f[0] for f in WP_FLOORS) + " or an image file")
    g.add_argument("--restore-wallpaper", action="store_true", help="restore the wallpaper you had before")
    ap.add_argument("--autostart", action="store_true", help=argparse.SUPPRESS)   # set by the login entry
    ap.add_argument("--version", action="store_true")
    return ap.parse_args(argv)


DESIGNS = [  # id, asset, English, Persian
    ("tabriz", "rug_default.png", "Tabriz — red", "تبریز — لاکی"),
    ("kashan", "rug_kashan.png", "Kashan — navy", "کاشان — سرمه‌ای"),
    ("nain", "rug_nain.png", "Nain — ivory & blue", "نائین — شیری و آبی"),
    ("qashqai", "rug_qashqai.png", "Qashqai — rust & green", "قشقایی — آجری و سبز"),
]
from desktop_rug.wallpaper import FLOORS as WP_FLOORS   # noqa: E402  (pure python, no Qt)


def _log_factory():
    """print + append to <config>/desktop-rug.log (the Windows exe has no console)."""
    def log(msg):
        print(msg, flush=True)
        try:
            from desktop_rug.install import config_dir
            import time
            with open(os.path.join(config_dir(), "desktop-rug.log"), "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
        except OSError:
            pass
    return log


def run_cli_actions(args):
    """--enable/--disable-autostart, --quit-running, --uninstall, wallpaper. Returns exit code or None."""
    from desktop_rug import install as I
    log = _log_factory()
    acted = False
    rc = 0
    try:
        if args.quit_running or args.disable_autostart or args.uninstall:
            if args.quit_running or args.uninstall:
                I.quit_running(log=log)
                acted = True
        if args.uninstall:
            I.uninstall(log=log)
            return 0
        if args.disable_autostart:
            I.disable_autostart(log=log)
            acted = True
        if args.enable_autostart:
            cmd = I.enable_autostart(log=log)
            log("installed command: %s" % " ".join(cmd))
            acted = True
        if args.wallpaper or args.restore_wallpaper:
            from desktop_rug import settings as S, wallpaper as WP
            sp = args.settings or S.settings_path()
            st = S.load(sp)
            if args.restore_wallpaper:
                ok, msg = WP.restore_original(st)
            else:
                path = WP.floor_path(args.wallpaper) or os.path.abspath(args.wallpaper)
                ok, msg = WP.set_wallpaper(path, st, tag="floor" if WP.floor_path(args.wallpaper) else "custom")
            S.save(st, sp)
            log(msg)
            rc = 0 if ok else 2
            acted = True
    except Exception as ex:
        log("error: %s" % ex)
        return 1
    return rc if acted else None


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    from desktop_rug import __version__, APP_NAME
    if args.version:
        print(APP_NAME, __version__)
        return 0
    rc = run_cli_actions(args)
    if rc is not None:
        return rc
    from desktop_rug import install as I
    lock = None
    if not args.render_preview:
        # single instance: take the lock first (before any login wait), so a
        # second start - autostart or manual - never runs alongside
        from PySide6.QtCore import QLockFile
        lock = QLockFile(I.lock_path())
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            I.request("show")          # ask the running instance to show itself
            print("Desktop Rug is already running.")
            return 0
        I.take_request("quit")         # a stale quit request must not close us
        I.take_request("show")
    if args.autostart:
        # started at login: run from the install folder and wait for the shell/desktop
        b = I.current_binary()
        if b:
            try:
                os.chdir(os.path.dirname(b))
            except OSError:
                pass
        I.wait_for_desktop()
    _prefer_xwayland()
    if args.render_preview and sys.platform.startswith("linux") and not os.environ.get("DISPLAY") \
            and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import Qt, QTimer, QPoint
    from PySide6.QtGui import QImage, QIcon, QPixmap, QPainter, QAction, QActionGroup, QGuiApplication
    from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QFileDialog,
                                   QMessageBox)
    from desktop_rug import settings as S, platform_support as PS
    from desktop_rug.rug_window import RugWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("desktop-rug")
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    builtin = os.path.join(assets, "rug_default.png")

    def design_path(did):
        for d in DESIGNS:
            if d[0] == did:
                return os.path.join(assets, d[1])
        return builtin
    settings_path = args.settings or S.settings_path()
    st = S.load(settings_path)
    if args.image:
        st.image = os.path.abspath(args.image)
    if args.renderer:
        st.renderer = args.renderer
    if args.design:
        st.design, st.image = args.design, ""
    cloth_path = os.path.splitext(settings_path)[0] + ".cloth.json"

    def load_image(path):
        img = QImage(path) if path else QImage()
        if img.isNull():
            img = QImage(design_path(st.design))
        if img.isNull():
            img = QImage(builtin)
        return img

    img = load_image(st.image)
    demo = []
    if args.demo_icons:
        for part in args.demo_icons.split(";"):
            if part.strip():
                x, y = part.split(",")
                demo.append((float(x), float(y)))

    if args.geometry:
        cx, cy, w, h, a = [float(v) for v in args.geometry.split(",")]
        st.cx, st.cy, st.w, st.h, st.angle = cx, cy, w, h, a
    if args.folded:
        st.folded = args.folded == "yes"

    # ------------------------------------------------------------ preview mode
    if args.render_preview:
        from desktop_rug.preview import render_scenario
        out = render_scenario(args.render_preview, args.preview_scenario, img, demo,
                              renderer_pref=st.renderer)
        print(out)
        return 0

    # ------------------------------------------------------------ single instance
    if args.autostart and sys.platform.startswith("linux"):
        # login: give the compositor (transparency) and the panel (tray) a moment
        import time
        t0 = time.time()
        while time.time() - t0 < 30 and not PS.x11_compositor_running():
            app.processEvents()
            time.sleep(0.5)
        t0 = time.time()
        while time.time() - t0 < 5 and not QSystemTrayIcon.isSystemTrayAvailable():
            app.processEvents()
            time.sleep(0.5)

    if args.reset:
        st.cx = st.cy = -1
        try:
            os.remove(cloth_path)
        except OSError:
            pass
    if args.geometry or args.folded:
        try:
            os.remove(cloth_path)
        except OSError:
            pass
    win = RugWindow(st, img, cloth_path=cloth_path, demo_icons=demo)
    if args.folded == "yes":
        win.cloth.set_positions(win.cloth.from_local(win.cloth.corner_fold_local(),
                                                     (st.cx, st.cy, st.angle)))
    if args.stats:
        print("RENDERER", win.renderer.name, getattr(win.renderer, "info", ""), flush=True)
        st_timer = QTimer()
        st_timer.timeout.connect(lambda: print("FPS %.1f sleeping=%s" % (win.fps, win.cloth.sleeping), flush=True))
        st_timer.start(2000)

    def save():
        try:
            S.save(st, settings_path)
        except OSError as ex:
            print("could not save settings:", ex, file=sys.stderr)

    win.stateChanged.connect(save)

    # ------------------------------------------------------------ menu
    menu = QMenu()
    act_show = QAction("Hide rug  |  پنهان کردن فرش", menu)
    act_fold = QAction("Lay flat / lift fold  |  صاف کردن / تا کردن", menu)
    m_design = QMenu("Rug design  |  طرح فرش", menu)
    design_group = QActionGroup(m_design)
    design_acts = {}
    for did, _f, en, fa in DESIGNS:
        a = QAction("%s  |  %s" % (en, fa), m_design, checkable=True)
        a.setActionGroup(design_group)
        a.triggered.connect(lambda _=False, d=did: set_design(d))
        m_design.addAction(a)
        design_acts[did] = a
    m_design.addSeparator()
    act_change = QAction("Custom image…  |  عکس دلخواه…", m_design, checkable=True)
    act_change.setActionGroup(design_group)
    m_design.addAction(act_change)

    m_bg = QMenu("Background (wallpaper)  |  پس‌زمینه", menu)
    for fid, _f, en, fa in WP_FLOORS:
        a = QAction("%s  |  %s" % (en, fa), m_bg)
        a.triggered.connect(lambda _=False, f=fid: set_floor(f))
        m_bg.addAction(a)
    m_bg.addSeparator()
    act_bg_custom = QAction("Custom image…  |  عکس دلخواه…", m_bg)
    act_bg_restore = QAction("Restore original wallpaper  |  برگرداندن پس‌زمینه‌ی قبلی", m_bg)
    m_bg.addAction(act_bg_custom)
    m_bg.addAction(act_bg_restore)
    act_bottom = QAction("Keep on desktop layer (below windows)", menu, checkable=True)
    act_bumps = QAction("Show bumps over hidden icons", menu, checkable=True)
    act_mask = QAction("Compatibility click-through mask", menu, checkable=True)
    act_auto = QAction("Start with system  |  اجرا با سیستم", menu, checkable=True)
    act_reset = QAction("Reset position / size", menu)
    act_about = QAction("About", menu)
    act_quit = QAction("Quit  |  خروج", menu)
    for a in (act_show, act_fold, None, m_design, m_bg, None, act_bottom, act_bumps,
              act_mask, act_auto, act_reset, None, act_about, act_quit):
        if a is None:
            menu.addSeparator()
        elif isinstance(a, QMenu):
            menu.addMenu(a)
        else:
            menu.addAction(a)

    def sync_menu():
        act_show.setText(("Hide rug  |  پنهان کردن فرش") if win.isVisible() else "Show rug  |  نمایش فرش")
        act_bottom.setChecked(st.bottom_layer)
        act_bumps.setChecked(st.bumps)
        act_mask.setChecked(st.hard_mask)
        act_auto.setChecked(PS.autostart_enabled())
        if st.image:
            act_change.setChecked(True)
        elif st.design in design_acts:
            design_acts[st.design].setChecked(True)
        act_bg_restore.setEnabled(bool(st.extra.get("orig_wallpaper_saved")))

    def toggle_show():
        if win.isVisible():
            win.hide()
            st.visible = False
        else:
            win.show()
            st.visible = True
        save()

    def change_image():
        path, _ = QFileDialog.getOpenFileName(None, "Choose a rug image", os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            sync_menu()
            return
        im = QImage(path)
        if im.isNull():
            QMessageBox.warning(None, APP_NAME, "Could not load image.")
            return
        st.image = path
        win.set_image(im)
        save()

    def set_design(did):
        st.design, st.image = did, ""
        win.set_image(QImage(design_path(did)))
        save()

    def wp_result(ok, msg):
        if not ok:
            QMessageBox.warning(None, APP_NAME, "Could not change the wallpaper:\n%s" % msg)
        save()

    def set_floor(fid):
        from desktop_rug import wallpaper as WP
        wp_result(*WP.set_wallpaper(WP.floor_path(fid), st, tag="floor"))

    def bg_custom():
        from desktop_rug import wallpaper as WP
        path, _ = QFileDialog.getOpenFileName(None, "Choose a wallpaper image", os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            wp_result(*WP.set_wallpaper(path, st, tag="custom"))

    def bg_restore():
        from desktop_rug import wallpaper as WP
        wp_result(*WP.restore_original(st))

    def set_auto(on):
        try:
            PS.set_autostart(on)
        except Exception as ex:
            QMessageBox.warning(None, APP_NAME, "Could not change autostart: %s" % ex)
        sync_menu()

    def set_bumps(on):
        st.bumps = on
        win.refresh_icons()
        save()

    def set_mask(on):
        st.hard_mask = on
        if not on:
            win.clearMask()
        win.update_shape()
        save()

    def about():
        QMessageBox.information(None, APP_NAME,
            "Desktop Rug %s — فرش دسکتاپ\n\nSweep your desktop mess under a Persian rug.\n"
            "Inspired by Terkel Gjervig's (@terkelg) macOS concept.\n\n"
            "• Grab any point of the rug and drag: it lifts and folds like real cloth\n"
            "• Click a folded rug to lay it flat; click the same spot again to re-fold\n"
            "• Ctrl+drag an edge: resize · Ctrl+drag, middle-drag or press-and-hold then drag: move\n"
            "• Shift+drag (or Alt+drag): rotate\n"
            "• Right-click the rug for this menu\n\nRenderer: %s\nRug artwork: procedurally generated, CC0."
            % (__version__, getattr(win.renderer, "info", win.renderer.name)))

    act_show.triggered.connect(toggle_show)
    act_fold.triggered.connect(win.toggle_fold)
    act_change.triggered.connect(change_image)
    act_bg_custom.triggered.connect(bg_custom)
    act_bg_restore.triggered.connect(bg_restore)
    act_bottom.toggled.connect(lambda on: (win.set_bottom_layer(on), save()))
    act_bumps.toggled.connect(set_bumps)
    act_mask.toggled.connect(set_mask)
    act_auto.triggered.connect(set_auto)
    act_reset.triggered.connect(win.reset_position)
    act_about.triggered.connect(about)
    act_quit.triggered.connect(lambda: (win._save_all(), app.quit()))
    menu.aboutToShow.connect(sync_menu)
    win.contextMenuRequested.connect(lambda pos: (sync_menu(), menu.popup(pos)))

    # tray icon from the centre of the rug
    icon_pm = QPixmap.fromImage(QImage(builtin)).copy(470, 170, 650, 650).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    app.setWindowIcon(QIcon(icon_pm))
    tray = None

    def make_tray():
        nonlocal tray
        if tray is not None or not QSystemTrayIcon.isSystemTrayAvailable():
            return tray is not None
        tray = QSystemTrayIcon(QIcon(icon_pm))
        tray.setToolTip("Desktop Rug — فرش دسکتاپ")
        tray.setContextMenu(menu)
        tray.activated.connect(lambda r: toggle_show() if r == QSystemTrayIcon.Trigger else None)
        tray.show()
        return True

    if not make_tray():
        print("No system tray available: right-click the rug for the menu.")
        # the panel may come up after us at login: keep trying for a minute
        tray_retry = QTimer()
        tray_retry_n = [0]

        def retry_tray():
            tray_retry_n[0] += 1
            if make_tray() or tray_retry_n[0] > 12:
                tray_retry.stop()
        tray_retry.timeout.connect(retry_tray)
        tray_retry.start(5000)

    if st.visible or tray is None:
        win.show()
    sync_menu()
    app.aboutToQuit.connect(win._save_all)

    # control requests from --quit-running / the Disable scripts / a second launch
    def poll_control():
        if I.take_request("quit"):
            win._save_all()
            app.quit()
        elif I.take_request("show"):
            win.show()
            st.visible = True
            save()
    ctl = QTimer()
    ctl.timeout.connect(poll_control)
    ctl.start(700)
    if not sys.platform.startswith("win"):
        import signal
        signal.signal(signal.SIGTERM, lambda *_: (win._save_all(), app.quit()))

    # default ON: first run of the packaged app enables autostart (installs a stable copy)
    def first_run():
        if I.first_run_enable(log=_log_factory()):
            sync_menu()
            if tray is not None:
                tray.showMessage(APP_NAME, "Desktop Rug will start with the system.\n"
                                 "فرش دسکتاپ از این به بعد با روشن شدن سیستم اجرا می‌شود.\n"
                                 "To turn it off: run the Disable file or untick 'Start with system'.",
                                 QSystemTrayIcon.Information, 8000)
    QTimer.singleShot(1500, first_run)
    rc = app.exec()
    if lock is not None:
        lock.unlock()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

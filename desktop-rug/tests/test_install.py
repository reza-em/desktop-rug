"""Autostart / control-file logic (Linux paths; runs anywhere without a GUI)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from desktop_rug import install as I   # noqa: E402


@unittest.skipUnless(sys.platform.startswith("linux"), "XDG autostart test")
class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "APPIMAGE")}
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.tmp.name, "cfg")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "data")
        os.environ.pop("APPIMAGE", None)

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_enable_disable_cycle(self):
        quiet = lambda *_: None
        self.assertFalse(I.autostart_enabled())
        I.enable_autostart(log=quiet)
        self.assertTrue(I.autostart_enabled())
        entry = open(I.autostart_file(), encoding="utf-8").read()
        self.assertIn("X-GNOME-Autostart-enabled=true", entry)
        self.assertIn("QT_QPA_PLATFORM=xcb", entry)
        launcher = open(I.launcher_script_path(), encoding="utf-8").read()
        self.assertIn("--autostart", launcher)
        self.assertIn("sleep", launcher)
        I.disable_autostart(log=quiet)
        self.assertFalse(I.autostart_enabled())
        self.assertTrue(os.path.exists(I.marker_path()))
        # explicit disable => first-run logic never re-enables it
        self.assertFalse(I.first_run_enable(log=quiet))
        self.assertFalse(I.autostart_enabled())

    def test_appimage_install_copy(self):
        src = os.path.join(self.tmp.name, "Downloads", "DesktopRug-x86_64.AppImage")
        os.makedirs(os.path.dirname(src))
        with open(src, "wb") as f:
            f.write(b"\x7fELF fake appimage")
        os.environ["APPIMAGE"] = src
        cmd = I.install_copy(log=lambda *_: None)
        self.assertEqual(cmd, [os.path.join(I.install_dir(), "DesktopRug.AppImage")])
        self.assertTrue(os.access(cmd[0], os.X_OK))
        os.remove(src)                      # downloaded file deleted: installed copy stays
        self.assertTrue(os.path.exists(cmd[0]))
        self.assertIn(".AppImage --version", open(I.write_launcher(cmd), encoding="utf-8").read())

    def test_control_requests(self):
        I.request("quit")
        self.assertTrue(I.take_request("quit"))
        self.assertFalse(I.take_request("quit"))


if __name__ == "__main__":
    unittest.main()

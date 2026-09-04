import win32con
import win32gui
import win32process


class WindowDisconnectDetector:
    """Detect Conquer disconnect dialogs without bringing windows to foreground.

    The detector enumerates Win32 top-level windows and their child controls,
    filters them by the target conquer.exe PID, and reads window/control text
    directly. This works even when the game page is behind another window.
    """

    DISCONNECT_PHRASES = (
        "disconnected with game server",
        "please login the game again",
    )

    def _collect_window_text(self, hwnd):
        parts = []

        try:
            title = win32gui.GetWindowText(hwnd)
            if title:
                parts.append(title)
        except Exception:
            pass

        def enum_child(child_hwnd, _):
            try:
                text = win32gui.GetWindowText(child_hwnd)
                if text:
                    parts.append(text)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumChildWindows(hwnd, enum_child, None)
        except Exception:
            pass

        return "\n".join(parts)

    def find_disconnect_dialog(self, pid):
        matches = []

        def enum_window(hwnd, _):
            try:
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True

            if window_pid != pid:
                return True

            text = self._collect_window_text(hwnd)
            lowered = text.lower()

            if all(phrase in lowered for phrase in self.DISCONNECT_PHRASES):
                matches.append({
                    "hwnd": hwnd,
                    "text": text,
                })
                return False

            return True

        try:
            win32gui.EnumWindows(enum_window, None)
        except Exception:
            pass

        return matches[0] if matches else None

    def has_disconnect_dialog(self, pid):
        return self.find_disconnect_dialog(pid) is not None

    def press_ok(self, pid):
        """Press the dialog's OK button directly by HWND, without focusing it."""
        dialog = self.find_disconnect_dialog(pid)
        if not dialog:
            return False

        hwnd = dialog["hwnd"]
        ok_button = None

        def enum_child(child_hwnd, _):
            nonlocal ok_button
            try:
                text = win32gui.GetWindowText(child_hwnd).strip().lower()
                class_name = win32gui.GetClassName(child_hwnd)
            except Exception:
                return True

            if class_name == "Button" and text in {"ok", "&ok"}:
                ok_button = child_hwnd
                return False

            return True

        try:
            win32gui.EnumChildWindows(hwnd, enum_child, None)
        except Exception:
            pass

        if not ok_button:
            return False

        try:
            win32gui.SendMessage(ok_button, win32con.BM_CLICK, 0, 0)
            return True
        except Exception:
            return False

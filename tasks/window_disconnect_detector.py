import time

import win32con
import win32gui
import win32process


class WindowDisconnectDetector:
    """Detect Conquer disconnect dialogs through Win32 window handles.

    This does not depend on the page being visible or in the foreground.
    It enumerates windows that belong to the target conquer.exe PID and reads
    their native window/control text directly.
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

    def _windows_for_pid(self, pid):
        windows = []

        def enum_window(hwnd, _):
            try:
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid == pid:
                    windows.append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(enum_window, None)
        except Exception:
            pass

        return windows

    def find_disconnect_dialog(self, pid):
        for hwnd in self._windows_for_pid(pid):
            text = self._collect_window_text(hwnd)
            lowered = text.lower()

            if all(phrase in lowered for phrase in self.DISCONNECT_PHRASES):
                return {
                    "hwnd": hwnd,
                    "text": text,
                }

        return None

    def has_disconnect_dialog(self, pid):
        return self.find_disconnect_dialog(pid) is not None

    def press_ok(self, pid):
        """Press the dialog OK button by HWND without needing screen focus."""
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
            time.sleep(0.3)
            return True
        except Exception:
            return False

    def activate_main_window(self, pid):
        """Bring the main visible Conquer window for this PID to foreground."""
        candidates = []

        for hwnd in self._windows_for_pid(pid):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    continue

                class_name = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                width = max(0, rect[2] - rect[0])
                height = max(0, rect[3] - rect[1])

                # Skip tiny/modal windows when selecting the main game page.
                if class_name == "#32770":
                    continue

                candidates.append((width * height, hwnd, title))
            except Exception:
                continue

        if not candidates:
            return False

        candidates.sort(reverse=True)
        _, hwnd, _ = candidates[0]

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.15)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.25)
            return True
        except Exception:
            return False

import psutil
import win32gui
import win32process


class PlusZeroWindowBridge:
    """Resolve the exact Conquer HWND that belongs to a login-session PID.

    The old google2 project discovered windows globally.  The merged program
    must instead bind bot work to the PID already owned by each login row so a
    bot can never jump to another manually opened Conquer page.
    """

    PROCESS_NAME = "conquer.exe"

    @staticmethod
    def _valid_process(pid):
        try:
            process = psutil.Process(int(pid))
            return process.name().lower() == PlusZeroWindowBridge.PROCESS_NAME
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, TypeError):
            return False

    @classmethod
    def hwnd_for_pid(cls, pid):
        if not pid or not cls._valid_process(pid):
            return None

        candidates = []

        def callback(hwnd, _):
            try:
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid != int(pid):
                    return True

                if not win32gui.IsWindowVisible(hwnd):
                    return True

                title = win32gui.GetWindowText(hwnd).strip()
                if not title:
                    return True

                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = max(0, right - left)
                height = max(0, bottom - top)

                # Ignore dialogs/tiny helper windows.  Keep the actual game page.
                if width < 700 or height < 500:
                    return True

                candidates.append((width * height, hwnd, title))
            except Exception:
                pass

            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            return None

        if not candidates:
            return None

        candidates.sort(reverse=True)
        return candidates[0][1]

    @classmethod
    def session_target(cls, row_index, session):
        """Return a normalized target record for one login-manager session."""
        session = session or {}
        pid = session.get("pid")
        hwnd = cls.hwnd_for_pid(pid)

        if hwnd is None:
            return None

        try:
            title = win32gui.GetWindowText(hwnd).strip()
        except Exception:
            title = ""

        return {
            "row_index": row_index,
            "pid": pid,
            "hwnd": hwnd,
            "title": title,
            "page_name": session.get("page_name", ""),
            "username": session.get("username", ""),
        }

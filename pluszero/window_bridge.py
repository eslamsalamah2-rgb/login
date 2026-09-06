class PlusZeroWindowBridge:
    """Use only the exact PID/HWND already registered by the login manager.

    The merged program must never scan all Conquer windows.  Login owns the
    page association; PlusZero only consumes that existing session data.
    """

    @classmethod
    def session_target(cls, row_index, session):
        session = session or {}

        pid = session.get("pid")
        hwnd = session.get("hwnd")

        if not pid or not hwnd:
            return None

        return {
            "row_index": row_index,
            "pid": int(pid),
            "hwnd": int(hwnd),
            "title": session.get("title", ""),
            "page_name": session.get("page_name", ""),
            "username": session.get("username", ""),
        }

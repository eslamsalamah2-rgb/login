import threading

from pluszero.window_bridge import PlusZeroWindowBridge


class PlusZeroController:
    """Integration coordinator owned by the login manager.

    Phase 1 only establishes safe account->PID->HWND targeting.  The migrated
    inventory/revive/sash engine will plug into this controller in later phases.
    """

    def __init__(self):
        self.window_bridge = PlusZeroWindowBridge()
        self._lock = threading.RLock()
        self._targets = {}

    def refresh_from_sessions(self, active_sessions):
        """Rebuild bot targets from the login manager's live sessions only."""
        targets = {}

        for row_index, session in list((active_sessions or {}).items()):
            target = self.window_bridge.session_target(row_index, session)
            if target is not None:
                targets[row_index] = target

        with self._lock:
            self._targets = targets

        return dict(targets)

    def target_for_row(self, row_index, active_sessions=None):
        if active_sessions is not None:
            session = (active_sessions or {}).get(row_index)
            target = self.window_bridge.session_target(row_index, session)
            if target is not None:
                with self._lock:
                    self._targets[row_index] = target
                return target

        with self._lock:
            return self._targets.get(row_index)

    def remove_row(self, row_index):
        with self._lock:
            self._targets.pop(row_index, None)

    def clear(self):
        with self._lock:
            self._targets.clear()

    def snapshot(self):
        with self._lock:
            return dict(self._targets)

import threading

from maintenance_launcher import MaintenanceAwareLauncher
from tasks.memory_reader import ConquerMemoryReader


class ControlAwareLauncher(MaintenanceAwareLauncher):
    """Adds a true global pause/resume layer.

    Alt+A / the pause button pauses:
    - account-sequence processing
    - image/template tasks
    - post-login message scanning
    - the 10-second memory state monitor

    Existing game pages are left open. Resume continues from the current
    account pointer instead of starting from account 1.
    """

    def __init__(self):
        # This must exist before SimpleLauncher.__init__ starts the monitor
        # thread, because Python dispatches to this overridden monitor method.
        self.monitor_pause_event = threading.Event()
        super().__init__()

    def pause_processing(self):
        # Pause the background memory scanner immediately, even when the main
        # account sequence has already finished and only monitoring is active.
        self.monitor_pause_event.set()
        self.pause_requested = True

        # Ask every active task to stop its own loop as soon as possible.
        try:
            self.start_game_task.stop()
        except Exception:
            pass

        try:
            self.login_task.stop()
        except Exception:
            pass

        try:
            self.login_button_task.stop()
        except Exception:
            pass

        try:
            self.post_login_task.stop()
        except Exception:
            pass

        self.set_status(
            f"إيقاف مؤقت كامل - تم إيقاف التشغيل والـMemory Scan عند الحساب {self.current_account_index + 1}"
        )

    def resume_processing(self):
        # Resume monitoring first. If all accounts had already been opened,
        # there may be no sequence work left, but monitoring should still run.
        self.monitor_pause_event.clear()
        self.pause_requested = False

        if self.is_running:
            self.set_status("تم استكمال الـMemory Scan - عملية الحساب الحالية ما زالت تعمل")
            return

        if not self.save_accounts_from_ui():
            return

        if self.current_account_index >= len(self.accounts_data):
            self.set_status("تم استكمال مراقبة الحسابات المفتوحة")
            return

        self.is_running = True
        self.run_in_thread(self.process_accounts)

    def start_from_beginning(self):
        # A fresh start also guarantees that the monitor is enabled.
        self.monitor_pause_event.clear()
        super().start_from_beginning()

    def monitor_active_sessions(self):
        """Monitor successful accounts every 10 seconds unless globally paused."""
        while not self.monitor_stop_event.is_set():
            if self.monitor_pause_event.is_set():
                # Wake frequently enough that Resume feels immediate while
                # doing no memory reads during the paused state.
                self.monitor_stop_event.wait(0.25)
                continue

            sessions = list(self.active_sessions.items())

            for row_index, session in sessions:
                # Alt+A may be pressed while walking the current session list.
                if self.monitor_pause_event.is_set() or self.monitor_stop_event.is_set():
                    break

                pid = session.get("pid")

                if not pid:
                    continue

                reader = None
                value = None

                try:
                    reader = ConquerMemoryReader(pid)
                    value = reader.read_state()
                except Exception as error:
                    print(
                        f"State monitor could not open PID {pid}: {error}"
                    )
                finally:
                    if reader is not None:
                        reader.close()

                state_text = ConquerMemoryReader.state_name(value)

                print(
                    f"State monitor - account {row_index + 1} - PID {pid} - "
                    f"Value: {value} - {state_text}"
                )

                if value == ConquerMemoryReader.STATE_LOGGED_IN:
                    self.set_row_state(row_index, "success")
                else:
                    self.set_row_state(row_index, "error")

            # Wait up to 10 seconds, but allow Pause/Close to interrupt quickly.
            for _ in range(40):
                if self.monitor_stop_event.is_set() or self.monitor_pause_event.is_set():
                    break
                self.monitor_stop_event.wait(0.25)

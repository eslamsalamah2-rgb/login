import time

from control_launcher import ControlAwareLauncher
from tasks.memory_reader import ConquerMemoryReader
from tasks.post_login_message_task import PostLoginMessageTask


class HealthAwareLauncher(ControlAwareLauncher):
    """Monitor each account using its own learned healthy memory signature.

    Healthy = same PID + same character name + same state value learned after
    the account has successfully logged in. No global LOGGED_IN number is used.
    """

    def _read_health(self, pid):
        if not pid or pid not in ConquerMemoryReader.list_conquer_pids():
            return None, None

        reader = None
        try:
            reader = ConquerMemoryReader(pid)
            return reader.read_name() or "", reader.read_state()
        except Exception as error:
            print(f"Health read failed for PID {pid}: {error}")
            return None, None
        finally:
            if reader is not None:
                reader.close()

    def _session_is_healthy(self, session, current_name, current_state):
        expected_name = session.get("page_name", "")
        healthy_state = session.get("healthy_state")

        return (
            current_name is not None
            and current_state is not None
            and bool(expected_name)
            and current_name == expected_name
            and healthy_state is not None
            and current_state == healthy_state
        )

    def _recover_logged_out_account(self, row_index, session):
        """Relog an unhealthy page and learn its new healthy signature."""
        if not self._mark_recovery_started(row_index):
            return

        try:
            if self.is_running or self.pause_requested or self.monitor_pause_event.is_set():
                return

            with self.recovery_lock:
                if self.pause_requested or self.monitor_pause_event.is_set():
                    return

                pid = session.get("pid")
                username = session.get("username", "")
                password = session.get("password", "")
                expected_name = session.get("page_name", "")

                if not pid or not username or not password:
                    self.set_row_state(row_index, "error")
                    return

                if pid not in ConquerMemoryReader.list_conquer_pids():
                    self.set_row_state(row_index, "error")
                    self.set_status(f"الحساب {row_index + 1}: صفحة اللعبة اتقفلت")
                    return

                self.set_row_state(row_index, "working")
                self.set_status(
                    f"الحساب {row_index + 1} حالته اتغيرت - جاري تسجيل الدخول من جديد..."
                )

                if not self.login_task.start(username=username, password=password):
                    if not self.pause_requested:
                        self.set_row_state(row_index, "error")
                    return

                if self.pause_requested or self.monitor_pause_event.is_set():
                    return

                if not self.login_button_task.start():
                    self.set_row_state(row_index, "error")
                    return

                message_type = self.post_login_task.wait_for_message(timeout=6.0)

                if self._handle_global_login_condition(message_type):
                    return

                if message_type == PostLoginMessageTask.DISCONNECTED:
                    self.post_login_task.press_ok()
                    time.sleep(0.7)
                    if not self.login_button_task.start():
                        self.set_row_state(row_index, "error")
                        return
                    message_type = self.post_login_task.wait_for_message(timeout=6.0)
                    if self._handle_global_login_condition(message_type):
                        return

                if message_type == PostLoginMessageTask.WRONG_PASSWORD:
                    self.post_login_task.press_ok()
                    time.sleep(0.5)
                    if not self.login_task.rewrite_password(password):
                        self.set_row_state(row_index, "error")
                        return
                    if not self.login_button_task.start():
                        self.set_row_state(row_index, "error")
                        return
                    message_type = self.post_login_task.wait_for_message(timeout=6.0)
                    if self._handle_global_login_condition(message_type):
                        return
                    if message_type == PostLoginMessageTask.WRONG_PASSWORD:
                        self.post_login_task.press_ok()
                        self.set_row_state(row_index, "error")
                        return

                # Wait until the same character name returns. At that moment,
                # whatever state value this character has becomes its new
                # healthy baseline. This avoids all hard-coded state numbers.
                while not self.pause_requested and not self.monitor_pause_event.is_set():
                    if pid not in ConquerMemoryReader.list_conquer_pids():
                        self.set_row_state(row_index, "error")
                        return

                    current_name, current_state = self._read_health(pid)
                    print(
                        f"Recovery health - account {row_index + 1} - PID {pid} - "
                        f"Name: {current_name!r} - State: {current_state}"
                    )

                    if current_name == expected_name and current_state is not None:
                        session["healthy_state"] = current_state
                        self.active_sessions[row_index] = session
                        self.set_row_state(row_index, "success", expected_name)
                        self.set_status(
                            f"الحساب {row_index + 1}: رجع شغال - Healthy State = {current_state}"
                        )
                        return

                    time.sleep(2.0)

        finally:
            self._mark_recovery_finished(row_index)

    def monitor_active_sessions(self):
        """Every 10 seconds verify PID + character name + learned state value."""
        while not self.monitor_stop_event.is_set():
            if self.monitor_pause_event.is_set():
                self.monitor_stop_event.wait(0.25)
                continue

            sessions = list(self.active_sessions.items())

            for row_index, session in sessions:
                if self.monitor_pause_event.is_set() or self.monitor_stop_event.is_set():
                    break

                pid = session.get("pid")
                current_name, current_state = self._read_health(pid)

                # Learn the successful state separately for every character.
                # Registration happens only after run_account reports SUCCESS.
                if session.get("healthy_state") is None and current_state is not None:
                    session["healthy_state"] = current_state
                    self.active_sessions[row_index] = session
                    print(
                        f"Health baseline learned - account {row_index + 1} - "
                        f"PID {pid} - Name: {session.get('page_name')!r} - "
                        f"Healthy State: {current_state}"
                    )

                healthy = self._session_is_healthy(
                    session,
                    current_name,
                    current_state
                )

                print(
                    f"Health monitor - account {row_index + 1} - PID {pid} - "
                    f"Name: {current_name!r}/{session.get('page_name')!r} - "
                    f"State: {current_state}/{session.get('healthy_state')} - "
                    f"{'HEALTHY' if healthy else 'UNHEALTHY'}"
                )

                if healthy:
                    self.set_row_state(row_index, "success")
                else:
                    self.set_row_state(row_index, "error")

                    # Do not fight with the normal account-opening workflow.
                    if not self.is_running:
                        self.run_in_thread(
                            lambda idx=row_index, sess=dict(session):
                                self._recover_logged_out_account(idx, sess)
                        )

            # Ten-second scan interval, interruptible by Alt+A / Pause.
            for _ in range(40):
                if self.monitor_stop_event.is_set() or self.monitor_pause_event.is_set():
                    break
                self.monitor_stop_event.wait(0.25)

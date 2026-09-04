import time

from control_launcher import ControlAwareLauncher
from tasks.memory_reader import ConquerMemoryReader
from tasks.post_login_message_task import PostLoginMessageTask
from tasks.window_disconnect_detector import WindowDisconnectDetector
from tasks.timer_heartbeat_detector import TimerHeartbeatDetector


class HealthAwareLauncher(ControlAwareLauncher):
    """Monitor accounts cheaply, then visually confirm only suspicious pages."""

    def __init__(self):
        self.window_disconnect_detector = WindowDisconnectDetector()
        self.timer_heartbeat_detector = TimerHeartbeatDetector()
        super().__init__()

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

    def _session_is_healthy(self, session, current_name, current_state, disconnected=False):
        expected_name = session.get("page_name", "")
        healthy_state = session.get("healthy_state")

        return (
            not disconnected
            and current_name is not None
            and current_state is not None
            and bool(expected_name)
            and current_name == expected_name
            and healthy_state is not None
            and current_state == healthy_state
        )

    def _refresh_baseline_from_live_page(self, row_index, session):
        pid = session.get("pid")
        current_name, current_state = self._read_health(pid)

        if current_state is None:
            return False

        page_name = current_name or session.get("page_name", "")

        session["pid"] = pid
        session["page_name"] = page_name
        session["healthy_state"] = current_state
        self.active_sessions[row_index] = session

        if 0 <= row_index < len(self.accounts_data):
            self.accounts_data[row_index]["character_name"] = page_name
            self.account_manager.save_accounts(self.accounts_data)

        self.set_row_state(row_index, "success", page_name)
        self.set_status(
            f"الحساب {row_index + 1}: العداد شغال - تم اعتماد البيانات الحالية كـBaseline جديد"
        )

        print(
            f"Live baseline refreshed - account {row_index + 1} - PID {pid} - "
            f"Name: {page_name!r} - Healthy State: {current_state}"
        )
        return True

    def _timer_stop_requested(self):
        return (
            self.pause_requested
            or self.monitor_pause_event.is_set()
            or self.monitor_stop_event.is_set()
        )

    def _reopen_missing_account(self, row_index, session):
        """Open a brand-new page only for the account whose old PID disappeared."""
        if not self._mark_recovery_started(row_index):
            return

        try:
            if self.is_running or self._timer_stop_requested():
                return

            with self.recovery_lock:
                if self.is_running or self._timer_stop_requested():
                    return

                username = session.get("username", "")
                password = session.get("password", "")
                path = self.path_entry.get().strip()

                if not username or not password or not path:
                    self.set_row_state(row_index, "error")
                    self.set_status(
                        f"الحساب {row_index + 1}: بيانات الحساب أو مسار play.exe غير مكتمل"
                    )
                    return

                old_pid = session.get("pid")
                print(
                    f"Missing page detected - account {row_index + 1} - old PID {old_pid} - reopening"
                )

                self.set_row_state(row_index, "working")
                self.set_status(
                    f"الحساب {row_index + 1}: الصفحة اختفت - جاري فتح صفحة جديدة لنفس الحساب..."
                )

                result, page_name = self.run_account(
                    path=path,
                    username=username,
                    password=password,
                    account_number=row_index + 1,
                    total_accounts=len(self.accounts_data),
                )

                if result == "SUCCESS":
                    # run_account already registered the new PID/session. Leave
                    # healthy_state empty so the next monitor pass learns the
                    # fresh value from this newly created page.
                    if 0 <= row_index < len(self.accounts_data):
                        self.accounts_data[row_index]["character_name"] = page_name or ""
                        self.account_manager.save_accounts(self.accounts_data)

                    self.set_row_state(row_index, "success", page_name or "")
                    self.set_status(
                        f"الحساب {row_index + 1}: تم فتح صفحة جديدة وتسجيل الدخول بنجاح"
                    )
                    print(
                        f"Missing page recovery success - account {row_index + 1} - Name: {page_name!r}"
                    )
                    return

                if result == "SERVER_MAINTENANCE":
                    ConquerMemoryReader.terminate_all_conquer()
                    self.active_sessions.clear()
                    self.current_account_index = 0
                    self.reset_all_row_states()

                    if self._wait_maintenance_retry() and not self._timer_stop_requested():
                        self.is_running = True
                        self.run_in_thread(self.process_accounts)
                    return

                if result == "CLIENT_UPDATE":
                    ConquerMemoryReader.terminate_all_conquer()
                    self.active_sessions.clear()
                    self.current_account_index = 0
                    self.reset_all_row_states()

                    if self._wait_update_retry() and not self._timer_stop_requested():
                        self.is_running = True
                        self.run_in_thread(self.process_accounts)
                    return

                self.set_row_state(row_index, "error")
                self.set_status(
                    f"الحساب {row_index + 1}: فشل فتح الصفحة الجديدة - {result}"
                )
                print(
                    f"Missing page recovery failed - account {row_index + 1} - {result}"
                )

        finally:
            self._mark_recovery_finished(row_index)

    def _verify_with_timer_before_recovery(self, row_index, session):
        """Run the heavier screenshot heartbeat only for a suspicious page."""
        if self.is_running or self._timer_stop_requested():
            return

        pid = session.get("pid")
        if not pid or pid not in ConquerMemoryReader.list_conquer_pids():
            self._reopen_missing_account(row_index, session)
            return

        self.set_status(
            f"الحساب {row_index + 1}: فحص تأكيدي للعداد قبل إعادة الدخول..."
        )

        result = self.timer_heartbeat_detector.check(
            pid,
            stop_check=self._timer_stop_requested,
        )

        print(
            f"Timer confirmation - account {row_index + 1} - PID {pid} - {result}"
        )

        if result == TimerHeartbeatDetector.ACTIVE:
            self._refresh_baseline_from_live_page(row_index, session)
            return

        if self._timer_stop_requested():
            return

        self._recover_logged_out_account(row_index, session)

    def _recover_logged_out_account(self, row_index, session):
        """Relog an unhealthy/background-disconnected page and relearn baseline."""
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
                    # The page vanished after recovery had already started.
                    # Release this recovery marker, then reopen on next pass.
                    self.set_row_state(row_index, "error")
                    self.set_status(f"الحساب {row_index + 1}: صفحة اللعبة اختفت")
                    return

                if self.window_disconnect_detector.has_disconnect_dialog(pid):
                    print(
                        f"Background disconnect detected - account {row_index + 1} - PID {pid}"
                    )
                    self.set_status(
                        f"الحساب {row_index + 1}: Disconnected في الخلفية - جاري إعادة الدخول..."
                    )
                    self.window_disconnect_detector.press_ok(pid)
                    time.sleep(0.5)

                self.window_disconnect_detector.activate_main_window(pid)
                time.sleep(0.3)

                self.set_row_state(row_index, "working")
                self.set_status(
                    f"الحساب {row_index + 1} حالته غير سليمة - جاري تسجيل الدخول من جديد..."
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

                while not self.pause_requested and not self.monitor_pause_event.is_set():
                    if pid not in ConquerMemoryReader.list_conquer_pids():
                        self.set_row_state(row_index, "error")
                        return

                    current_name, current_state = self._read_health(pid)
                    disconnected = self.window_disconnect_detector.has_disconnect_dialog(pid)

                    print(
                        f"Recovery health - account {row_index + 1} - PID {pid} - "
                        f"Name: {current_name!r} - State: {current_state} - "
                        f"DisconnectDialog: {disconnected}"
                    )

                    if (
                        current_name == expected_name
                        and current_state is not None
                        and not disconnected
                    ):
                        session["page_name"] = current_name or expected_name
                        session["healthy_state"] = current_state
                        self.active_sessions[row_index] = session
                        self.set_row_state(
                            row_index,
                            "success",
                            session["page_name"],
                        )
                        self.set_status(
                            f"الحساب {row_index + 1}: رجع شغال - Healthy State = {current_state}"
                        )
                        return

                    time.sleep(2.0)

        finally:
            self._mark_recovery_finished(row_index)

    def monitor_active_sessions(self):
        """Cheap checks every 10 seconds; timer screenshot only on suspicion."""
        while not self.monitor_stop_event.is_set():
            if self.monitor_pause_event.is_set():
                self.monitor_stop_event.wait(0.25)
                continue

            sessions = list(self.active_sessions.items())
            live_pids = set(ConquerMemoryReader.list_conquer_pids())

            for row_index, session in sessions:
                if self.monitor_pause_event.is_set() or self.monitor_stop_event.is_set():
                    break

                pid = session.get("pid")

                # Missing process/page is definitive. Do not waste time on the
                # visual heartbeat; open a fresh page for this account only.
                if not pid or pid not in live_pids:
                    print(
                        f"Health monitor - account {row_index + 1} - PID {pid} - MISSING PAGE"
                    )
                    self.set_row_state(row_index, "error")

                    if not self.is_running:
                        self.run_in_thread(
                            lambda idx=row_index, sess=dict(session):
                                self._reopen_missing_account(idx, sess)
                        )
                    continue

                current_name, current_state = self._read_health(pid)
                disconnected = self.window_disconnect_detector.has_disconnect_dialog(pid)

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
                    current_state,
                    disconnected=disconnected,
                )

                print(
                    f"Health monitor - account {row_index + 1} - PID {pid} - "
                    f"Name: {current_name!r}/{session.get('page_name')!r} - "
                    f"State: {current_state}/{session.get('healthy_state')} - "
                    f"DisconnectDialog: {disconnected} - "
                    f"{'HEALTHY' if healthy else 'UNHEALTHY'}"
                )

                if healthy:
                    self.set_row_state(row_index, "success")
                    continue

                self.set_row_state(row_index, "error")

                if self.is_running:
                    continue

                if disconnected:
                    self.run_in_thread(
                        lambda idx=row_index, sess=dict(session):
                            self._recover_logged_out_account(idx, sess)
                    )
                else:
                    self.run_in_thread(
                        lambda idx=row_index, sess=dict(session):
                            self._verify_with_timer_before_recovery(idx, sess)
                    )

            for _ in range(40):
                if self.monitor_stop_event.is_set() or self.monitor_pause_event.is_set():
                    break
                self.monitor_stop_event.wait(0.25)

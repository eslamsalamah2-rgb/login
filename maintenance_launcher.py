import time

import win32gui
import win32process

from gui import SimpleLauncher
from tasks.memory_reader import ConquerMemoryReader
from tasks.post_login_message_task import PostLoginMessageTask


class MaintenanceAwareLauncher(SimpleLauncher):
    """SimpleLauncher with maintenance and client-update recovery."""

    MAINTENANCE_RETRY_SECONDS = 60
    UPDATE_RETRY_SECONDS = 5

    @staticmethod
    def _foreground_hwnd_for_pid(pid):
        """Return the current foreground HWND only if it belongs to this PID.

        No global window scan is performed. The login flow has already focused
        the exact Conquer page, so we simply capture that known window handle.
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if int(window_pid) != int(pid):
                return None
            return int(hwnd)
        except Exception:
            return None

    def _maintenance_result(self, memory_reader):
        self.post_login_task.press_ok()

        if memory_reader is not None:
            memory_reader.close()

        return "SERVER_MAINTENANCE", None

    def _client_update_result(self, memory_reader):
        self.post_login_task.press_ok()

        if memory_reader is not None:
            memory_reader.close()

        return "CLIENT_UPDATE", None

    def _wait_maintenance_retry(self):
        remaining = self.MAINTENANCE_RETRY_SECONDS

        while remaining > 0:
            if self.pause_requested:
                return False

            self.set_status(
                f"صيانة السيرفر - المحاولة التالية بعد {remaining} ثانية"
            )

            time.sleep(1.0)
            remaining -= 1

        return True

    def _wait_update_retry(self):
        remaining = self.UPDATE_RETRY_SECONDS

        while remaining > 0:
            if self.pause_requested:
                return False

            self.set_status(
                f"يوجد Update - إعادة فتح اللعبة بعد {remaining} ثانية"
            )
            time.sleep(1.0)
            remaining -= 1

        return True

    def _wait_for_login_ready(
        self,
        memory_reader,
        conquer_pid,
        username,
        password,
        initial_name,
        account_number,
        total_accounts,
        timeout=120.0,
    ):
        """Wait for a real logged-in character while continuously handling dialogs.

        The old flow checked post-login dialogs for only a few seconds and then
        waited on memory alone. If a dialog appeared later, the program could sit
        forever reading an empty name. This loop keeps both checks alive together.
        """
        start_time = time.time()
        password_retries = 0
        check_number = 0

        while time.time() - start_time < timeout:
            if self.pause_requested:
                return "PAUSED", None

            check_number += 1
            page_name = memory_reader.read_name() or ""
            current_state = memory_reader.read_state()

            print(
                f"Login ready check #{check_number} - PID {conquer_pid} - "
                f"Name: {page_name!r} - State: {current_state} "
                f"({ConquerMemoryReader.state_name(current_state)})"
            )

            if page_name and page_name != (initial_name or ""):
                return "SUCCESS", page_name

            # Keep watching the screen while memory is still not ready. A popup
            # can appear after the original six-second post-login window.
            message_type = self.post_login_task.detect()

            if message_type == PostLoginMessageTask.SERVER_MAINTENANCE:
                return "SERVER_MAINTENANCE", None

            if message_type == PostLoginMessageTask.CLIENT_UPDATE:
                return "CLIENT_UPDATE", None

            if message_type == PostLoginMessageTask.DISCONNECTED:
                self.set_status(
                    f"الحساب {account_number}/{total_accounts}: Disconnected - إعادة Log In..."
                )
                self.post_login_task.press_ok()
                time.sleep(0.7)

                if not self.login_button_task.start():
                    return "LOGIN_BUTTON_ERROR", None

                time.sleep(0.8)
                continue

            if message_type == PostLoginMessageTask.WRONG_PASSWORD:
                password_retries += 1
                self.set_status(
                    f"الحساب {account_number}/{total_accounts}: رسالة باسورد - إعادة كتابة الباسورد..."
                )
                self.post_login_task.press_ok()
                time.sleep(0.5)

                if password_retries > 2:
                    return "PAGE_ERROR", None

                if not self.login_task.rewrite_password(password):
                    return "PASSWORD_RETRY_ERROR", None

                if not self.login_button_task.start():
                    return "LOGIN_BUTTON_ERROR", None

                time.sleep(0.8)
                continue

            self.set_status(
                f"الحساب {account_number}/{total_accounts}: انتظار اكتمال الدخول ومراقبة أي رسالة..."
            )
            time.sleep(0.75)

        return "MEMORY_NAME_TIMEOUT", None

    def process_accounts(self):
        path = self.path_entry.get().strip()
        accounts = list(self.accounts_data)
        total_accounts = len(accounts)

        if not path:
            self.set_status("لم يتم اختيار play.exe")
            self.is_running = False
            return

        while self.current_account_index < total_accounts:
            if self.pause_requested:
                self.is_running = False
                self.set_status(
                    f"متوقف مؤقتًا - الحساب التالي رقم {self.current_account_index + 1}"
                )
                return

            index = self.current_account_index
            account = accounts[index]

            self.set_row_state(index, "working")

            result, page_name = self.run_account(
                path=path,
                username=account["username"],
                password=account["password"],
                account_number=index + 1,
                total_accounts=total_accounts
            )

            if result == "SERVER_MAINTENANCE":
                self.set_status(
                    "تم اكتشاف صيانة السيرفر - جاري إغلاق كل صفحات Conquer..."
                )

                closed_count = ConquerMemoryReader.terminate_all_conquer()
                print(
                    f"Server maintenance: closed {closed_count} conquer.exe process(es)"
                )

                self.active_sessions.clear()
                self.current_account_index = 0
                self.reset_all_row_states()

                if not self._wait_maintenance_retry():
                    self.is_running = False
                    self.set_status("متوقف مؤقتًا أثناء انتظار صيانة السيرفر")
                    return

                continue

            if result == "CLIENT_UPDATE":
                self.set_status(
                    "تم اكتشاف Update - جاري إغلاق كل صفحات Conquer وإعادة فتح اللعبة..."
                )

                closed_count = ConquerMemoryReader.terminate_all_conquer()
                print(
                    f"Client update: closed {closed_count} conquer.exe process(es)"
                )

                self.active_sessions.clear()
                self.current_account_index = 0
                self.reset_all_row_states()

                if not self._wait_update_retry():
                    self.is_running = False
                    self.set_status("متوقف مؤقتًا أثناء انتظار الـ Update")
                    return

                continue

            if result != "SUCCESS":
                self.set_row_state(index, "error", page_name or "")
                self.is_running = False
                self.set_status(
                    f"الحساب {index + 1}: فشل - {result}"
                )
                return

            self.set_row_state(index, "success", page_name)

            accounts[index]["character_name"] = page_name
            self.accounts_data = accounts
            self.account_manager.save_accounts(accounts)

            self.current_account_index = index + 1

            if self.pause_requested:
                self.is_running = False
                self.set_status(
                    f"متوقف مؤقتًا - الحساب التالي رقم {self.current_account_index + 1}"
                )
                return

            self.set_status(
                f"الحساب {index + 1}/{total_accounts}: تم - {page_name}"
            )
            time.sleep(1.0)

        self.is_running = False
        self.set_status(f"تم الانتهاء من {total_accounts} حساب")

    def run_account(self, path, username, password, account_number, total_accounts):
        previous_conquer_pids = ConquerMemoryReader.list_conquer_pids()

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري فتح صفحة جديدة..."
        )

        success, message = self.launcher.open(path)

        if not success:
            return "OPEN_ERROR", None

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري البحث عن Start Game..."
        )

        found = self.start_game_task.start()

        if not found:
            return "START_GAME_ERROR", None

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري تحديد conquer.exe الجديد..."
        )

        conquer_pid = ConquerMemoryReader.wait_for_new_conquer_pid(
            previous_conquer_pids,
            timeout=20.0
        )

        if conquer_pid is None:
            return "CONQUER_PID_ERROR", None

        try:
            memory_reader = ConquerMemoryReader(conquer_pid)
        except Exception as error:
            print(f"Could not open Conquer PID {conquer_pid}: {error}")
            return "MEMORY_OPEN_ERROR", None

        initial_name = memory_reader.read_name() or ""
        initial_state = memory_reader.read_state()

        print(
            f"Conquer PID {conquer_pid} initial name: {initial_name!r}"
        )
        print(
            f"Conquer PID {conquer_pid} initial state: "
            f"{initial_state} ({ConquerMemoryReader.state_name(initial_state)})"
        )

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري إدخال بيانات الدخول..."
        )

        login_done = self.login_task.start(
            username=username,
            password=password
        )

        if not login_done:
            memory_reader.close()
            return "LOGIN_FIELDS_ERROR", None

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري الضغط على Log In..."
        )

        if not self.login_button_task.start():
            memory_reader.close()
            return "LOGIN_BUTTON_ERROR", None

        # Keep one short immediate check for fast dialogs, then hand over to the
        # combined memory+dialog watcher below. This prevents late popups from
        # being ignored while waiting for the character name.
        message_type = self.post_login_task.wait_for_message(timeout=2.0)

        if message_type == PostLoginMessageTask.SERVER_MAINTENANCE:
            return self._maintenance_result(memory_reader)

        if message_type == PostLoginMessageTask.CLIENT_UPDATE:
            return self._client_update_result(memory_reader)

        if message_type == PostLoginMessageTask.DISCONNECTED:
            self.post_login_task.press_ok()
            time.sleep(0.7)
            if not self.login_button_task.start():
                memory_reader.close()
                return "LOGIN_BUTTON_ERROR", None

        if message_type == PostLoginMessageTask.WRONG_PASSWORD:
            self.post_login_task.press_ok()
            time.sleep(0.5)
            if not self.login_task.rewrite_password(password):
                memory_reader.close()
                return "PASSWORD_RETRY_ERROR", None
            if not self.login_button_task.start():
                memory_reader.close()
                return "LOGIN_BUTTON_ERROR", None

        ready_result, page_name = self._wait_for_login_ready(
            memory_reader=memory_reader,
            conquer_pid=conquer_pid,
            username=username,
            password=password,
            initial_name=initial_name,
            account_number=account_number,
            total_accounts=total_accounts,
            timeout=120.0,
        )

        if ready_result == "SERVER_MAINTENANCE":
            return self._maintenance_result(memory_reader)

        if ready_result == "CLIENT_UPDATE":
            return self._client_update_result(memory_reader)

        if ready_result != "SUCCESS":
            memory_reader.close()
            return ready_result, None

        final_state = memory_reader.read_state()
        print(
            f"Conquer PID {conquer_pid} state after login: "
            f"{final_state} ({ConquerMemoryReader.state_name(final_state)})"
        )

        memory_reader.close()

        hwnd = self._foreground_hwnd_for_pid(conquer_pid)

        print(
            f"Account {account_number} ready - PID {conquer_pid} - HWND {hwnd} - Name: {page_name}"
        )

        self.active_sessions[account_number - 1] = {
            "pid": conquer_pid,
            "hwnd": hwnd,
            "username": username,
            "password": password,
            "page_name": page_name,
        }

        return "SUCCESS", page_name

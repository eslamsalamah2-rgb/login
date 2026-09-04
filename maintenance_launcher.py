import time

from gui import SimpleLauncher
from tasks.memory_reader import ConquerMemoryReader
from tasks.post_login_message_task import PostLoginMessageTask


class MaintenanceAwareLauncher(SimpleLauncher):
    """SimpleLauncher with automatic server-maintenance recovery.

    When the maintenance dialog appears after Log In:
    1. Click OK.
    2. Close every conquer.exe page.
    3. Wait 60 seconds.
    4. Restart the account sequence from account 1.
    5. Repeat once per minute until maintenance is gone.

    Existing successful-account monitoring remains handled by SimpleLauncher.
    """

    MAINTENANCE_RETRY_SECONDS = 60

    def _maintenance_result(self, memory_reader):
        self.post_login_task.press_ok()

        if memory_reader is not None:
            memory_reader.close()

        return "SERVER_MAINTENANCE", None

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

                # All previously registered sessions are now closed.
                self.active_sessions.clear()
                self.current_account_index = 0
                self.reset_all_row_states()

                if not self._wait_maintenance_retry():
                    self.is_running = False
                    self.set_status("متوقف مؤقتًا أثناء انتظار صيانة السيرفر")
                    return

                # Retry from account 1. If maintenance still exists, the same
                # flow repeats and waits another minute.
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

        message_type = self.post_login_task.wait_for_message(
            timeout=6.0
        )

        if message_type == PostLoginMessageTask.SERVER_MAINTENANCE:
            return self._maintenance_result(memory_reader)

        if message_type == PostLoginMessageTask.DISCONNECTED:
            self.set_status(
                f"الحساب {account_number}/{total_accounts}: Disconnected - إعادة Log In..."
            )

            self.post_login_task.press_ok()
            time.sleep(0.7)

            if not self.login_button_task.start():
                memory_reader.close()
                return "LOGIN_BUTTON_ERROR", None

            message_type = self.post_login_task.wait_for_message(
                timeout=6.0
            )

            if message_type == PostLoginMessageTask.SERVER_MAINTENANCE:
                return self._maintenance_result(memory_reader)

        if message_type == PostLoginMessageTask.WRONG_PASSWORD:
            self.set_status(
                f"الحساب {account_number}/{total_accounts}: مراجعة الباسورد..."
            )

            self.post_login_task.press_ok()
            time.sleep(0.5)

            if not self.login_task.rewrite_password(password):
                memory_reader.close()
                return "PASSWORD_RETRY_ERROR", None

            if not self.login_button_task.start():
                memory_reader.close()
                return "LOGIN_BUTTON_ERROR", None

            second_message = self.post_login_task.wait_for_message(
                timeout=6.0
            )

            if second_message == PostLoginMessageTask.SERVER_MAINTENANCE:
                return self._maintenance_result(memory_reader)

            if second_message == PostLoginMessageTask.WRONG_PASSWORD:
                self.post_login_task.press_ok()
                memory_reader.close()
                return "PAGE_ERROR", None

            if second_message == PostLoginMessageTask.DISCONNECTED:
                self.post_login_task.press_ok()
                time.sleep(0.7)

                if not self.login_button_task.start():
                    memory_reader.close()
                    return "LOGIN_BUTTON_ERROR", None

                # One more short dialog check after the extra Log In so a
                # maintenance message cannot leave us waiting on memory forever.
                third_message = self.post_login_task.wait_for_message(
                    timeout=6.0
                )

                if third_message == PostLoginMessageTask.SERVER_MAINTENANCE:
                    return self._maintenance_result(memory_reader)

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري قراءة اسم الشخصية من Memory..."
        )

        # Keep the existing name-address confirmation behavior. The state
        # monitor continues checking the 4-byte state every 10 seconds after
        # this account succeeds.
        page_name = memory_reader.wait_for_name_change(
            previous_value=initial_name,
            timeout=20.0,
            require_change=True
        )

        final_state = memory_reader.read_state()
        print(
            f"Conquer PID {conquer_pid} state after login: "
            f"{final_state} ({ConquerMemoryReader.state_name(final_state)})"
        )

        memory_reader.close()

        if not page_name:
            return "MEMORY_NAME_TIMEOUT", None

        print(
            f"Account {account_number} ready - PID {conquer_pid} - Name: {page_name}"
        )

        self.active_sessions[account_number - 1] = {
            "pid": conquer_pid,
            "username": username,
            "page_name": page_name,
        }

        return "SUCCESS", page_name

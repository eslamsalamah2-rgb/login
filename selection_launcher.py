import time
import customtkinter as ctk

from clear_all_launcher import ClearAllAwareLauncher
from tasks.memory_reader import ConquerMemoryReader


class SelectionAwareLauncher(ClearAllAwareLauncher):
    """Adds per-account checkboxes so only selected accounts are processed."""

    def __init__(self):
        self.selected_run_only = True
        super().__init__()

        controls = self.resume_button.master

        self.select_all_button = ctk.CTkButton(
            controls,
            text="تحديد الكل",
            width=105,
            height=40,
            command=self.select_all_accounts,
        )
        self.select_all_button.pack(side="right", padx=6, pady=10)

        self.clear_selection_button = ctk.CTkButton(
            controls,
            text="إلغاء التحديد",
            width=115,
            height=40,
            command=self.clear_account_selection,
        )
        self.clear_selection_button.pack(side="right", padx=6, pady=10)

    def create_account_row(self, account=None):
        super().create_account_row(account)

        row = self.account_rows[-1]

        # Shift the existing row one column right and put the selection box first.
        for key in ("number", "username", "password", "name", "lamp", "delete"):
            widget = row[key]
            info = widget.grid_info()
            widget.grid_configure(column=int(info.get("column", 0)) + 1)

        selected_var = ctk.BooleanVar(value=True)
        selected_box = ctk.CTkCheckBox(
            row["frame"],
            text="",
            width=28,
            variable=selected_var,
            onvalue=True,
            offvalue=False,
        )
        selected_box.grid(row=0, column=0, padx=(6, 0), pady=7)

        row["selected_var"] = selected_var
        row["selected_box"] = selected_box

    def select_all_accounts(self):
        for row in self.account_rows:
            var = row.get("selected_var")
            if var is not None:
                var.set(True)
        self.set_status("تم تحديد كل الحسابات")

    def clear_account_selection(self):
        for row in self.account_rows:
            var = row.get("selected_var")
            if var is not None:
                var.set(False)
        self.set_status("تم إلغاء تحديد كل الحسابات")

    def _is_account_selected(self, index):
        if not (0 <= index < len(self.account_rows)):
            return False
        var = self.account_rows[index].get("selected_var")
        return bool(var.get()) if var is not None else True

    def _selected_indices(self):
        return [
            index
            for index in range(len(self.account_rows))
            if self._is_account_selected(index)
        ]

    def start_from_beginning(self):
        selected = self._selected_indices()
        if not selected:
            self.set_status("حدد حساب واحد على الأقل قبل التشغيل")
            return
        super().start_from_beginning()

    def resume_processing(self):
        selected = [
            index for index in self._selected_indices()
            if index >= self.current_account_index
        ]

        # If monitoring is merely paused after all selected accounts opened,
        # let the parent resume the monitor even though there is no new account.
        if not selected and self.current_account_index < len(self.account_rows):
            self.set_status("لا توجد حسابات محددة متبقية بعد نقطة الاستكمال الحالية")
            return

        super().resume_processing()

    def process_accounts(self):
        path = self.path_entry.get().strip()
        accounts = list(self.accounts_data)
        total_accounts = len(accounts)
        selected_indices = set(self._selected_indices())

        if not path:
            self.set_status("لم يتم اختيار play.exe")
            self.is_running = False
            return

        if not selected_indices:
            self.is_running = False
            self.set_status("لا توجد حسابات محددة للتشغيل")
            return

        while self.current_account_index < total_accounts:
            if self.pause_requested:
                self.is_running = False
                self.set_status("متوقف مؤقتًا")
                return

            index = self.current_account_index

            # Skip every unticked row without opening or touching it.
            if index not in selected_indices:
                self.set_row_state(index, "idle")
                self.current_account_index = index + 1
                continue

            account = accounts[index]
            self.set_row_state(index, "working")

            result, page_name = self.run_account(
                path=path,
                username=account["username"],
                password=account["password"],
                account_number=index + 1,
                total_accounts=total_accounts,
            )

            if result == "SERVER_MAINTENANCE":
                self.set_status("تم اكتشاف صيانة السيرفر - جاري إغلاق كل صفحات Conquer...")
                ConquerMemoryReader.terminate_all_conquer()
                self.active_sessions.clear()
                self.current_account_index = 0
                self.reset_all_row_states()

                if not self._wait_maintenance_retry():
                    self.is_running = False
                    self.set_status("متوقف مؤقتًا أثناء انتظار صيانة السيرفر")
                    return
                continue

            if result == "CLIENT_UPDATE":
                self.set_status("تم اكتشاف Update - جاري إغلاق كل صفحات Conquer وإعادة الفتح...")
                ConquerMemoryReader.terminate_all_conquer()
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
                self.set_status(f"الحساب {index + 1}: فشل - {result}")
                return

            self.set_row_state(index, "success", page_name)
            accounts[index]["character_name"] = page_name
            self.accounts_data = accounts
            self.account_manager.save_accounts(accounts)
            self.current_account_index = index + 1

            if self.pause_requested:
                self.is_running = False
                self.set_status("متوقف مؤقتًا")
                return

            selected_done = sum(1 for i in selected_indices if i < self.current_account_index)
            self.set_status(
                f"تم تشغيل {selected_done}/{len(selected_indices)} من الحسابات المحددة - {page_name}"
            )
            time.sleep(1.0)

        self.is_running = False
        self.set_status(f"تم الانتهاء من {len(selected_indices)} حساب محدد")

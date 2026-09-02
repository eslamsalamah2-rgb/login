import customtkinter as ctk
from tkinter import filedialog
import keyboard
import threading
import json
import os
import time

from launcher import Launcher
from account_manager import AccountManager
from tasks.start_game_task import StartGameTask
from tasks.login_task import LoginTask
from tasks.login_button_task import LoginButtonTask
from tasks.post_login_message_task import PostLoginMessageTask
from tasks.memory_reader import ConquerMemoryReader
from config import (
    CONFIG_FILE,
    WINDOW_TITLE,
    WINDOW_SIZE,
    START_HOTKEY,
    STOP_HOTKEY
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SimpleLauncher:

    def __init__(self):

        self.app = ctk.CTk()
        self.app.title(WINDOW_TITLE)
        self.app.geometry(WINDOW_SIZE)
        self.app.resizable(False, False)

        self.launcher = Launcher()
        self.account_manager = AccountManager()
        self.start_game_task = StartGameTask()
        self.login_task = LoginTask()
        self.login_button_task = LoginButtonTask()
        self.post_login_task = PostLoginMessageTask()

        self.stop_requested = False

        self.build_ui()
        self.load_settings()

        keyboard.add_hotkey(
            START_HOTKEY,
            lambda: self.run_in_thread(self.open_selected)
        )

        keyboard.add_hotkey(
            STOP_HOTKEY,
            lambda: self.run_in_thread(self.stop_selected)
        )

        self.app.protocol("WM_DELETE_WINDOW", self.close_program)

    def build_ui(self):

        title = ctk.CTkLabel(
            self.app,
            text="PAGE LAUNCHER",
            font=("Segoe UI", 26, "bold")
        )
        title.pack(pady=(25, 15))

        self.path_entry = ctk.CTkEntry(
            self.app,
            width=560,
            height=40,
            placeholder_text="لم يتم اختيار ملف..."
        )
        self.path_entry.pack(pady=10)

        buttons_frame = ctk.CTkFrame(
            self.app,
            fg_color="transparent"
        )
        buttons_frame.pack(pady=15)

        select_button = ctk.CTkButton(
            buttons_frame,
            text="اختيار الصفحة",
            width=160,
            height=40,
            command=self.select_file
        )
        select_button.grid(row=0, column=0, padx=8)

        open_button = ctk.CTkButton(
            buttons_frame,
            text="فتح  Alt + S",
            width=160,
            height=40,
            command=lambda: self.run_in_thread(self.open_selected)
        )
        open_button.grid(row=0, column=1, padx=8)

        stop_button = ctk.CTkButton(
            buttons_frame,
            text="إيقاف  Alt + A",
            width=160,
            height=40,
            command=lambda: self.run_in_thread(self.stop_selected)
        )
        stop_button.grid(row=0, column=2, padx=8)

        self.status_label = ctk.CTkLabel(
            self.app,
            text="جاهز",
            font=("Segoe UI", 14)
        )
        self.status_label.pack(pady=10)

    def select_file(self):

        path = filedialog.askopenfilename(
            title="اختار الصفحة أو البرنامج",
            filetypes=[
                ("All Files", "*.*"),
                ("Programs", "*.exe"),
                ("HTML Pages", "*.html *.htm"),
                ("Shortcuts", "*.lnk")
            ]
        )

        if not path:
            return

        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, path)
        self.save_settings()
        self.set_status("تم اختيار الملف")

    def run_account(self, path, username, password, account_number, total_accounts):

        if self.stop_requested:
            return "STOPPED"

        # Snapshot currently-open Conquer pages before opening this account.
        previous_conquer_pids = ConquerMemoryReader.list_conquer_pids()

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري فتح صفحة جديدة..."
        )

        success, message = self.launcher.open(path)

        if not success:
            self.set_status(message)
            return "OPEN_ERROR"

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري البحث عن Start Game..."
        )

        found = self.start_game_task.start()

        if not found or self.stop_requested:
            return "START_GAME_ERROR"

        # Start Game should create one new conquer.exe process.
        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري تحديد PID الصفحة الجديدة..."
        )

        conquer_pid = ConquerMemoryReader.wait_for_new_conquer_pid(
            previous_conquer_pids,
            timeout=20.0
        )

        if conquer_pid is None:
            return "CONQUER_PID_ERROR"

        try:
            memory_reader = ConquerMemoryReader(conquer_pid)
        except Exception as error:
            print(f"Could not open Conquer PID {conquer_pid}: {error}")
            return "MEMORY_OPEN_ERROR"

        initial_name = memory_reader.read_name() or ""
        print(
            f"Conquer PID {conquer_pid} initial name: {initial_name!r}"
        )

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري إدخال بيانات الدخول..."
        )

        login_done = self.login_task.start(
            username=username,
            password=password
        )

        if not login_done or self.stop_requested:
            memory_reader.close()
            return "LOGIN_FIELDS_ERROR"

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري الضغط على Log In..."
        )

        button_done = self.login_button_task.start()

        if not button_done or self.stop_requested:
            memory_reader.close()
            return "LOGIN_BUTTON_ERROR"

        message_type = self.post_login_task.wait_for_message(
            timeout=6.0
        )

        # Case 1: credentials are fine, server asks for another Log In.
        if message_type == PostLoginMessageTask.DISCONNECTED:
            self.set_status(
                f"الحساب {account_number}/{total_accounts}: Disconnected - إعادة Log In..."
            )

            self.post_login_task.press_ok()
            time.sleep(0.7)

            if not self.login_button_task.start():
                memory_reader.close()
                return "LOGIN_BUTTON_ERROR"

            message_type = self.post_login_task.wait_for_message(
                timeout=6.0
            )

        # Case 2: retry the saved password once. If Wrong Password appears
        # again after an explicit rewrite, report PAGE_ERROR to the main flow.
        if message_type == PostLoginMessageTask.WRONG_PASSWORD:
            self.set_status(
                f"الحساب {account_number}/{total_accounts}: مراجعة الباسورد..."
            )

            self.post_login_task.press_ok()
            time.sleep(0.5)

            password_done = self.login_task.rewrite_password(
                password
            )

            if not password_done:
                memory_reader.close()
                return "PASSWORD_RETRY_ERROR"

            if not self.login_button_task.start():
                memory_reader.close()
                return "LOGIN_BUTTON_ERROR"

            second_message = self.post_login_task.wait_for_message(
                timeout=6.0
            )

            if second_message == PostLoginMessageTask.WRONG_PASSWORD:
                self.post_login_task.press_ok()
                memory_reader.close()
                return "PAGE_ERROR"

            if second_message == PostLoginMessageTask.DISCONNECTED:
                self.post_login_task.press_ok()
                time.sleep(0.7)

                if not self.login_button_task.start():
                    memory_reader.close()
                    return "LOGIN_BUTTON_ERROR"

        # Final proof that this page actually entered the game:
        # conquer.exe + 0x8E6184 must change to a non-empty character/page name.
        self.set_status(
            f"الحساب {account_number}/{total_accounts}: جاري التأكد من اسم الصفحة من الذاكرة..."
        )

        page_name = memory_reader.wait_for_name_change(
            previous_value=initial_name,
            timeout=20.0,
            require_change=True
        )

        memory_reader.close()

        if not page_name:
            return "MEMORY_NAME_TIMEOUT"

        print(
            f"Account {account_number} ready - PID {conquer_pid} - Name: {page_name}"
        )

        self.set_status(
            f"الحساب {account_number}/{total_accounts}: تم الدخول - {page_name}"
        )

        return "SUCCESS"

    def open_selected(self):

        self.stop_requested = False
        path = self.path_entry.get().strip()

        accounts = self.account_manager.load_accounts()

        # If accounts.json exists and has accounts, open one new page per account.
        if accounts:
            total_accounts = len(accounts)

            for index, account in enumerate(accounts, start=1):
                if self.stop_requested:
                    self.set_status("تم الإيقاف")
                    return

                result = self.run_account(
                    path=path,
                    username=account["username"],
                    password=account["password"],
                    account_number=index,
                    total_accounts=total_accounts
                )

                if result == "PAGE_ERROR":
                    self.set_status(
                        f"الحساب {index}: PAGE_ERROR - الصفحة تحتاج معالجة من البرنامج الرئيسي"
                    )
                    return

                if result != "SUCCESS":
                    self.set_status(
                        f"الحساب {index}: فشل - {result}"
                    )
                    return

                self.set_status(
                    f"الحساب {index}/{total_accounts}: تم - الانتقال للحساب التالي..."
                )

                time.sleep(1.0)

            self.set_status(
                f"تم الانتهاء من {total_accounts} حساب"
            )
            return

        # Backward-compatible single-account mode using credentials.json.
        username, password = self.login_task.load_credentials()

        if not username or not password:
            self.set_status(
                "لا يوجد accounts.json ولا بيانات صالحة في credentials.json"
            )
            return

        result = self.run_account(
            path=path,
            username=username,
            password=password,
            account_number=1,
            total_accounts=1
        )

        if result == "PAGE_ERROR":
            self.set_status(
                "PAGE_ERROR - الصفحة تحتاج معالجة من البرنامج الرئيسي"
            )
        elif result == "SUCCESS":
            self.set_status("تم تسجيل الدخول")
        else:
            self.set_status(f"فشل - {result}")

    def stop_selected(self):

        self.stop_requested = True
        self.start_game_task.stop()
        self.login_task.stop()
        self.login_button_task.stop()
        self.post_login_task.stop()
        self.launcher.stop()

        self.set_status("تم الإيقاف")

    def save_settings(self):

        try:
            data = {
                "selected_path": self.path_entry.get().strip()
            }

            with open(
                CONFIG_FILE,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=4
                )

        except Exception:
            pass

    def load_settings(self):

        if not os.path.exists(CONFIG_FILE):
            return

        try:
            with open(
                CONFIG_FILE,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            path = data.get("selected_path", "")

            if path:
                self.path_entry.insert(0, path)
                self.set_status("تم تحميل آخر مسار")

        except Exception:
            pass

    def set_status(self, text):

        self.app.after(
            0,
            lambda: self.status_label.configure(text=text)
        )

    def run_in_thread(self, function):

        threading.Thread(
            target=function,
            daemon=True
        ).start()

    def close_program(self):

        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        self.app.destroy()

    def run(self):
        self.app.mainloop()

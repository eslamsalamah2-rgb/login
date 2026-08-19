import customtkinter as ctk
from tkinter import filedialog
import keyboard
import threading
import json
import os

from launcher import Launcher
from tasks.start_game_task import StartGameTask
from tasks.login_task import LoginTask
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
        self.start_game_task = StartGameTask()
        self.login_task = LoginTask()

        self.build_ui()
        self.load_settings()

        keyboard.add_hotkey(
            START_HOTKEY,
            lambda: self.run_in_thread(
                self.open_selected
            )
        )

        keyboard.add_hotkey(
            STOP_HOTKEY,
            lambda: self.run_in_thread(
                self.stop_selected
            )
        )

        self.app.protocol(
            "WM_DELETE_WINDOW",
            self.close_program
        )

    def build_ui(self):

        title = ctk.CTkLabel(
            self.app,
            text="PAGE LAUNCHER",
            font=("Segoe UI", 26, "bold")
        )

        title.pack(
            pady=(25, 15)
        )

        self.path_entry = ctk.CTkEntry(
            self.app,
            width=560,
            height=40,
            placeholder_text="لم يتم اختيار ملف..."
        )

        self.path_entry.pack(
            pady=10
        )

        buttons_frame = ctk.CTkFrame(
            self.app,
            fg_color="transparent"
        )

        buttons_frame.pack(
            pady=15
        )

        select_button = ctk.CTkButton(
            buttons_frame,
            text="اختيار الصفحة",
            width=160,
            height=40,
            command=self.select_file
        )

        select_button.grid(
            row=0,
            column=0,
            padx=8
        )

        open_button = ctk.CTkButton(
            buttons_frame,
            text="فتح  Alt + S",
            width=160,
            height=40,
            command=lambda: self.run_in_thread(
                self.open_selected
            )
        )

        open_button.grid(
            row=0,
            column=1,
            padx=8
        )

        stop_button = ctk.CTkButton(
            buttons_frame,
            text="إيقاف  Alt + A",
            width=160,
            height=40,
            command=lambda: self.run_in_thread(
                self.stop_selected
            )
        )

        stop_button.grid(
            row=0,
            column=2,
            padx=8
        )

        self.status_label = ctk.CTkLabel(
            self.app,
            text="جاهز",
            font=("Segoe UI", 14)
        )

        self.status_label.pack(
            pady=10
        )

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

        self.path_entry.delete(
            0,
            "end"
        )

        self.path_entry.insert(
            0,
            path
        )

        self.save_settings()

        self.set_status(
            "تم اختيار الملف"
        )

    def open_selected(self):

        path = self.path_entry.get().strip()

        success, message = self.launcher.open(
            path
        )

        self.set_status(
            message
        )

        if not success:
            return

        self.set_status(
            "جاري البحث عن Start Game..."
        )

        found = self.start_game_task.start()

        if not found:
            self.set_status(
                "لم يتم العثور على Start Game"
            )
            return

        self.set_status(
            "تم الضغط على Start Game - جاري انتظار خانات الدخول..."
        )

        login_done = self.login_task.start()

        if login_done:
            self.set_status(
                "تم إدخال بيانات الدخول"
            )
        else:
            self.set_status(
                "لم يتم العثور على خانات الدخول أو بيانات الدخول غير موجودة"
            )

    def stop_selected(self):

        self.start_game_task.stop()
        self.login_task.stop()
        self.launcher.stop()

        self.set_status(
            "تم الإيقاف"
        )

    def save_settings(self):

        try:

            data = {
                "selected_path":
                    self.path_entry.get().strip()
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

        if not os.path.exists(
            CONFIG_FILE
        ):
            return

        try:

            with open(
                CONFIG_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            path = data.get(
                "selected_path",
                ""
            )

            if path:

                self.path_entry.insert(
                    0,
                    path
                )

                self.set_status(
                    "تم تحميل آخر مسار"
                )

        except Exception:
            pass

    def set_status(self, text):

        self.app.after(
            0,
            lambda: self.status_label.configure(
                text=text
            )
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

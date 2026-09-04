import os
import time
import json
import cv2
import numpy as np
import pydirectinput
import win32gui
import win32process

from PIL import ImageGrab
from tasks.base_task import BaseTask
from tasks.window_disconnect_detector import WindowDisconnectDetector


class LoginTask(BaseTask):

    def __init__(self):
        super().__init__()

        self.template_path = os.path.join(
            "assets",
            "login_fields.png"
        )

        self.credentials_path = "credentials.json"
        self.threshold = 0.80
        self.target_pid = None
        self.window_helper = WindowDisconnectDetector()

    def set_target_pid(self, pid):
        self.target_pid = pid

    def _foreground_pid(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return pid
        except Exception:
            return None

    def _ensure_target_window(self):
        """Bring the intended Conquer PID forward and verify it owns focus.

        This prevents credentials from being typed into another manually opened
        Conquer page that happens to show the same login form.
        """
        if not self.target_pid:
            return True

        for _ in range(4):
            self.window_helper.activate_main_window(self.target_pid)
            time.sleep(0.12)

            if self._foreground_pid() == self.target_pid:
                return True

            time.sleep(0.12)

        print(
            f"Login safety: could not focus target PID {self.target_pid}; typing blocked"
        )
        return False

    def load_credentials(self):

        if not os.path.exists(self.credentials_path):
            return None, None

        try:
            with open(
                self.credentials_path,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            username = str(data.get("username", ""))
            password = str(data.get("password", ""))

            if not username or not password:
                return None, None

            return username, password

        except Exception:
            return None, None

    def find_login_fields(self):

        if not os.path.exists(self.template_path):
            print("Login fields image not found")
            return None

        template = cv2.imread(
            self.template_path,
            cv2.IMREAD_COLOR
        )

        if template is None:
            return None

        template_h, template_w = template.shape[:2]

        screenshot = ImageGrab.grab()
        screen = np.array(screenshot)
        screen = cv2.cvtColor(
            screen,
            cv2.COLOR_RGB2BGR
        )

        result = cv2.matchTemplate(
            screen,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        _, max_value, _, max_location = cv2.minMaxLoc(result)

        print(f"Login fields Match: {max_value:.3f}")

        if max_value < self.threshold:
            return None

        left = max_location[0]
        top = max_location[1]

        username_x = left + int(template_w * 0.82)
        username_y = top + int(template_h * 0.25)

        password_x = left + int(template_w * 0.43)
        password_y = top + int(template_h * 0.76)

        password_clear_x = left + int(template_w * 0.82)

        return (
            username_x,
            username_y,
            password_x,
            password_y,
            password_clear_x
        )

    def clear_username_field(self):
        for _ in range(10):
            pydirectinput.press("backspace")
            time.sleep(0.02)

    def clear_password_field(self):
        for _ in range(20):
            pydirectinput.press("backspace")
            time.sleep(0.02)

    def _type_exact(self, text, interval=0.04):
        text = str(text)

        caps_was_on = False
        try:
            import ctypes
            caps_was_on = bool(ctypes.windll.user32.GetKeyState(0x14) & 0x0001)
        except Exception:
            caps_was_on = False

        try:
            if caps_was_on:
                pydirectinput.press("capslock")
                time.sleep(0.08)

            for char in text:
                # If the user manually changes pages while typing, stop before
                # sending another character to the wrong Conquer process.
                if self.target_pid and self._foreground_pid() != self.target_pid:
                    raise RuntimeError(
                        f"Target focus lost while typing; expected PID {self.target_pid}"
                    )

                if "A" <= char <= "Z":
                    key = char.lower()
                    pydirectinput.keyDown("shift")
                    pydirectinput.press(key)
                    pydirectinput.keyUp("shift")
                else:
                    pydirectinput.write(char)

                if interval:
                    time.sleep(interval)

        finally:
            try:
                pydirectinput.keyUp("shift")
            except Exception:
                pass

            if caps_was_on:
                pydirectinput.press("capslock")
                time.sleep(0.08)

    def start(self, username=None, password=None, target_pid=None):

        self.running = True

        if target_pid is not None:
            self.target_pid = target_pid

        if username is None or password is None:
            username, password = self.load_credentials()

        if not username or not password:
            print("Login credentials missing or incomplete")
            self.running = False
            return False

        start_time = time.time()

        while self.running:

            if time.time() - start_time > 30:
                print("Login fields not found")
                self.running = False
                return False

            if not self._ensure_target_window():
                time.sleep(0.25)
                continue

            positions = self.find_login_fields()

            if positions:
                (
                    username_x,
                    username_y,
                    password_x,
                    password_y,
                    _
                ) = positions

                # Re-check immediately before touching the keyboard/mouse.
                if not self._ensure_target_window():
                    time.sleep(0.20)
                    continue

                try:
                    pydirectinput.click(username_x, username_y)
                    time.sleep(0.20)

                    self.clear_username_field()
                    time.sleep(0.10)

                    self._type_exact(username, interval=0.04)
                    time.sleep(0.20)

                    if not self._ensure_target_window():
                        continue

                    pydirectinput.click(password_x, password_y)
                    time.sleep(0.15)
                    self._type_exact(password, interval=0.04)
                except RuntimeError as error:
                    print(f"Login safety: {error}")
                    time.sleep(0.25)
                    continue

                print(
                    f"Login credentials entered for {username} on target PID {self.target_pid}"
                )

                self.running = False
                return True

            time.sleep(0.5)

        return False

    def rewrite_password(self, password, timeout=5.0, target_pid=None):
        if not password:
            return False

        if target_pid is not None:
            self.target_pid = target_pid

        start_time = time.time()
        positions = None

        while time.time() - start_time < timeout:
            if not self._ensure_target_window():
                time.sleep(0.20)
                continue

            positions = self.find_login_fields()
            if positions:
                break
            time.sleep(0.20)

        if not positions:
            print("Password retry: login fields not found after OK")
            return False

        if not self._ensure_target_window():
            return False

        (
            _,
            _,
            password_x,
            password_y,
            password_clear_x
        ) = positions

        try:
            pydirectinput.click(password_clear_x, password_y)
            time.sleep(0.20)

            self.clear_password_field()
            time.sleep(0.15)

            if not self._ensure_target_window():
                return False

            pydirectinput.click(password_x, password_y)
            time.sleep(0.15)
            self._type_exact(password, interval=0.04)
            time.sleep(0.20)
        except RuntimeError as error:
            print(f"Password retry safety: {error}")
            return False

        print(
            f"Password rewritten on target PID {self.target_pid} with exact letter case"
        )
        return True

    def stop(self):
        self.running = False

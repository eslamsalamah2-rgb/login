import os
import time
import json
import cv2
import numpy as np
import pydirectinput

from PIL import ImageGrab
from tasks.base_task import BaseTask


class LoginTask(BaseTask):

    def __init__(self):
        super().__init__()

        self.template_path = os.path.join(
            "assets",
            "login_fields.png"
        )

        self.credentials_path = "credentials.json"
        self.threshold = 0.80

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

        # Far-right click point for clearing username from the end.
        username_x = left + int(template_w * 0.82)
        username_y = top + int(template_h * 0.25)

        # Normal password typing point.
        password_x = left + int(template_w * 0.43)
        password_y = top + int(template_h * 0.76)

        # Far-right password point used only when retrying a password.
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

    def start(self, username=None, password=None):

        self.running = True

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

            positions = self.find_login_fields()

            if positions:
                (
                    username_x,
                    username_y,
                    password_x,
                    password_y,
                    _
                ) = positions

                pydirectinput.click(username_x, username_y)
                time.sleep(0.20)

                self.clear_username_field()
                time.sleep(0.10)

                pydirectinput.write(username, interval=0.04)
                time.sleep(0.20)

                pydirectinput.click(password_x, password_y)
                time.sleep(0.15)
                pydirectinput.write(password, interval=0.04)

                print(f"Login credentials entered for {username}")

                self.running = False
                return True

            time.sleep(0.5)

        return False

    def rewrite_password(self, password):
        if not password:
            return False

        positions = self.find_login_fields()

        if not positions:
            return False

        (
            _,
            _,
            password_x,
            password_y,
            password_clear_x
        ) = positions

        # Click at the far-right side of the password field and clear it.
        pydirectinput.click(password_clear_x, password_y)
        time.sleep(0.15)
        self.clear_password_field()
        time.sleep(0.10)

        # Type the password again from scratch.
        pydirectinput.click(password_x, password_y)
        time.sleep(0.10)
        pydirectinput.write(password, interval=0.04)
        time.sleep(0.15)

        return True

    def stop(self):
        self.running = False

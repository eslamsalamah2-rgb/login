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

        username_x = left + int(template_w * 0.43)
        username_y = top + int(template_h * 0.25)

        password_x = left + int(template_w * 0.43)
        password_y = top + int(template_h * 0.76)

        return (
            username_x,
            username_y,
            password_x,
            password_y
        )

    def select_all(self):
        pydirectinput.keyDown("ctrl")
        time.sleep(0.03)
        pydirectinput.press("a")
        time.sleep(0.03)
        pydirectinput.keyUp("ctrl")

    def start(self):

        self.running = True

        username, password = self.load_credentials()

        if not username or not password:
            print("credentials.json missing or incomplete")
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
                    password_y
                ) = positions

                pydirectinput.click(
                    username_x,
                    username_y
                )

                time.sleep(0.15)

                self.select_all()

                pydirectinput.write(
                    username,
                    interval=0.04
                )

                time.sleep(0.15)

                pydirectinput.click(
                    password_x,
                    password_y
                )

                time.sleep(0.15)

                self.select_all()

                pydirectinput.write(
                    password,
                    interval=0.04
                )

                print("Login credentials entered")

                self.running = False
                return True

            time.sleep(0.5)

        return False

    def stop(self):
        self.running = False

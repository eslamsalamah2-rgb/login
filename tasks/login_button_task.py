import os
import time
import cv2
import numpy as np
import pydirectinput

from PIL import ImageGrab
from tasks.base_task import BaseTask


class LoginButtonTask(BaseTask):

    def __init__(self):
        super().__init__()

        self.template_path = os.path.join(
            "assets",
            "login_button.png"
        )
        self.threshold = 0.82

    def find_button(self):

        if not os.path.exists(self.template_path):
            print("Login button image not found")
            return None

        template = cv2.imread(self.template_path, cv2.IMREAD_COLOR)

        if template is None:
            return None

        template_h, template_w = template.shape[:2]

        screenshot = ImageGrab.grab()
        screen = np.array(screenshot)
        screen = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

        result = cv2.matchTemplate(
            screen,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        _, max_value, _, max_location = cv2.minMaxLoc(result)
        print(f"Login button Match: {max_value:.3f}")

        if max_value < self.threshold:
            return None

        x = max_location[0] + template_w // 2
        y = max_location[1] + template_h // 2

        return x, y

    def start(self):

        self.running = True
        start_time = time.time()

        while self.running:

            if time.time() - start_time > 30:
                print("Login button not found")
                self.running = False
                return False

            position = self.find_button()

            if position:
                x, y = position

                pydirectinput.moveTo(x, y, duration=0.10)
                time.sleep(0.10)
                pydirectinput.click()

                print("Login button clicked")

                self.running = False
                return True

            time.sleep(0.4)

        return False

    def stop(self):
        self.running = False

import os
import time
import cv2
import numpy as np
import pydirectinput

from PIL import ImageGrab
from tasks.base_task import BaseTask


class PostLoginMessageTask(BaseTask):

    DISCONNECTED = "DISCONNECTED"
    WRONG_PASSWORD = "WRONG_PASSWORD"

    def __init__(self):
        super().__init__()

        self.templates = {
            self.DISCONNECTED: os.path.join(
                "assets",
                "disconnected.png"
            ),
            self.WRONG_PASSWORD: os.path.join(
                "assets",
                "wrong_password.png"
            )
        }

        self.threshold = 0.82

    def _match_template(self, screen, template_path):
        if not os.path.exists(template_path):
            return 0.0

        template = cv2.imread(
            template_path,
            cv2.IMREAD_COLOR
        )

        if template is None:
            return 0.0

        result = cv2.matchTemplate(
            screen,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        _, max_value, _, _ = cv2.minMaxLoc(result)
        return max_value

    def detect(self):
        screenshot = ImageGrab.grab()
        screen = np.array(screenshot)
        screen = cv2.cvtColor(
            screen,
            cv2.COLOR_RGB2BGR
        )

        best_type = None
        best_value = 0.0

        for message_type, template_path in self.templates.items():
            value = self._match_template(
                screen,
                template_path
            )

            print(
                f"Post login {message_type} Match: {value:.3f}"
            )

            if value > best_value:
                best_value = value
                best_type = message_type

        if best_value < self.threshold:
            return None

        return best_type

    def wait_for_message(self, timeout=6.0):
        self.running = True
        start_time = time.time()

        while self.running:
            message_type = self.detect()

            if message_type:
                self.running = False
                return message_type

            if time.time() - start_time >= timeout:
                self.running = False
                return None

            time.sleep(0.25)

        return None

    def press_ok(self):
        # These dialogs use OK as the default action.
        # Enter avoids depending on a fixed screen coordinate.
        pydirectinput.press("enter")
        time.sleep(0.5)

    def stop(self):
        self.running = False

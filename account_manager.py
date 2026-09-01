import json
import os


class AccountManager:

    def __init__(self, path="accounts.json"):
        self.path = path

    def load_accounts(self):
        if not os.path.exists(self.path):
            return []

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, list):
                return []

            accounts = []

            for item in data:
                if not isinstance(item, dict):
                    continue

                username = str(item.get("username", "")).strip()
                password = str(item.get("password", ""))

                if username and password:
                    accounts.append({
                        "username": username,
                        "password": password
                    })

            return accounts

        except Exception:
            return []

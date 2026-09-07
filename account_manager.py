import json
import os


class AccountManager:

    def __init__(self, path="accounts.json"):
        self.path = path

    @staticmethod
    def _clean_pluszero_settings(value):
        value = value if isinstance(value, dict) else {}

        def clean_string_list(key):
            raw = value.get(key, [])
            if not isinstance(raw, list):
                return []
            return [str(item) for item in raw if str(item).strip()]

        return {
            "bot_enabled": bool(value.get("bot_enabled", False)),
            "sash_enabled": bool(value.get("sash_enabled", False)),
            "revive_here_enabled": bool(value.get("revive_here_enabled", False)),
            "drop_items": clean_string_list("drop_items"),
            "use_items": clean_string_list("use_items"),
        }

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
                character_name = str(
                    item.get("character_name", item.get("name", ""))
                ).strip()

                if username and password:
                    accounts.append({
                        "username": username,
                        "password": password,
                        "character_name": character_name,
                        "selected": bool(item.get("selected", True)),
                        "pluszero": self._clean_pluszero_settings(
                            item.get("pluszero", {})
                        ),
                    })

            return accounts

        except Exception as error:
            print(f"Failed to load accounts: {error}")
            return []

    def save_accounts(self, accounts):
        try:
            clean_accounts = []

            for item in accounts:
                if not isinstance(item, dict):
                    continue

                username = str(item.get("username", "")).strip()
                password = str(item.get("password", ""))
                character_name = str(
                    item.get("character_name", "")
                ).strip()

                if not username or not password:
                    continue

                clean_accounts.append({
                    "username": username,
                    "password": password,
                    "character_name": character_name,
                    "selected": bool(item.get("selected", True)),
                    "pluszero": self._clean_pluszero_settings(
                        item.get("pluszero", {})
                    ),
                })

            with open(self.path, "w", encoding="utf-8") as file:
                json.dump(
                    clean_accounts,
                    file,
                    ensure_ascii=False,
                    indent=4
                )

            return True

        except Exception as error:
            print(f"Failed to save accounts: {error}")
            return False

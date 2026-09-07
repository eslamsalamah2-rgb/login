import customtkinter as ctk

from selection_launcher import SelectionAwareLauncher


class PlusZeroControlsLauncher(SelectionAwareLauncher):
    """Adds per-account PlusZero controls directly to known login rows.

    No Conquer scan is used here. Each control belongs to the same account row
    that owns the login session PID/HWND, and its settings are persisted in the
    account record so restarting the manager restores the previous choices.
    """

    def __init__(self):
        super().__init__()
        self.app.geometry("1350x720")
        self.app.minsize(1180, 620)

    def create_account_row(self, account=None):
        account = account or {}
        pluszero = account.get("pluszero", {})
        if not isinstance(pluszero, dict):
            pluszero = {}

        super().create_account_row(account)

        row = self.account_rows[-1]
        row_index = len(self.account_rows) - 1

        # Move delete button farther right to make room for PlusZero controls.
        row["delete"].grid_configure(column=8)

        sash_enabled = bool(pluszero.get("sash_enabled", False))
        sash_var = ctk.BooleanVar(value=sash_enabled)
        sash_button = ctk.CTkButton(
            row["frame"],
            text="Sash ON" if sash_enabled else "Sash OFF",
            width=90,
            height=32,
            fg_color="#1565c0" if sash_enabled else "#555555",
            command=lambda idx=row_index: self.toggle_sash(idx),
        )
        sash_button.grid(row=0, column=6, padx=4, pady=7)

        revive_here_enabled = bool(pluszero.get("revive_here_enabled", False))
        revive_here_var = ctk.BooleanVar(value=revive_here_enabled)
        revive_here_button = ctk.CTkButton(
            row["frame"],
            text="Revive Here ON" if revive_here_enabled else "Revive Here OFF",
            width=125,
            height=32,
            fg_color="#e65100" if revive_here_enabled else "#555555",
            command=lambda idx=row_index: self.toggle_revive_here(idx),
        )
        revive_here_button.grid(row=0, column=7, padx=4, pady=7)

        row["sash_var"] = sash_var
        row["sash_button"] = sash_button
        row["revive_here_var"] = revive_here_var
        row["revive_here_button"] = revive_here_button

    def collect_accounts_from_ui(self, include_empty=False):
        accounts = super().collect_accounts_from_ui(include_empty=include_empty)

        source_rows = self.account_rows if include_empty else [
            row for row in self.account_rows
            if row["username"].get().strip() and row["password"].get()
        ]

        for account, row in zip(accounts, source_rows):
            existing = {}
            try:
                row_index = self.account_rows.index(row)
                if 0 <= row_index < len(self.accounts_data):
                    saved = self.accounts_data[row_index].get("pluszero", {})
                    if isinstance(saved, dict):
                        existing = dict(saved)
            except Exception:
                existing = {}

            sash_var = row.get("sash_var")
            revive_var = row.get("revive_here_var")

            existing["sash_enabled"] = (
                bool(sash_var.get()) if sash_var is not None else False
            )
            existing["revive_here_enabled"] = (
                bool(revive_var.get()) if revive_var is not None else False
            )

            account["pluszero"] = existing

        return accounts

    def _save_control_change(self):
        # Persist immediately. A user should not have to press Save after every
        # per-account automation option change.
        self.save_accounts_from_ui()

    def toggle_sash(self, index):
        if not (0 <= index < len(self.account_rows)):
            return

        row = self.account_rows[index]
        var = row.get("sash_var")
        button = row.get("sash_button")
        if var is None or button is None:
            return

        enabled = not bool(var.get())
        var.set(enabled)
        button.configure(
            text="Sash ON" if enabled else "Sash OFF",
            fg_color="#1565c0" if enabled else "#555555",
        )

        self._save_control_change()
        self.set_status(
            f"الحساب {index + 1}: Sash {'ON' if enabled else 'OFF'} - تم الحفظ"
        )

    def toggle_revive_here(self, index):
        if not (0 <= index < len(self.account_rows)):
            return

        row = self.account_rows[index]
        var = row.get("revive_here_var")
        button = row.get("revive_here_button")
        if var is None or button is None:
            return

        enabled = not bool(var.get())
        var.set(enabled)
        button.configure(
            text="Revive Here ON" if enabled else "Revive Here OFF",
            fg_color="#e65100" if enabled else "#555555",
        )

        self._save_control_change()
        self.set_status(
            f"الحساب {index + 1}: Revive Here {'ON' if enabled else 'OFF'} - تم الحفظ"
        )

    def pluszero_settings_for_row(self, index):
        """Return the chosen PlusZero settings for one existing login row."""
        if not (0 <= index < len(self.account_rows)):
            return None

        row = self.account_rows[index]
        return {
            "sash_enabled": bool(row.get("sash_var").get())
            if row.get("sash_var") is not None else False,
            "revive_here_enabled": bool(row.get("revive_here_var").get())
            if row.get("revive_here_var") is not None else False,
        }

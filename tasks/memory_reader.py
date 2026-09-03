import time
import psutil
import pymem
import pymem.process


class ConquerMemoryReader:

    PROCESS_NAME = "conquer.exe"
    NAME_OFFSET = 0x8E6184

    @classmethod
    def list_conquer_pids(cls):
        pids = set()

        for process in psutil.process_iter(["pid", "name"]):
            try:
                name = process.info.get("name") or ""

                if name.lower() == cls.PROCESS_NAME:
                    pids.add(process.info["pid"])

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return pids

    @classmethod
    def wait_for_new_conquer_pid(cls, previous_pids, timeout=20.0):
        start_time = time.time()

        while time.time() - start_time < timeout:
            current_pids = cls.list_conquer_pids()
            new_pids = current_pids - set(previous_pids)

            if new_pids:
                # Normally one new Conquer process is created per page.
                return max(new_pids)

            time.sleep(0.25)

        return None

    def __init__(self, pid):
        self.pid = int(pid)
        self.pm = pymem.Pymem()
        self.pm.open_process_from_id(self.pid)

    def close(self):
        try:
            self.pm.close_process()
        except Exception:
            pass

    def read_name(self, max_length=64):
        try:
            module = pymem.process.module_from_name(
                self.pm.process_handle,
                self.PROCESS_NAME
            )

            if module is None:
                return None

            address = module.lpBaseOfDll + self.NAME_OFFSET
            value = self.pm.read_string(address, max_length)

            if value is None:
                return None

            return value.strip("\x00").strip()

        except Exception as error:
            print(
                f"Memory read error for PID {self.pid}: {error}"
            )
            return None

    def wait_for_name_change(
        self,
        previous_value=None,
        timeout=None,
        require_change=True,
        check_interval=10.0
    ):
        """Keep checking the character-name address until a valid name appears.

        The login/server can take a long time, so this intentionally does not
        fail after a short timeout. It checks conquer.exe+8E6184 once every
        ``check_interval`` seconds (10 seconds by default) until the value is
        non-empty and, when requested, different from the initial value.

        ``timeout`` is kept only for compatibility with older gui.py calls and
        is intentionally ignored.
        """
        previous_value = (previous_value or "").strip()
        check_number = 0

        while True:
            check_number += 1
            value = self.read_name()

            print(
                f"Memory name check #{check_number} - PID {self.pid} - "
                f"Value: {value!r}"
            )

            if value:
                if not require_change:
                    return value

                if value != previous_value:
                    return value

            print(
                f"Name not ready yet. Checking again in "
                f"{check_interval:g} seconds..."
            )
            time.sleep(check_interval)

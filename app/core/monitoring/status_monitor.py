class StatusMonitor:
    """The traffic light system to monitor LLM generation status."""
    STATUS_COLORS = {
        "RED": "\033[91m🔴\033[0m",
        "YELLOW": "\033[93m🟡\033[0m",
        "GREEN": "\033[92m🟢\033[0m",
        "OFF": "⚪️"
    }

    def __init__(self):
        self.status = "OFF"  # Initial status

    def set_status(self, new_status: str):
        """Sets the new status (RED, YELLOW, GREEN)."""
        if new_status.upper() in self.STATUS_COLORS:
            self.status = new_status.upper()
        else:
            print(f"Warning: Invalid status '{new_status}' ignored.")

    def get_status(self) -> str:
        return self.status

    def get_status_colored(self) -> str:
        """Returns the status with a colored icon for terminal output."""
        return f"{self.STATUS_COLORS.get(self.status, '⚪️')} ({self.status})"
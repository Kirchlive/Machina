import datetime

class BasicLogger:
    """A simple logger for Phase 1."""
    def log(self, level: str, message: str):
        timestamp = datetime.datetime.now().isoformat()
        print(f"[{timestamp}] [{level.upper()}] {message}")
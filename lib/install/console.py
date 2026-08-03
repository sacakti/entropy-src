class InstallerConsole:

    @staticmethod
    def step(message: str) -> None:

        print(f"▶ {message}")

    @staticmethod
    def success(message: str) -> None:

        print(f"✔ {message}")

    @staticmethod
    def warning(message: str) -> None:

        print(f"⚠ {message}")

    @staticmethod
    def error(message: str) -> None:

        print(f"✖ {message}")

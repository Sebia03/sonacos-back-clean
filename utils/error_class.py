class CheckError(Exception):
    def __init__(self, message: str, error_code: int) -> None:
        super().__init__(message)
        self.error_code = error_code
class MigrationError(Exception):
    def __init__(self, filename: str, cause: Exception):
        self.filename = filename
        self.cause = cause
        super().__init__(f"Migration {filename} failed: {cause}")

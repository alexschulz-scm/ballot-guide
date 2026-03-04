class SessionNotFoundError(Exception):
    """Raised when a session ID does not exist in the database."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class InvalidTransitionError(Exception):
    """Raised when a session state transition violates the state machine."""

    def __init__(self, current_status: str, requested_status: str):
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(
            f"Invalid transition: {current_status} -> {requested_status}"
        )

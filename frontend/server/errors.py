"""User-facing error codes and the exact messages shown in the app."""

MESSAGES = {
    "wrong_file_type": "Oops! Please upload a PNG, JPEG, or HEIC photo.",
    "file_too_big": "That photo is too large. Please try a smaller one (under 10 MB).",
    "no_handwriting": (
        "We couldn’t find any handwriting. Make sure your writing is in black pen "
        "on white paper and fills the photo."
    ),
    "analysis_failed": "Miggle got a little confused by this one. Please try another photo.",
    "analysis_offline": "Miggle can’t reach the scoring server right now. Please try again in a moment.",
    "not_signed_in": "Please sign in first.",
    "bad_credentials": "That username and password don’t match. Please try again.",
    "username_taken": "That username is taken. Please try another one.",
    "invalid_input": "Please check the form and try again.",
    "not_found": "We couldn’t find that.",
}

STATUS = {
    "wrong_file_type": 415,
    "file_too_big": 413,
    "no_handwriting": 422,
    "analysis_failed": 500,
    "analysis_offline": 503,
    "not_signed_in": 401,
    "bad_credentials": 401,
    "username_taken": 409,
    "invalid_input": 400,
    "not_found": 404,
}


class InkoError(Exception):
    """Raise anywhere in the backend; main.py turns it into a JSON error response."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or MESSAGES.get(code, MESSAGES["analysis_failed"])
        self.status = STATUS.get(code, 400)
        super().__init__(self.message)

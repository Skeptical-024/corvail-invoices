from typing import Optional
class CorvailInvoicesError(Exception):
    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class IngestionError(CorvailInvoicesError):
    status_code = 400
    error_code = "ingestion_error"


class ExtractionError(CorvailInvoicesError):
    status_code = 502
    error_code = "extraction_error"


class ValidationError(CorvailInvoicesError):
    status_code = 422
    error_code = "validation_error"


class EgressError(CorvailInvoicesError):
    status_code = 502
    error_code = "egress_error"


class AuthenticationError(CorvailInvoicesError):
    status_code = 401
    error_code = "authentication_error"

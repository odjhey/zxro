class ZxroError(Exception):
    exit_code = 4


class ValidationError(ZxroError):
    exit_code = 2


class NotFoundError(ZxroError):
    exit_code = 3


class ConflictError(ZxroError):
    exit_code = 4


class UnsafeStateError(ZxroError):
    exit_code = 5

class APIError(RuntimeError):
    """Raised for bad HTTP codes, missing data, unexpected format, etc"""


class ImproperlyConfigured(RuntimeError):
    """Raised for incorrect YAML values"""


class TickerDataError(RuntimeError):
    """Raise for ticker data that is missing, incomplete, corrupt, etc"""

class RateLimitExceededError(RuntimeError):
    """Raised when a request would exceed configured or provider-reported limits."""

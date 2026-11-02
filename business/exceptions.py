class SlotUnavailableError(Exception):
    """The service already has an active appointment starting at the requested time."""


class StartTimeInPastError(Exception):
    """The requested start time is not in the future."""


class StartTimeTooFarError(Exception):
    """The requested start time is beyond the booking horizon."""


class BusinessNotOwnedError(Exception):
    """The caller does not own the requested business."""

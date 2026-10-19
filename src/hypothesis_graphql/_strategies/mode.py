import enum


class Mode(enum.Enum):
    """Kind of operations a strategy generates.

    POSITIVE: Operations that pass schema validation.
    NEGATIVE: Operations with one schema violation, such as a wrong argument type, a missing required
              argument, or an unknown enum value. Use them to test how your server rejects bad input.
    """

    POSITIVE = enum.auto()
    NEGATIVE = enum.auto()

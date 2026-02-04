import enum


class Mode(enum.Enum):
    """Generation mode for GraphQL queries.

    POSITIVE: Generate valid queries that pass schema validation.
    NEGATIVE: Generate invalid queries with intentional violations
              (wrong types, missing required args, invalid enums, etc.)
              for testing error handling.
    """

    POSITIVE = enum.auto()
    NEGATIVE = enum.auto()

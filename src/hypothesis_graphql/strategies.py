from ._strategies.mode import Mode
from ._strategies.strategy import from_schema, mutations, queries

# Backward compatibility
query = queries

__all__ = ["Mode", "from_schema", "mutations", "query", "queries"]

# pylint: disable=unused-import
from ._strategies.mutations import mutations
from ._strategies.queries import queries
from ._strategies.schema import schemas

# Backward compatibility
query = queries
schema = schemas

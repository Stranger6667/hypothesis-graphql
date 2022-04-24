from functools import lru_cache

import graphql


@lru_cache(maxsize=32)
def cached_build_schema(schema: str) -> graphql.GraphQLSchema:
    return graphql.build_schema(schema)

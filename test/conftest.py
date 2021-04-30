from functools import lru_cache

import graphql
import pytest
from hypothesis import HealthCheck, settings

settings.register_profile("default", suppress_health_check=[HealthCheck.too_slow], deadline=None)
settings.load_profile("default")


@pytest.fixture(scope="session")
def build_schema():
    # Parses a GraphQL schema. Caching is required to avoid re-parsing in each Hypothesis test as schemas are mostly
    # static

    @lru_cache()
    def inner(schema: str):
        return graphql.build_schema(schema)

    return inner


@pytest.fixture(scope="session")
def validate_query(build_schema):
    def inner(schema, query):
        if isinstance(schema, str):
            parsed_schema = build_schema(schema)
        else:
            parsed_schema = schema
        query_ast = graphql.parse(query)
        errors = graphql.validate(parsed_schema, query_ast)
        assert not errors
        return query_ast

    return inner

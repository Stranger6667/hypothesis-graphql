from functools import lru_cache

import graphql
import pytest
from hypothesis import HealthCheck, settings

settings.register_profile("default", suppress_health_check=[HealthCheck.too_slow], deadline=None)
settings.load_profile("default")


SCHEMA = """
type Book {
  title: String
  author: Author
}

type Author {
  name: String
  books: [Book]
}

enum Color {
  RED
  GREEN
  BLUE
}

input EnumInput {
  color: Color
}

input QueryInput {
  eq: String
  ne: String
}

input RequiredInput {
  eq: Float!,
}

input NestedQueryInput {
  code: QueryInput
}

type Image {
  path: String
}
type Video {
  duration: Int
}

union Media = Image | Video

interface Node {
  id: ID
}

interface Alone {
  id: ID
}

type Model implements Node {
  int: Int,
  float: Float,
  media: Media,
  string: String
  id: ID,
  boolean: Boolean
  color: Color
}
"""


@pytest.fixture(scope="session")
def schema():
    return SCHEMA


@pytest.fixture(scope="session")
def build_schema():
    # Parses a GraphQL schema. Caching is required to avoid re-parsing in each Hypothesis test as schemas are mostly
    # static

    @lru_cache()
    def inner(schema: str):
        return graphql.build_schema(schema)

    return inner


@pytest.fixture(scope="session")
def validate_operation(build_schema):
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

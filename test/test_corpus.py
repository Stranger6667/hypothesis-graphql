import json
import pathlib
from dataclasses import dataclass
from typing import Optional

import graphql
import pytest
from hypothesis import HealthCheck, Phase, Verbosity, given, settings
from hypothesis import strategies as st

from hypothesis_graphql import from_schema, nodes
from hypothesis_graphql._strategies.strategy import BUILT_IN_SCALAR_TYPE_NAMES
from hypothesis_graphql.cache import cached_build_schema

HERE = pathlib.Path(__file__).parent

with open(HERE / "corpus-api-guru-catalog.json") as fd:
    schemas = json.load(fd)

INVALID_SCHEMAS = {
    # Error: The directive '@deprecated' can only be used once at this location
    "Gitlab",
}


@dataclass
class Schema:
    raw: dict
    custom_scalars: Optional[dict]


PLACEHOLDER_STRATEGY = st.just("placeholder").map(nodes.String)


@pytest.fixture
def schema(request):
    raw_schema = schemas[request.param]
    parsed = cached_build_schema(raw_schema)
    custom_scalars = {}
    # Put placeholders for every custom scalar. Their value is pretty much irrelevant here, it is more important to
    # test query generation, therefore a placeholder will allow these tests to run on schemas that contain custom
    # scalars
    for name, type_ in parsed.type_map.items():
        if name not in BUILT_IN_SCALAR_TYPE_NAMES and isinstance(type_, graphql.GraphQLScalarType):
            custom_scalars[name] = PLACEHOLDER_STRATEGY
    return Schema(raw_schema, custom_scalars or None)


def get_names(corpus, predicate=None):
    for name in sorted(corpus):
        if name in INVALID_SCHEMAS or (predicate and not predicate(name)):
            continue
        yield name


CORPUS_SETTINGS = {
    "suppress_health_check": [
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        HealthCheck.filter_too_much,
        HealthCheck.function_scoped_fixture,
    ],
    "phases": [Phase.generate],
    "verbosity": Verbosity.quiet,
    "deadline": None,
    "max_examples": 10,
}


@pytest.mark.parametrize("schema", get_names(schemas), indirect=["schema"])
@settings(**CORPUS_SETTINGS)
@given(data=st.data())
def test_corpus(data, schema: Schema, validate_operation):
    query = data.draw(from_schema(schema.raw, custom_scalars=schema.custom_scalars))
    validate_operation(schema.raw, query)

import json

import pytest
from hypothesis import HealthCheck, Phase, Verbosity, given, settings
from hypothesis import strategies as st

from hypothesis_graphql import strategies as gql_st

with open("test/corpus-api-guru-catalog.json") as fd:
    schemas = json.load(fd)

INVALID_SCHEMAS = {
    # Error: The directive '@deprecated' can only be used once at this location
    "Gitlab",
}
SCHEMAS_WITH_CUSTOM_SCALARS = {
    "MongoDB Northwind demo",
    "Bitquery",
    "MusicBrainz",
    "Spacex Land",
    "TravelgateX",
    "HIVDB",
    "Contentful",
    "Universe",
}


def get_names(corpus, predicate=None):
    for name in sorted(corpus):
        if name in INVALID_SCHEMAS or (predicate and not predicate(name)):
            continue
        if name in SCHEMAS_WITH_CUSTOM_SCALARS:
            yield pytest.param(name, marks=pytest.mark.xfail(reason="Custom scalars are not supported"))
        else:
            yield name


CORPUS_SETTINGS = {
    "suppress_health_check": [HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
    "phases": [Phase.generate],
    "verbosity": Verbosity.quiet,
    "deadline": None,
    "max_examples": 5,
}


@pytest.mark.parametrize("name", get_names(schemas))
@settings(**CORPUS_SETTINGS)
@given(data=st.data())
def test_corpus(data, name, validate_operation):
    schema = schemas[name]
    query = data.draw(gql_st.queries(schema))
    validate_operation(schema, query)


@pytest.mark.parametrize("name", get_names(schemas, lambda name: "type Mutation" in schemas[name]))
@settings(**CORPUS_SETTINGS)
@given(data=st.data())
def test_corpus_mutations(data, name, validate_operation):
    schema = schemas[name]
    mutation = data.draw(gql_st.mutations(schema))
    validate_operation(schema, mutation)

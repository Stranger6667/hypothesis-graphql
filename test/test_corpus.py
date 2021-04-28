import json

import pytest
from hypothesis import HealthCheck, given, settings
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
}


def get_names(corpus):
    for name in sorted(corpus):
        if name in INVALID_SCHEMAS:
            continue
        if name in SCHEMAS_WITH_CUSTOM_SCALARS:
            yield pytest.param(name, marks=pytest.mark.xfail(reason="Custom scalars are not supported"))
        else:
            yield name


@pytest.mark.parametrize("name", get_names(schemas))
@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
    deadline=None,
    max_examples=5,
)
@given(data=st.data())
def test_corpus(data, name):
    schema = schemas[name]
    data.draw(gql_st.query(schema))

import graphql
import pytest
from hypothesis import given, settings

import hypothesis_graphql._strategies.schema as gql_st


@pytest.mark.parametrize(
    "strategy, node_type",
    (
        (gql_st.scalar_typedef(), graphql.ScalarTypeDefinitionNode),
        (gql_st.object_typedef(), graphql.ObjectTypeDefinitionNode),
    ),
)
def test_generation(strategy, node_type):
    @given(item=strategy)
    @settings(max_examples=10)
    def test(item):
        parsed = graphql.parse(item)
        assert isinstance(parsed.definitions[0], node_type)

    test()

import graphql
import pytest
from hypothesis import given, settings

from hypothesis_graphql._strategies import schema as gst


@pytest.mark.parametrize(
    "strategy, node_type",
    (
        (gst.scalar_typedef(), graphql.ScalarTypeDefinitionNode),
        (gst.object_typedef(), graphql.ObjectTypeDefinitionNode),
    ),
)
def test_generation(strategy, node_type):
    @given(item=strategy)
    @settings(max_examples=10)
    def test(item):
        parsed = graphql.parse(item)
        assert isinstance(parsed.definitions[0], node_type)

    test()

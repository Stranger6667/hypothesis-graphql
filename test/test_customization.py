import re

import pytest
from hypothesis import find, given
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from hypothesis_graphql import nodes, queries

CUSTOM_SCALAR_TEMPLATE = """
scalar Date

type Object {{
  created: Date
}}

input QueryInput {{
  created: Date
  id: String!
}}

input RequiredQueryInput {{
  created: Date!
}}

type Query {{
  {query}
}}
"""


@given(data=st.data())
def test_custom_scalar_non_argument(data, validate_operation):
    # When a custom scalar type is defined
    # And is used in a non-argument position

    schema = CUSTOM_SCALAR_TEMPLATE.format(query="getObjects: [Object]")
    query = data.draw(queries(schema))
    validate_operation(schema, query)
    # Then queries should be generated
    assert "created" in query


def test_custom_scalar_argument_nullable(validate_operation):
    # When a custom scalar type is defined
    # And is used in an argument position
    # And is nullable
    # And there are no other arguments

    num_of_queries = 0

    schema = CUSTOM_SCALAR_TEMPLATE.format(query="getByDate(created: Date): Object")

    @given(query=queries(schema))
    def test(query):
        nonlocal num_of_queries

        num_of_queries += 1
        validate_operation(schema, query)
        assert "getByDate {" in query or "getByDate(created: null)" in query

    test()
    # Then only two queries should be generated - no fields, and `created: null`
    assert num_of_queries == 2


@pytest.mark.parametrize("input_type", ("Date", "RequiredQueryInput"))
@given(data=st.data())
def test_custom_scalar_argument(data, input_type):
    # When a custom scalar type is defined
    # And is used in an argument position
    # And is not nullable

    schema = CUSTOM_SCALAR_TEMPLATE.format(query=f"getByDate(created: {input_type}!): Object")

    with pytest.raises(TypeError, match="Scalar 'Date' is not supported"):
        data.draw(queries(schema))


@pytest.mark.parametrize("other_type", ("String!", "String"))
def test_custom_scalar_nested_argument(validate_operation, other_type):
    # When a custom scalar type is defined
    # And is used as a field inside an input type
    # And is nullable
    schema = f"""
scalar Date

input QueryInput {{
  created: Date
  id: {other_type}
}}

type Query {{
  getByDate(created: QueryInput!): Int
}}"""

    # Then it could be skipped
    strategy = queries(schema)

    @given(strategy)
    def test(query):
        validate_operation(schema, query)

    test()
    # And "id" is still possible to generate
    assert find(strategy, lambda x: "id" in x).strip() in (
        '{\n  getByDate(created: {id: ""})\n}',
        "{\n  getByDate(created: {id: null})\n}",
    )


@given(data=st.data())
def test_custom_scalar_field(data, validate_operation):
    # When a custom scalar type is defined
    # And is used in a field position
    # And is not nullable
    schema = """
    scalar Date

    type Object {
      created: Date!
    }
    type Query {
      getObject: Object
    }
    """
    # Then query should be generated without errors
    query = data.draw(queries(schema))
    validate_operation(schema, query)
    assert (
        query.strip()
        == """{
  getObject {
    created
  }
}"""
    )


@given(data=st.data())
def test_custom_scalar_registered(data, validate_operation):
    # When the user registered a custom strategy for a scalar
    # Then it should generate valid queries
    schema = CUSTOM_SCALAR_TEMPLATE.format(query="getByDate(created: Date!): Int")
    expected = "EXAMPLE"

    query = data.draw(queries(schema, custom_scalars={"Date": st.just(expected).map(nodes.String)}))
    validate_operation(schema, query)
    assert f'getByDate(created: "{expected}")' in query


@pytest.mark.parametrize(
    "custom_scalars, expected",
    (
        (
            {"Date": 42},
            re.escape(
                r"custom_scalars['Date']=42 must be a Hypothesis strategy which generates AST nodes matching this"
            ),
        ),
        ({42: 42}, "scalar name 42 must be a string"),
    ),
)
def test_invalid_custom_scalar_strategy(custom_scalars, expected):
    # When the user passes `custom_scalars`
    # And it has a wrong type
    # Then there should be an error
    schema = CUSTOM_SCALAR_TEMPLATE.format(query="getByDate(created: Date!): Int")
    with pytest.raises(InvalidArgument, match=expected):
        queries(schema, custom_scalars=custom_scalars)

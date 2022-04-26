import re

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from hypothesis_graphql import strategies as gql_st
from hypothesis_graphql._strategies import factories

CUSTOM_SCALAR_TEMPLATE = """
scalar Date

type Object {{
  created: Date
}}

input QueryInput {{
  created: Date
  id: String!
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
    query = data.draw(gql_st.queries(schema))
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

    @given(query=gql_st.queries(schema))
    def test(query):
        nonlocal num_of_queries

        num_of_queries += 1
        validate_operation(schema, query)
        assert "getByDate {" in query

    test()
    # Then only one query should be generated
    assert num_of_queries == 1


@given(data=st.data())
def test_custom_scalar_argument(data):
    # When a custom scalar type is defined
    # And is used in an argument position
    # And is not nullable

    schema = CUSTOM_SCALAR_TEMPLATE.format(query="getByDate(created: Date!): Object")

    with pytest.raises(TypeError, match="Scalar 'Date' is not supported"):
        data.draw(gql_st.queries(schema))


@given(data=st.data())
@pytest.mark.parametrize("other_type", ("String!", "String"))
def test_custom_scalar_nested_argument(data, validate_operation, other_type):
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
    query = data.draw(gql_st.queries(schema))
    validate_operation(schema, query)


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
    query = data.draw(gql_st.queries(schema))
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

    query = data.draw(gql_st.queries(schema, custom_scalars={"Date": st.just(expected).map(factories.string)}))
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
        gql_st.queries(schema, custom_scalars=custom_scalars)

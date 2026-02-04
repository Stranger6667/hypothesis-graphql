import graphql
import pytest
from hypothesis import given, settings, find, HealthCheck
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from hypothesis_graphql import queries, mutations, from_schema, Mode, nodes


def assert_query_invalid(query: str, schema: str) -> None:
    parsed_schema = graphql.build_schema(schema)
    doc = graphql.parse(query)
    assert doc is not None, f"Query failed to parse: {query}"
    errors = graphql.validate(parsed_schema, doc)
    assert len(errors) > 0, f"Query should be invalid but passed validation: {query}"


def generate_multiple_queries(schema: str, strategy, count: int = 20, **kwargs) -> list:
    queries_list = []
    failures = {}

    for _ in range(count):
        try:
            query = find(strategy, lambda q: True, settings=settings(database=None, max_examples=20, **kwargs))
            queries_list.append(query)
        except Exception as e:
            exc_type = type(e).__name__
            failures[exc_type] = failures.get(exc_type, 0) + 1
            continue

    if len(queries_list) == 0:
        failure_summary = ", ".join(f"{exc}: {count}" for exc, count in failures.items())
        raise AssertionError(f"Failed to generate any queries after {count} attempts. Failures: {failure_summary}")

    return queries_list


@given(data=st.data())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_all_negative_queries_are_invalid(data):
    schema = """
    type Query {
        test(value: Int!): String
        getUser(id: ID!): String
    }
    """
    parsed_schema = graphql.build_schema(schema)

    for _ in range(20):
        query = data.draw(queries(schema, mode=Mode.NEGATIVE))
        doc = graphql.parse(query)
        errors = graphql.validate(parsed_schema, doc)
        assert len(errors) > 0, f"Query should be invalid but passed validation: {query}"


def test_negative_with_mutations():
    schema = """
    input CreateUserInput {
        name: String!
        email: String!
        age: Int
    }

    type Mutation {
        createUser(input: CreateUserInput!): User
    }

    type User {
        id: ID!
        name: String!
    }

    type Query {
        dummy: String
    }
    """
    mutation = find(
        mutations(schema, mode=Mode.NEGATIVE), lambda q: "createUser" in q, settings=settings(max_examples=100)
    )
    graphql.parse(mutation)


def test_negative_with_from_schema():
    schema = """
    type Query {
        getUser(id: Int!): String
    }

    type Mutation {
        updateUser(id: Int!, name: String!): String
    }
    """
    result = find(from_schema(schema, mode=Mode.NEGATIVE), lambda q: True, settings=settings(max_examples=100))
    graphql.parse(result)


def test_backward_compatibility():
    schema = """
    type Query { test: String }
    """

    @given(queries(schema))
    @settings(max_examples=10)
    def test(query):
        parsed_schema = graphql.build_schema(schema)
        doc = graphql.parse(query)
        errors = graphql.validate(parsed_schema, doc)
        assert not errors

    test()


def test_positive_mode_generates_valid():
    schema = """
    type Query {
        test(value: Int!): String
    }
    """

    @given(queries(schema, mode=Mode.POSITIVE))
    @settings(max_examples=20)
    def test(query):
        parsed_schema = graphql.build_schema(schema)
        doc = graphql.parse(query)
        errors = graphql.validate(parsed_schema, doc)
        assert not errors

    test()


@given(
    from_schema(
        """
    enum Status { ACTIVE INACTIVE }

    input UserInput {
        name: String!
        age: Int
    }

    type User {
        id: ID!
        name: String!
    }

    type Query {
        getUser(id: ID!): User
        searchUsers(input: UserInput!): [User]
    }

    type Mutation {
        createUser(input: UserInput!): User
    }
    """,
        mode=Mode.NEGATIVE,
    )
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_complex_schema_negative(query):
    schema = """
    enum Status { ACTIVE INACTIVE }

    input UserInput {
        name: String!
        age: Int
    }

    type User {
        id: ID!
        name: String!
    }

    type Query {
        getUser(id: ID!): User
        searchUsers(input: UserInput!): [User]
    }

    type Mutation {
        createUser(input: UserInput!): User
    }
    """

    doc = graphql.parse(query)

    parsed_schema = graphql.build_schema(schema)
    errors = graphql.validate(parsed_schema, doc)
    assert len(errors) > 0, f"Query should be invalid but passed validation: {query}"


def test_missing_required_fields_in_input():
    schema = """
    input RequiredInput {
        required1: String!
        required2: Int!
        optional: String
    }

    type Query {
        test(input: RequiredInput!): String
    }
    """

    query_list = generate_multiple_queries(schema, queries(schema, mode=Mode.NEGATIVE), count=15)

    # Verify queries are invalid (violations may be type errors, missing fields, or null in required positions)
    for query in query_list:
        assert_query_invalid(query, schema)

    assert len(query_list) >= 10, f"Only generated {len(query_list)} queries, expected at least 10"


def test_wrong_type_violations():
    schema = """
    type Query {
        testInt(value: Int!): String
        testString(value: String!): Int
        testFloat(value: Float!): String
        testBoolean(value: Boolean!): String
    }
    """

    query_list = generate_multiple_queries(schema, queries(schema, mode=Mode.NEGATIVE), count=15)

    for query in query_list:
        assert_query_invalid(query, schema)

    assert len(query_list) >= 10, f"Only generated {len(query_list)} queries, expected at least 10"


def test_null_violations():
    schema = """
    type Query {
        testRequired(value: String!): String
        testOptional(value: String): String
    }
    """

    query_list = generate_multiple_queries(
        schema, queries(schema, mode=Mode.NEGATIVE).filter(lambda q: "testRequired" in q), count=15
    )

    for query in query_list:
        assert_query_invalid(query, schema)

    assert len(query_list) >= 10, f"Only generated {len(query_list)} queries, expected at least 10"


def test_enum_violations():
    schema = """
    enum Color { RED GREEN BLUE }

    type Query {
        testEnum(color: Color!): String
    }
    """

    query_list = generate_multiple_queries(
        schema, queries(schema, mode=Mode.NEGATIVE).filter(lambda q: "testEnum" in q), count=15
    )

    for query in query_list:
        assert_query_invalid(query, schema)

    assert len(query_list) >= 10, f"Only generated {len(query_list)} queries, expected at least 10"


def test_out_of_range_int():
    schema = """
    type Query {
        testInt(value: Int!): String
    }
    """

    query_list = generate_multiple_queries(
        schema, queries(schema, mode=Mode.NEGATIVE).filter(lambda q: "testInt" in q), count=15
    )

    # All queries with Int! argument should be invalid (violations may be wrong type,
    # out-of-range, null, or missing argument)
    for query in query_list:
        assert_query_invalid(query, schema)


def test_float_violations():
    schema = """
    type Query {
        testFloat(value: Float!): String
    }
    """

    query_list = generate_multiple_queries(
        schema, queries(schema, mode=Mode.NEGATIVE).filter(lambda q: "testFloat" in q), count=15
    )

    for query in query_list:
        assert_query_invalid(query, schema)

    assert len(query_list) >= 10, f"Only generated {len(query_list)} queries, expected at least 10"


def test_missing_required_arguments():
    schema = """
    type Query {
        testRequired(arg1: String!, arg2: Int!): String
        testOptional(arg: String): String
    }
    """

    query_list = generate_multiple_queries(
        schema, queries(schema, mode=Mode.NEGATIVE).filter(lambda q: "testRequired" in q), count=15
    )

    for query in query_list:
        assert_query_invalid(query, schema)

    assert len(query_list) >= 10, f"Only generated {len(query_list)} queries, expected at least 10"


def test_negative_preserves_custom_scalars():
    schema = """
    scalar DateTime

    type Query {
        test(time: DateTime!): String
    }
    """

    custom_scalars = {
        "DateTime": st.datetimes().map(lambda dt: nodes.String(dt.isoformat())),
    }

    query = find(
        queries(schema, custom_scalars=custom_scalars, mode=Mode.NEGATIVE),
        lambda q: True,
        settings=settings(max_examples=100),
    )

    graphql.parse(query)


def test_negative_mode_coverage():
    schema = """
    enum Status { ACTIVE INACTIVE }

    input TestInput {
        required: String!
        optional: Int
    }

    type Query {
        testInt(value: Int!): String
        testString(value: String!): String
        testEnum(status: Status!): String
        testInput(input: TestInput!): String
    }
    """

    query_list = generate_multiple_queries(schema, queries(schema, mode=Mode.NEGATIVE), count=15)

    for query in query_list:
        assert_query_invalid(query, schema)

    assert len(query_list) >= 10, f"Only generated {len(query_list)} queries, expected at least 10"


@given(
    queries(
        """
    type Query {
        test(arg1: Int!, arg2: String!, arg3: Boolean!): String
    }
    """,
        mode=Mode.NEGATIVE,
    )
)
@settings(max_examples=30)
def test_multiple_violations_possible(query):
    schema = """
    type Query {
        test(arg1: Int!, arg2: String!, arg3: Boolean!): String
    }
    """

    # Query must be invalid (at least one violation)
    parsed_schema = graphql.build_schema(schema)
    doc = graphql.parse(query)
    errors = graphql.validate(parsed_schema, doc)
    assert len(errors) > 0


@given(data=st.data())
@settings(max_examples=20)
def test_tracker_state_isolated_between_queries(data):
    schema = """
    type Query {
        test(value: Int!): String
    }
    """

    parsed_schema = graphql.build_schema(schema)

    for i in range(5):
        query = data.draw(queries(schema, mode=Mode.NEGATIVE))
        doc = graphql.parse(query)
        errors = graphql.validate(parsed_schema, doc)

        assert len(errors) > 0, f"Query {i + 1} should be invalid but was valid: {query}"


def test_all_violation_types_can_generate():
    schema_int = """type Query { test(value: Int!): String }"""
    schema_enum = """
        enum Color { RED GREEN BLUE }
        type Query { test(color: Color!): String }
    """
    schema_missing = """type Query { test(arg1: String!, arg2: Int!): String }"""

    int_queries = generate_multiple_queries(
        schema_int, queries(schema_int, mode=Mode.NEGATIVE).filter(lambda q: "test" in q), count=15
    )
    assert len(int_queries) >= 10, f"Only generated {len(int_queries)} int queries"

    for query in int_queries:
        assert_query_invalid(query, schema_int)

    enum_queries = generate_multiple_queries(
        schema_enum, queries(schema_enum, mode=Mode.NEGATIVE).filter(lambda q: "test" in q), count=15
    )
    assert len(enum_queries) >= 10, f"Only generated {len(enum_queries)} enum queries"

    for query in enum_queries:
        assert_query_invalid(query, schema_enum)

    missing_queries = generate_multiple_queries(
        schema_missing, queries(schema_missing, mode=Mode.NEGATIVE).filter(lambda q: "test" in q), count=15
    )
    assert len(missing_queries) >= 10, f"Only generated {len(missing_queries)} missing arg queries"

    for query in missing_queries:
        assert_query_invalid(query, schema_missing)

    queries_with_missing = [q for q in missing_queries if "arg1" not in q or "arg2" not in q]
    assert len(queries_with_missing) > 0, "Should generate some queries with missing arguments"


@given(
    queries(
        """
    type Query {
        test(optional1: String, optional2: Int): String
    }
    """,
        mode=Mode.NEGATIVE,
    )
)
@settings(max_examples=20)
def test_optional_only_schema(query):
    schema = """
    type Query {
        test(optional1: String, optional2: Int): String
    }
    """
    parsed_schema = graphql.build_schema(schema)
    doc = graphql.parse(query)
    errors = graphql.validate(parsed_schema, doc)
    assert len(errors) > 0, f"Query should be invalid: {query}"


def test_nested_input_violations():
    schema = """
    input Level3 {
        value: Int!
    }

    input Level2 {
        nested: Level3!
    }

    input Level1 {
        nested: Level2!
    }

    type Query {
        test(input: Level1!): String
    }
    """

    query = find(queries(schema, mode=Mode.NEGATIVE), lambda q: "test" in q, settings=settings(max_examples=100))

    parsed_schema = graphql.build_schema(schema)
    doc = graphql.parse(query)
    errors = graphql.validate(parsed_schema, doc)

    assert len(errors) > 0, f"Nested input query should be invalid: {query}"


@given(
    queries(
        """
    type Query {
        field1(arg: Int!): String
        field2(arg: String!): Int
        field3(arg: Boolean!): Float
    }
    """,
        mode=Mode.NEGATIVE,
    )
)
@settings(max_examples=30)
def test_different_fields_can_be_selected(query):
    schema = """
    type Query {
        field1(arg: Int!): String
        field2(arg: String!): Int
        field3(arg: Boolean!): Float
    }
    """

    parsed_schema = graphql.build_schema(schema)
    doc = graphql.parse(query)
    errors = graphql.validate(parsed_schema, doc)
    assert len(errors) > 0, f"Query should be invalid: {query}"


def test_negative_with_lists():
    schema = """
    type Query {
        testList(values: [Int!]!): String
        testOptionalList(values: [String]): Int
    }
    """

    query = find(queries(schema, mode=Mode.NEGATIVE), lambda q: True, settings=settings(max_examples=100))

    parsed_schema = graphql.build_schema(schema)
    doc = graphql.parse(query)
    errors = graphql.validate(parsed_schema, doc)

    assert len(errors) > 0, f"Query with lists should be invalid: {query}"


def test_negative_fails_on_schema_without_opportunities():
    schema = """
    type Query {
        test: String
        anotherField: Int
    }
    """

    # Should raise InvalidArgument because there are no arguments to violate
    with pytest.raises(InvalidArgument, match="Cannot generate invalid queries in NEGATIVE mode"):
        find(queries(schema, mode=Mode.NEGATIVE), lambda q: True, settings=settings(max_examples=10))


def test_negative_with_only_custom_scalars_fails():
    schema = """
    scalar DateTime

    type Query {
        test(time: DateTime): String
    }
    """

    with pytest.raises(InvalidArgument, match="Scalar 'DateTime' is not supported"):
        find(queries(schema, mode=Mode.NEGATIVE), lambda q: True, settings=settings(max_examples=10))


def test_negative_with_custom_scalars_and_built_ins():
    schema = """
    scalar DateTime

    type Query {
        test(time: DateTime, id: Int!): String
    }
    """

    custom_scalars = {
        "DateTime": st.text().map(nodes.String),
    }

    query_list = generate_multiple_queries(
        schema, queries(schema, custom_scalars=custom_scalars, mode=Mode.NEGATIVE), count=10
    )

    for query in query_list:
        assert_query_invalid(query, schema)


def test_negative_with_allow_null_false():
    schema = """
    type Query {
        test(value: String!): String
    }
    """

    query_list = generate_multiple_queries(schema, queries(schema, mode=Mode.NEGATIVE, allow_null=False), count=10)

    for query in query_list:
        assert_query_invalid(query, schema)

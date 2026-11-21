import datetime
import decimal
import json
import urllib.parse
import uuid

import graphql
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hypothesis_graphql import queries
from hypothesis_graphql.scalars import COMMON_SCALARS

INT64 = range(-(2**63), 2**63)
NAMES = sorted(COMMON_SCALARS)
SCHEMA = "\n".join(f"scalar {name}" for name in NAMES) + (
    "\ninput Everything {" + " ".join(f"{name}: {name}!" for name in NAMES) + "}"
    "\ntype Query { all(" + ", ".join(f"{name}: {name}!" for name in NAMES) + ", nested: [Everything!]): Int }"
)


def parse_datetime(value):
    assert value.endswith("Z")
    parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    assert parsed.utcoffset() == datetime.timedelta(0)


def parse_time(value):
    assert value.endswith("Z")
    datetime.time.fromisoformat(value[:-1])


def parse_email(value):
    local, _, domain = value.rpartition("@")
    assert local and domain


def parse_url(value):
    parts = urllib.parse.urlsplit(value)
    assert parts.scheme in ("http", "https")
    assert parts.netloc


def in_int64(value):
    assert value in INT64


def is_object(value):
    assert isinstance(value, dict)


CHECKS = {
    "Date": datetime.date.fromisoformat,
    "DateTime": parse_datetime,
    "Time": parse_time,
    "UUID": uuid.UUID,
    "JSON": json.dumps,
    "JSONObject": is_object,
    "Long": in_int64,
    "BigInt": in_int64,
    "Decimal": decimal.Decimal,
    "EmailAddress": parse_email,
    "URL": parse_url,
}
NODE_TYPES = {
    "JSON": graphql.ValueNode,
    "JSONObject": graphql.ObjectValueNode,
    "Long": graphql.IntValueNode,
    "BigInt": graphql.IntValueNode,
}


def test_names():
    assert set(COMMON_SCALARS) == set(CHECKS)


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_values(name):
    seen = set()

    @given(COMMON_SCALARS[name])
    @settings(max_examples=200)
    def test(node):
        assert isinstance(node, NODE_TYPES.get(name, graphql.StringValueNode))
        # Nullability comes from the schema, not from the scalar strategy
        assert not isinstance(node, graphql.NullValueNode)
        printed = graphql.print_ast(node)
        reparsed = graphql.parse_value(printed)
        assert graphql.print_ast(reparsed) == printed
        CHECKS[name](graphql.value_from_ast_untyped(node))
        seen.add(printed)

    test()
    assert len(seen) > 20


def test_json_covers_all_kinds():
    seen = set()

    class Collector(graphql.Visitor):
        def enter(self, node, *_):
            seen.add(type(node))

    @given(COMMON_SCALARS["JSON"])
    @settings(max_examples=300)
    def test(node):
        graphql.visit(node, Collector())

    test()
    assert seen == {
        graphql.NullValueNode,
        graphql.BooleanValueNode,
        graphql.IntValueNode,
        graphql.FloatValueNode,
        graphql.StringValueNode,
        graphql.ListValueNode,
        graphql.ObjectValueNode,
        graphql.ObjectFieldNode,
        graphql.NameNode,
    }


def test_is_read_only():
    with pytest.raises(TypeError):
        COMMON_SCALARS["Date"] = st.none()


@given(data=st.data())
def test_queries(data, validate_operation):
    query = data.draw(queries(SCHEMA, custom_scalars=COMMON_SCALARS))
    validate_operation(SCHEMA, query)
    assert "all(" in query


@given(data=st.data())
def test_merge(data, validate_operation):
    schema = SCHEMA + "\nscalar Custom\nextend type Query { custom(value: Custom!, date: Date!): Int }"
    custom = st.just(graphql.StringValueNode(value="custom"))
    query = data.draw(queries(schema, custom_scalars={**COMMON_SCALARS, "Custom": custom}, fields=["custom"]))
    validate_operation(schema, query)
    assert 'value: "custom"' in query

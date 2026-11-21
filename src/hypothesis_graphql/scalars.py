from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import graphql
from hypothesis import provisional
from hypothesis import strategies as st

from . import nodes


def _objects(values: st.SearchStrategy[graphql.ValueNode]) -> st.SearchStrategy[graphql.ValueNode]:
    # Keys of an object literal are GraphQL names
    return st.dictionaries(st.from_regex(r"[_A-Za-z][_0-9A-Za-z]{0,9}", fullmatch=True), values, max_size=5).map(
        lambda fields: nodes.Object(
            [graphql.ObjectFieldNode(name=graphql.NameNode(value=key), value=value) for key, value in fields.items()]
        )
    )


_INT64 = st.integers(min_value=-(2**63), max_value=2**63 - 1).map(nodes.Int)
_JSON: st.SearchStrategy[graphql.ValueNode] = st.recursive(
    st.booleans().map(nodes.Boolean)
    | st.integers().map(nodes.Int)
    | st.floats(allow_nan=False, allow_infinity=False).map(nodes.Float)
    | st.text().map(nodes.String),
    # `null` only nested: whether the scalar itself is nullable is up to the schema
    lambda children: (
        st.lists(children | st.just(nodes.Null), max_size=5).map(nodes.List) | _objects(children | st.just(nodes.Null))
    ),
    max_leaves=10,
)

COMMON_SCALARS: Mapping[str, st.SearchStrategy[graphql.ValueNode]] = MappingProxyType(
    {
        "Date": st.dates().map(nodes.String),
        "DateTime": st.datetimes().map(lambda value: nodes.String(f"{value.isoformat()}Z")),
        "Time": st.times().map(lambda value: nodes.String(f"{value.isoformat()}Z")),
        "UUID": st.uuids().map(nodes.String),
        "JSON": _JSON,
        "JSONObject": _objects(_JSON),
        "Long": _INT64,
        "BigInt": _INT64,
        "Decimal": st.decimals(allow_nan=False, allow_infinity=False).map(nodes.String),
        "EmailAddress": st.emails().map(nodes.String),
        "URL": provisional.urls().map(nodes.String),
    }
)

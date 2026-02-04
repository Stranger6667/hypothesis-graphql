"""Strategies for simple types like scalars or enums."""

from functools import lru_cache
from typing import Optional, Tuple, Type, TypeVar, Union

import graphql
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from .. import nodes
from ..types import ScalarValueNode

T = TypeVar("T")
MIN_INT = -(2**31)
MAX_INT = 2**31 - 1


# `String` version without extra `str` call
def _string(
    value: str, StringValueNode: Type[graphql.StringValueNode] = graphql.StringValueNode
) -> graphql.StringValueNode:
    return StringValueNode(value=value)


INTEGER_STRATEGY = st.integers(min_value=MIN_INT, max_value=MAX_INT).map(nodes.Int)
FLOAT_STRATEGY = st.floats(allow_infinity=False, allow_nan=False).map(nodes.Float)
STRING_STRATEGY = st.text().map(_string)
BOOLEAN_STRATEGY = st.booleans().map(nodes.Boolean)
NULL_STRATEGY = st.just(nodes.Null)

# Mapping of type names to their strategies for exclusion logic
_PRIMITIVE_STRATEGIES = {
    "Int": INTEGER_STRATEGY,
    "Float": FLOAT_STRATEGY,
    "String": STRING_STRATEGY,
    "Boolean": BOOLEAN_STRATEGY,
    "Null": NULL_STRATEGY,
}


def _except(*exclude: str) -> st.SearchStrategy[graphql.ValueNode]:
    # Exclude Null from wrong type violations - null is valid for nullable fields
    exclude_with_null = set(exclude) | {"Null"}
    return st.one_of(*(strategy for name, strategy in _PRIMITIVE_STRATEGIES.items() if name not in exclude_with_null))


@lru_cache(maxsize=16)
def scalar(
    alphabet: st.SearchStrategy[str],
    type_name: str,
    nullable: bool = True,
    default: Optional[graphql.ValueNode] = None,
) -> st.SearchStrategy[ScalarValueNode]:
    if type_name == "Int":
        return int_(nullable=nullable, default=default)
    if type_name == "Float":
        return float_(nullable=nullable, default=default)
    if type_name == "String":
        return string(nullable=nullable, default=default, alphabet=alphabet)
    if type_name == "ID":
        return id_(nullable=nullable, default=default, alphabet=alphabet)
    if type_name == "Boolean":
        return boolean(nullable=nullable, default=default)
    raise InvalidArgument(
        f"Scalar {type_name!r} is not supported. "
        "Provide a Hypothesis strategy via the `custom_scalars` argument to generate it."
    )


def int_(
    *, nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[graphql.IntValueNode]:
    return maybe_default(maybe_null(INTEGER_STRATEGY, nullable), default=default)


def float_(
    *, nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[graphql.FloatValueNode]:
    return maybe_default(maybe_null(FLOAT_STRATEGY, nullable), default=default)


def string(
    *, nullable: bool = True, default: Optional[graphql.ValueNode] = None, alphabet: st.SearchStrategy[str]
) -> st.SearchStrategy[graphql.StringValueNode]:
    return maybe_default(
        maybe_null(st.text(alphabet=alphabet).map(_string), nullable),
        default=default,
    )


def id_(
    *, nullable: bool = True, default: Optional[graphql.ValueNode] = None, alphabet: st.SearchStrategy[str]
) -> st.SearchStrategy[Union[graphql.StringValueNode, graphql.IntValueNode]]:
    return maybe_default(string(nullable=nullable, alphabet=alphabet) | int_(nullable=nullable), default=default)


def boolean(
    *, nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[graphql.BooleanValueNode]:
    return maybe_default(maybe_null(BOOLEAN_STRATEGY, nullable), default=default)


def maybe_null(strategy: st.SearchStrategy[T], nullable: bool) -> st.SearchStrategy[T]:
    if nullable:
        strategy |= NULL_STRATEGY
    return strategy


def custom(
    strategy: st.SearchStrategy,
    nullable: bool = True,
    default: Optional[graphql.ValueNode] = None,
) -> st.SearchStrategy:
    return maybe_default(maybe_null(strategy, nullable), default=default)


def maybe_default(
    strategy: st.SearchStrategy[T], *, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[T]:
    if default is not None:
        strategy |= st.just(default)
    return strategy


@lru_cache(maxsize=64)
def enum(
    values: Tuple[str],
    nullable: bool = True,
    default: Optional[graphql.ValueNode] = None,
) -> st.SearchStrategy[graphql.EnumValueNode]:
    return maybe_default(maybe_null(st.sampled_from(values).map(nodes.Enum), nullable), default=default)


def list_(
    strategy: st.SearchStrategy[graphql.ListValueNode],
    nullable: bool = True,
    default: Optional[graphql.ValueNode] = None,
) -> st.SearchStrategy[graphql.ListValueNode]:
    return maybe_default(maybe_null(strategy.map(nodes.List), nullable), default=default)


def invalid_int() -> st.SearchStrategy[graphql.ValueNode]:
    return _except("Int")


def invalid_string() -> st.SearchStrategy[graphql.ValueNode]:
    return _except("String")


def invalid_float() -> st.SearchStrategy[graphql.ValueNode]:
    # Int coerces to Float in GraphQL, so exclude both
    return _except("Float", "Int")


def invalid_boolean() -> st.SearchStrategy[graphql.ValueNode]:
    return _except("Boolean")


def invalid_id() -> st.SearchStrategy[graphql.ValueNode]:
    return st.one_of(FLOAT_STRATEGY, BOOLEAN_STRATEGY)


def wrong_type_for(ty: str) -> st.SearchStrategy[graphql.ValueNode]:
    if ty == "Int":
        return invalid_int()
    if ty == "String":
        return invalid_string()
    if ty == "Float":
        return invalid_float()
    if ty == "Boolean":
        return invalid_boolean()
    return invalid_id()


def out_of_range_int() -> st.SearchStrategy[graphql.IntValueNode]:
    return st.one_of(
        st.integers(max_value=MIN_INT - 1),  # Too small
        st.integers(min_value=MAX_INT + 1),  # Too large
    ).map(nodes.Int)


def invalid_enum(valid_values: Tuple[str, ...]) -> st.SearchStrategy[graphql.EnumValueNode]:
    # Use only ASCII letters, digits, and underscore to match GraphQL enum syntax
    # Enum values must match /[_A-Za-z][_0-9A-Za-z]*/ pattern
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
    first_char_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"

    return (
        st.builds(
            lambda first, rest: first + rest,
            st.sampled_from(first_char_alphabet),
            st.text(alphabet=alphabet, max_size=10),
        )
        .filter(lambda x: x not in valid_values)
        .map(nodes.Enum)
    )

# pylint: disable=unused-import
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable
from functools import reduce, wraps
from operator import or_
from typing import Any

import graphql
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument
from hypothesis.strategies._internal.utils import cacheable

from .. import nodes
from ..types import (
    AstPrinter,
    CustomScalarStrategies,
    Field,
    InputTypeNode,
)
from . import factories, primitives, validation
from .ast import make_mutation, make_query
from .mode import Mode

EMPTY_LISTS_STRATEGY = st.builds(list)
BUILT_IN_SCALAR_TYPE_NAMES = {"Int", "Float", "String", "ID", "Boolean"}


def instance_cache(key_func: Callable) -> Callable:
    def decorator(method: Callable) -> Callable:
        @wraps(method)
        def wrapped(self: GraphQLStrategy, *args: Any, **kwargs: Any) -> st.SearchStrategy:
            key = key_func(*args, **kwargs)
            memo = self._cache.setdefault(method.__name__, {})
            cached = memo.get(key)
            if cached is not None:
                return cached
            result = method(self, *args, **kwargs)
            memo[key] = result
            return result

        return wrapped

    return decorator


@dataclasses.dataclass(slots=True)
class GraphQLStrategy:
    """Strategy for generating various GraphQL nodes."""

    schema: graphql.GraphQLSchema
    alphabet: st.SearchStrategy[str]
    custom_scalars: CustomScalarStrategies = dataclasses.field(default_factory=dict)
    allow_null: bool = True
    # As the schema is assumed to be immutable, there are a few strategy caches possible for internal components
    # This is a per-method cache without limits as they are proportionate to the schema size
    _cache: dict[str, dict] = dataclasses.field(default_factory=dict)

    def values(
        self,
        type_: graphql.GraphQLInputType,
        default: graphql.ValueNode | None = None,
    ) -> st.SearchStrategy[InputTypeNode]:
        """Generate value nodes for a `GraphQLInputType` (scalar/enum/list/input object)."""
        type_, nullable = check_nullable(type_)
        if not self.allow_null:
            nullable = False

        # Types without children
        if isinstance(type_, graphql.GraphQLScalarType):
            type_name = type_.name
            if type_name in self.custom_scalars:
                return primitives.custom(self.custom_scalars[type_name], nullable, default=default)
            return primitives.scalar(alphabet=self.alphabet, type_name=type_name, nullable=nullable, default=default)
        if isinstance(type_, graphql.GraphQLEnumType):
            values = tuple(type_.values)
            return primitives.enum(values, nullable, default=default)
        # Types with children
        if isinstance(type_, graphql.GraphQLList):
            return self.lists(type_, nullable, default=default)
        if isinstance(type_, graphql.GraphQLInputObjectType):
            return self.objects(type_, nullable)
        raise TypeError(f"Type {type_.__class__.__name__} is not supported.")

    @instance_cache(
        lambda type_, nullable=True, default=None: (
            make_type_name(type_),
            nullable,
            default,
        )
    )
    def lists(
        self,
        type_: graphql.GraphQLList,
        nullable: bool = True,
        default: graphql.ValueNode | None = None,
    ) -> st.SearchStrategy[graphql.ListValueNode]:
        """Generate a `graphql.ListValueNode`."""
        strategy = st.lists(self.values(type_.of_type))
        return primitives.list_(strategy, nullable, default=default)

    @instance_cache(lambda type_, nullable=True: (type_.name, nullable))
    def objects(
        self, type_: graphql.GraphQLInputObjectType, nullable: bool = True
    ) -> st.SearchStrategy[graphql.ObjectValueNode]:
        """Generate a `graphql.ObjectValueNode`."""
        # Generate optional fields that are possible to generate and all required fields.
        # If a required field is not possible to generate, then it will fail deeper anyway
        fields = {
            name: field
            for name, field in type_.fields.items()
            if self.can_generate_field(field) or graphql.is_required_input_field(field)
        }

        strategy = subset_of_fields(fields, force_required=True).flatmap(self.lists_of_object_fields)
        return primitives.maybe_null(strategy.map(nodes.Object), nullable)

    def can_generate_field(self, field: graphql.GraphQLInputField) -> bool:
        """Whether it is possible to generate values for the given field."""
        type_ = unwrap_field_type(field)
        return (
            # Can generate any non-scalar
            not isinstance(type_, graphql.GraphQLScalarType)
            # Default scalars
            or type_.name in BUILT_IN_SCALAR_TYPE_NAMES
            # User-provided scalars
            or type_.name in self.custom_scalars
        )

    def lists_of_object_fields(
        self, items: list[tuple[str, graphql.GraphQLInputField]]
    ) -> st.SearchStrategy[list[graphql.ObjectFieldNode]]:
        return st.tuples(
            *(
                self.values(
                    field.type,
                    field.ast_node.default_value if field.ast_node is not None else None,
                ).map(factories.object_field(name))
                for name, field in items
            )
        ).map(list)

    def list_of_arguments(
        self, arguments: dict[str, graphql.GraphQLArgument]
    ) -> st.SearchStrategy[list[graphql.ArgumentNode]]:
        """Generate a list `graphql.ArgumentNode` for a field."""
        if not arguments:
            return st.just([])

        @st.composite  # type: ignore
        def inner(draw: st.DrawFn) -> list[graphql.ArgumentNode]:
            args = []
            for name, argument in arguments.items():
                default = argument.ast_node.default_value if argument.ast_node is not None else None
                try:
                    argument_strategy = self.values(argument.type, default=default)
                except InvalidArgument:
                    if not isinstance(argument.type, graphql.GraphQLNonNull):
                        # If the type is nullable, then either generate `null` or skip it completely
                        if draw(st.booleans()):
                            args.append(graphql.ArgumentNode(name=graphql.NameNode(value=name), value=nodes.Null))
                        continue
                    raise
                args.append(draw(argument_strategy.map(factories.argument(name))))
            return args

        return inner()


def check_nullable(type_: graphql.GraphQLInputType) -> tuple[graphql.GraphQLInputType, bool]:
    """Get the wrapped type and detect if it is nullable."""
    nullable = True
    if isinstance(type_, graphql.GraphQLNonNull):
        type_ = type_.of_type
        nullable = False
    return type_, nullable


def unwrap_field_type(field: Field) -> graphql.GraphQLNamedType:
    """Get the underlying field type which is not wrapped."""
    type_ = field.type
    while isinstance(type_, graphql.GraphQLWrappingType):
        type_ = type_.of_type
    return type_


def make_type_name(type_: graphql.GraphQLType) -> str:
    """Create a name for a type."""
    name = ""
    while isinstance(type_, graphql.GraphQLWrappingType):
        name += type_.__class__.__name__.replace("GraphQL", "")
        type_ = type_.of_type
    return f"{name}{type_.name}"


def subset_of_fields(
    fields: dict[str, graphql.GraphQLInputField], *, force_required: bool = False
) -> st.SearchStrategy[list[tuple[str, graphql.GraphQLInputField]]]:
    """A helper to select a subset of fields."""
    if not fields:
        # Nothing selectable, e.g. an input object whose fields are all optional and not generatable
        return EMPTY_LISTS_STRATEGY
    field_pairs = sorted(fields.items())
    # if we need to always generate required fields, then return them and extend with a subset of optional fields
    if force_required:
        required, optional = [], {}
        for name, field in field_pairs:
            # TYPING: `field` is always `GraphQLInputField` as `force_required` equals `True` only with
            # `GraphQLInputObjectType`. A better solution is to create a separate function
            if graphql.is_required_input_field(field):  # type: ignore
                required.append((name, field))
            else:
                optional[name] = field
        if optional:
            return subset_of_fields(optional).map(required.__add__)
        return st.just(required)
    # pairs are unique by field name
    return st.lists(st.sampled_from(field_pairs), min_size=1, unique_by=lambda x: x[0])


def _make_strategy(
    schema: graphql.GraphQLSchema,
    *,
    type_: graphql.GraphQLObjectType,
    fields: Iterable[str] | None = None,
    custom_scalars: CustomScalarStrategies | None = None,
    alphabet: st.SearchStrategy[str],
    allow_null: bool = True,
    mode: Mode = Mode.POSITIVE,
) -> st.SearchStrategy[list[graphql.FieldNode]]:
    """Create strategy for GraphQL selections (query/mutation fields)."""
    from .builder import build_selection_set
    from .negative_sites import negative_selection
    from .sampler import positive_selection

    if fields is not None:
        fields = tuple(fields)
        validation.validate_fields(fields, list(type_.fields))
    if custom_scalars:
        validation.validate_custom_scalars(custom_scalars)

    if mode == Mode.NEGATIVE:
        selection = negative_selection(
            schema, type_, alphabet, custom_scalars=custom_scalars or {}, allow_null=allow_null, fields=fields
        )
    else:
        selection = positive_selection(
            schema, type_, alphabet, custom_scalars=custom_scalars or {}, allow_null=allow_null, fields=fields
        )
    return selection.map(lambda sel_nodes: build_selection_set(sel_nodes, type_map=schema.type_map).selections)


def _build_alphabet(allow_x00: bool = True, codec: str | None = "utf-8") -> st.SearchStrategy[str]:
    return st.characters(
        codec=codec, min_codepoint=0 if allow_x00 else 1, max_codepoint=0xFFFF, blacklist_categories=["Cs"]
    )


@cacheable  # type: ignore
def queries(
    schema: str | graphql.GraphQLSchema,
    *,
    fields: Iterable[str] | None = None,
    custom_scalars: CustomScalarStrategies | None = None,
    print_ast: AstPrinter = graphql.print_ast,
    allow_x00: bool = True,
    allow_null: bool = True,
    codec: str | None = "utf-8",
    mode: Mode = Mode.POSITIVE,
) -> st.SearchStrategy[str]:
    r"""A strategy for generating queries for the given GraphQL schema.

    The output query will contain a subset of fields defined in the `Query` type.

    :param schema: GraphQL schema as a string or `graphql.GraphQLSchema`.
    :param fields: Restrict generated fields to ones in this list.
    :param custom_scalars: Strategies for generating custom scalars.
    :param print_ast: A function to convert the generated AST to a string.
    :param allow_x00: Determines whether to allow the generation of `\x00` bytes within strings.
    :param allow_null: Whether `null` values should be used for optional arguments.
    :param codec: Specifies the codec used for generating strings.
    :param mode: Generation mode - POSITIVE for valid queries, NEGATIVE for invalid queries.
    """
    parsed_schema = validation.maybe_parse_schema(schema)
    if parsed_schema.query_type is None:
        raise InvalidArgument("Query type is not defined in the schema")
    alphabet = _build_alphabet(allow_x00=allow_x00, codec=codec)

    return (
        _make_strategy(
            parsed_schema,
            type_=parsed_schema.query_type,
            fields=fields,
            custom_scalars=custom_scalars,
            alphabet=alphabet,
            allow_null=allow_null,
            mode=mode,
        )
        .map(make_query)
        .map(print_ast)
    )


@cacheable  # type: ignore
def mutations(
    schema: str | graphql.GraphQLSchema,
    *,
    fields: Iterable[str] | None = None,
    custom_scalars: CustomScalarStrategies | None = None,
    print_ast: AstPrinter = graphql.print_ast,
    allow_x00: bool = True,
    allow_null: bool = True,
    codec: str | None = "utf-8",
    mode: Mode = Mode.POSITIVE,
) -> st.SearchStrategy[str]:
    r"""A strategy for generating mutations for the given GraphQL schema.

    The output mutation will contain a subset of fields defined in the `Mutation` type.

    :param schema: GraphQL schema as a string or `graphql.GraphQLSchema`.
    :param fields: Restrict generated fields to ones in this list.
    :param custom_scalars: Strategies for generating custom scalars.
    :param print_ast: A function to convert the generated AST to a string.
    :param allow_x00: Determines whether to allow the generation of `\x00` bytes within strings.
    :param allow_null: Whether `null` values should be used for optional arguments.
    :param codec: Specifies the codec used for generating strings.
    :param mode: Generation mode - POSITIVE for valid mutations, NEGATIVE for invalid mutations.
    """
    parsed_schema = validation.maybe_parse_schema(schema)
    if parsed_schema.mutation_type is None:
        raise InvalidArgument("Mutation type is not defined in the schema")
    alphabet = _build_alphabet(allow_x00=allow_x00, codec=codec)

    return (
        _make_strategy(
            parsed_schema,
            type_=parsed_schema.mutation_type,
            fields=fields,
            custom_scalars=custom_scalars,
            alphabet=alphabet,
            allow_null=allow_null,
            mode=mode,
        )
        .map(make_mutation)
        .map(print_ast)
    )


@cacheable  # type: ignore
def from_schema(
    schema: str | graphql.GraphQLSchema,
    *,
    fields: Iterable[str] | None = None,
    custom_scalars: CustomScalarStrategies | None = None,
    print_ast: AstPrinter = graphql.print_ast,
    allow_x00: bool = True,
    allow_null: bool = True,
    codec: str | None = "utf-8",
    mode: Mode = Mode.POSITIVE,
) -> st.SearchStrategy[str]:
    r"""A strategy for generating queries and mutations for the given GraphQL schema.

    :param schema: GraphQL schema as a string or `graphql.GraphQLSchema`.
    :param fields: Restrict generated fields to ones in this list.
    :param custom_scalars: Strategies for generating custom scalars.
    :param print_ast: A function to convert the generated AST to a string.
    :param allow_x00: Determines whether to allow the generation of `\x00` bytes within strings.
    :param allow_null: Whether `null` values should be used for optional arguments.
    :param codec: Specifies the codec used for generating strings.
    :param mode: Generation mode - POSITIVE for valid queries/mutations, NEGATIVE for invalid ones.
    """
    parsed_schema = validation.maybe_parse_schema(schema)
    if custom_scalars:
        validation.validate_custom_scalars(custom_scalars)
    query = parsed_schema.query_type
    mutation = parsed_schema.mutation_type
    query_fields = None
    mutation_fields = None
    if fields is not None:
        # Split fields based on the type they are defined on & validate them
        fields = tuple(fields)
        available_fields = []
        if query is not None:
            query_fields = tuple(field for field in fields if field in query.fields)
            available_fields.extend(query.fields)
        if mutation is not None:
            mutation_fields = tuple(field for field in fields if field in mutation.fields)
            available_fields.extend(mutation.fields)
        validation.validate_fields(fields, available_fields)

    alphabet = _build_alphabet(allow_x00=allow_x00, codec=codec)

    # Build strategies for available types (works for both positive and negative mode)
    strategies = []
    for type_, type_fields, node_factory in (
        (query, query_fields, make_query),
        (mutation, mutation_fields, make_mutation),
    ):
        # If a type is defined in the schema and doesn't have restrictions on fields or has at least one selected field
        if type_ is None or (type_fields is not None and len(type_fields) == 0):
            continue

        # Create strategy using unified _make_strategy (handles both modes)
        strategy = (
            _make_strategy(
                parsed_schema,
                type_=type_,
                fields=type_fields,
                custom_scalars=custom_scalars,
                alphabet=alphabet,
                allow_null=allow_null,
                mode=mode,
            )
            .map(node_factory)
            .map(print_ast)
        )

        strategies.append(strategy)

    if not strategies:
        raise InvalidArgument("Query or Mutation type must be provided")

    return reduce(or_, strategies)

# pylint: disable=unused-import
import dataclasses
import operator
from functools import reduce, wraps
from operator import or_
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import graphql
from graphql import is_equal_type
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument
from hypothesis.strategies._internal.utils import cacheable

from .. import nodes
from ..types import (
    AstPrinter,
    CustomScalarStrategies,
    Field,
    InputTypeNode,
    InterfaceOrObject,
    SelectionNodes,
)
from . import factories, primitives, validation
from .ast import make_mutation, make_query
from .containers import flatten
from .mode import Mode
from .negative import ViolationTracker

BY_NAME = operator.attrgetter("name")
EMPTY_LISTS_STRATEGY = st.builds(list)
BUILT_IN_SCALAR_TYPE_NAMES = {"Int", "Float", "String", "ID", "Boolean"}


def instance_cache(key_func: Callable) -> Callable:
    def decorator(method: Callable) -> Callable:
        @wraps(method)
        def wrapped(self: "GraphQLStrategy", *args: Any, **kwargs: Any) -> st.SearchStrategy:
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


@dataclasses.dataclass
class GraphQLStrategy:
    """Strategy for generating various GraphQL nodes."""

    schema: graphql.GraphQLSchema
    alphabet: st.SearchStrategy[str]
    custom_scalars: CustomScalarStrategies = dataclasses.field(default_factory=dict)
    allow_null: bool = True
    violation_tracker: Optional[ViolationTracker] = None
    # As the schema is assumed to be immutable, there are a few strategy caches possible for internal components
    # This is a per-method cache without limits as they are proportionate to the schema size
    _cache: Dict[str, Dict] = dataclasses.field(default_factory=dict)

    def _inject_or_generate(
        self, draw: st.DrawFn, violation_strategies: List[st.SearchStrategy], valid_strategy: st.SearchStrategy
    ) -> Any:
        """Choose between injecting a violation or generating a valid value."""
        if self.violation_tracker is not None and violation_strategies:
            should_inject = self.violation_tracker.should_inject(draw)
            if should_inject:
                # Draw a strategy from the list, then draw from that strategy
                chosen_strategy = draw(st.sampled_from(violation_strategies))
                self.violation_tracker.mark_injected()
                return draw(chosen_strategy)
        return draw(valid_strategy)

    def values(
        self,
        type_: graphql.GraphQLInputType,
        default: Optional[graphql.ValueNode] = None,
    ) -> st.SearchStrategy[InputTypeNode]:
        """Generate value nodes of a type, that corresponds to the input type.

        They correspond to all `GraphQLInputType` variants:
            - GraphQLScalarType -> ScalarValueNode
            - GraphQLEnumType -> EnumValueNode
            - GraphQLInputObjectType -> ObjectValueNode

        GraphQLWrappingType[T] is unwrapped:
            - GraphQLList -> ListValueNode[T]
            - GraphQLNonNull -> T (processed with nullable=False)
        """
        if self.violation_tracker is not None:
            # Negative mode - use composite strategy to inject violations
            return self._values_with_violations(type_, default)
        return self._values_valid(type_, default)

    def _values_valid(
        self,
        type_: graphql.GraphQLInputType,
        default: Optional[graphql.ValueNode] = None,
    ) -> st.SearchStrategy[InputTypeNode]:
        """Generate valid value nodes (original behavior)."""
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

    def _values_with_violations(
        self,
        type_: graphql.GraphQLInputType,
        default: Optional[graphql.ValueNode] = None,
    ) -> st.SearchStrategy[InputTypeNode]:
        """Generate value nodes with possible violations for negative testing."""

        @st.composite  # type: ignore
        def _generate(draw: st.DrawFn) -> InputTypeNode:
            unwrapped_type, schema_nullable = check_nullable(type_)
            # For valid values, respect allow_null setting
            nullable = schema_nullable and self.allow_null

            if isinstance(unwrapped_type, graphql.GraphQLScalarType):
                type_name = unwrapped_type.name
                violations = []
                if type_name in BUILT_IN_SCALAR_TYPE_NAMES:
                    violations.append(primitives.wrong_type_for(type_name))
                if type_name == "Int":
                    violations.append(primitives.out_of_range_int())
                # Null is only a violation if schema says field is NOT nullable
                if not schema_nullable:
                    violations.append(st.just(nodes.Null))

                if type_name in self.custom_scalars:
                    valid_strategy = primitives.custom(self.custom_scalars[type_name], nullable, default=default)
                else:
                    valid_strategy = primitives.scalar(
                        alphabet=self.alphabet, type_name=type_name, nullable=nullable, default=default
                    )

                return self._inject_or_generate(draw, violations, valid_strategy)

            if isinstance(unwrapped_type, graphql.GraphQLEnumType):
                valid_values = tuple(unwrapped_type.values.keys())
                violations = [primitives.invalid_enum(valid_values)]
                valid_strategy = primitives.enum(tuple(unwrapped_type.values), nullable, default=default)
                return self._inject_or_generate(draw, violations, valid_strategy)

            if isinstance(unwrapped_type, graphql.GraphQLList):
                violations = []
                element_type = unwrapped_type.of_type
                while isinstance(element_type, graphql.GraphQLWrappingType):
                    element_type = element_type.of_type
                if (
                    isinstance(element_type, graphql.GraphQLScalarType)
                    and element_type.name in BUILT_IN_SCALAR_TYPE_NAMES
                ):
                    violations.append(primitives.wrong_type_for(element_type.name))
                elif isinstance(element_type, graphql.GraphQLEnumType):
                    violations.append(primitives.INTEGER_STRATEGY)
                if not schema_nullable:
                    violations.append(st.just(nodes.Null))

                valid_strategy = st.lists(self.values(unwrapped_type.of_type), min_size=1).map(nodes.List)
                valid_strategy = primitives.maybe_null(valid_strategy, nullable)
                valid_strategy = primitives.maybe_default(valid_strategy, default=default)

                return self._inject_or_generate(draw, violations, valid_strategy)
            # InputObject is the only remaining input type
            return draw(self.objects(unwrapped_type, nullable))

        return _generate()

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
        default: Optional[graphql.ValueNode] = None,
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

        if self.violation_tracker is not None:
            required_field_names = {name for name, field in fields.items() if graphql.is_required_input_field(field)}
            tracker = self.violation_tracker

            @st.composite  # type: ignore
            def _object_with_violations(draw: st.DrawFn) -> List[graphql.ObjectFieldNode]:
                should_violate = tracker.should_inject(draw)
                selected = draw(subset_of_fields(fields, force_required=not should_violate))
                selected_names = {name for name, _ in selected}
                if should_violate and required_field_names and not required_field_names.issubset(selected_names):
                    tracker.mark_injected()
                return draw(self.lists_of_object_fields(selected))

            strategy = _object_with_violations()
        else:
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
        self, items: List[Tuple[str, graphql.GraphQLInputField]]
    ) -> st.SearchStrategy[List[graphql.ObjectFieldNode]]:
        return st.tuples(
            *(
                self.values(
                    field.type,
                    field.ast_node.default_value if field.ast_node is not None else None,
                ).map(factories.object_field(name))
                for name, field in items
            )
        ).map(list)

    @instance_cache(
        lambda interface, implementations: (
            interface.name,
            tuple(impl.name for impl in implementations),
        )
    )
    def interfaces(
        self,
        interface: graphql.GraphQLInterfaceType,
        implementations: List[InterfaceOrObject],
    ) -> st.SearchStrategy[SelectionNodes]:
        """Build query for GraphQL interface type."""
        # If there are implementations that have fields with the same name but different types
        # then the resulting query should not have these fields simultaneously
        strategies, overlapping_fields = self.collect_fragment_strategies(implementations)
        if overlapping_fields:
            return compose_interfaces_with_filter(self.selections(interface), strategies, self.schema.type_map)
        # No overlapping - safe to choose any subset of fields within the interface itself and any fragment
        return st.tuples(self.selections(interface), *strategies).map(flatten)  # type: ignore

    @instance_cache(lambda items: tuple(item.name for item in items))
    def inline_fragments(self, items: List[graphql.GraphQLObjectType]) -> st.SearchStrategy[SelectionNodes]:
        """Create inline fragment nodes for each given item."""
        # If there are implementations that have fields with the same name but different types
        # then the resulting query should not have these fields simultaneously
        strategies, overlapping_fields = self.collect_fragment_strategies(items)
        if overlapping_fields:
            return compose_interfaces_with_filter(EMPTY_LISTS_STRATEGY, strategies, self.schema.type_map)
        # No overlapping - safe to choose any subset of fields within the interface itself and any fragment
        return st.tuples(*(self.inline_fragment(type_) for type_ in items)).map(list)

    @instance_cache(lambda type_: type_.name)
    def inline_fragment(self, type_: graphql.GraphQLObjectType) -> st.SearchStrategy[graphql.InlineFragmentNode]:
        """Build `InlineFragmentNode` for the given type."""
        return self.selections(type_).map(factories.inline_fragment(type_.name))

    @instance_cache(lambda type_, fields=None: (type_.name, fields))
    def selections(
        self,
        object_type: InterfaceOrObject,
        fields: Optional[Tuple[str, ...]] = None,
    ) -> st.SearchStrategy[List[graphql.FieldNode]]:
        """Generate a subset of fields defined on the given type."""
        if fields:
            subset = {name: value for name, value in object_type.fields.items() if name in fields}
        else:
            subset = object_type.fields
        # minimum 1 field, an empty query is not valid
        if self.violation_tracker is not None:
            return subset_of_fields_negative(subset, self.custom_scalars).flatmap(self.lists_of_fields)
        return subset_of_fields(subset).flatmap(self.lists_of_fields)

    def lists_of_fields(self, items: List[Tuple[str, Field]]) -> st.SearchStrategy[List[graphql.FieldNode]]:
        return st.tuples(
            *(
                st.tuples(self.list_of_arguments(field.args), self.selections_for_type(field)).map(
                    factories.field(name)
                )
                for name, field in items
            )
        ).map(list)

    @instance_cache(lambda items: tuple(item.name for item in items))
    def collect_fragment_strategies(
        self, items: List[graphql.GraphQLObjectType]
    ) -> Tuple[List[st.SearchStrategy[graphql.InlineFragmentNode]], bool]:
        field_types: Dict[str, graphql.GraphQLType] = {}
        strategies = []
        has_overlapping_fields = False
        for item in items:
            if not has_overlapping_fields:
                for name, field in item.fields.items():
                    if name in field_types:
                        if not is_equal_type(field.type, field_types[name]):
                            # There are fields with the same names but different types
                            has_overlapping_fields = True
                    else:
                        field_types[name] = field.type
            strategies.append(self.inline_fragment(item))
        return strategies, has_overlapping_fields

    def list_of_arguments(
        self, arguments: Dict[str, graphql.GraphQLArgument]
    ) -> st.SearchStrategy[List[graphql.ArgumentNode]]:
        """Generate a list `graphql.ArgumentNode` for a field."""
        if not arguments:
            return st.just([])

        @st.composite  # type: ignore
        def inner(draw: st.DrawFn) -> List[graphql.ArgumentNode]:
            args = []
            for name, argument in arguments.items():
                is_required = isinstance(argument.type, graphql.GraphQLNonNull)

                # Negative mode: probabilistically skip required arguments (violation)
                if is_required and self.violation_tracker is not None and self.violation_tracker.should_inject(draw):
                    self.violation_tracker.mark_injected()
                    continue

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

    def selections_for_type(
        self,
        field: graphql.GraphQLField,
    ) -> st.SearchStrategy[Optional[SelectionNodes]]:
        """Extract proper type from the field and generate field nodes for this type."""
        field_type = unwrap_field_type(field)
        if isinstance(field_type, graphql.GraphQLObjectType):
            return self.selections(field_type)
        if isinstance(field_type, graphql.GraphQLInterfaceType):
            # Besides the fields on the interface type, it is possible to generate inline fragments on types that
            # implement this interface type
            implementations = self.schema.get_implementations(field_type).objects
            if not implementations:
                # Shortcut when there are no implementations - take fields from the interface itself
                return self.selections(field_type)
            return st.lists(st.sampled_from(implementations), min_size=1, unique_by=BY_NAME).flatmap(
                lambda impls: self.interfaces(field_type, impls)
            )
        if isinstance(field_type, graphql.GraphQLUnionType):
            # A union is a set of object types - take a subset of them and generate inline fragments
            return st.lists(st.sampled_from(field_type.types), min_size=1, unique_by=BY_NAME).flatmap(
                self.inline_fragments
            )
        # Other types don't have fields
        return st.none()


def check_nullable(type_: graphql.GraphQLInputType) -> Tuple[graphql.GraphQLInputType, bool]:
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


@st.composite  # type: ignore
def compose_interfaces_with_filter(
    draw: st.DrawFn,
    already_selected: st.SearchStrategy[List],
    strategies: List[st.SearchStrategy[SelectionNodes]],
    type_map: Dict[str, graphql.GraphQLType],
) -> SelectionNodes:
    selection_nodes = draw(already_selected)
    # Store what fields are already used and their corresponding types
    seen: Dict[str, graphql.GraphQLType] = {}

    def mark_seen(frag: graphql.InlineFragmentNode) -> None:
        # Add this fragment's fields to `seen`
        fragment_type = type_map[frag.type_condition.name.value]
        for selected in frag.selection_set.selections:
            seen.setdefault(selected.name.value, fragment_type.fields[selected.name.value].type)

    def add_alias(frag: graphql.InlineFragmentNode) -> graphql.InlineFragmentNode:
        # Add an alias for all fields that have the same name with already selected ones but a different type
        fragment_type = type_map[frag.type_condition.name.value]
        for selected in frag.selection_set.selections:
            field_name = selected.name.value
            if field_name in seen:
                field_type = fragment_type.fields[field_name].type
                if not is_equal_type(seen[field_name], field_type):
                    selected.alias = graphql.NameNode(value=f"{field_name}_{make_type_name(field_type)}")
        return frag

    for strategy in strategies:
        fragment = draw(strategy.map(add_alias))
        selection_nodes.append(fragment)
        mark_seen(fragment)
    return selection_nodes


def subset_of_fields(
    fields: Dict[str, graphql.GraphQLInputField], *, force_required: bool = False
) -> st.SearchStrategy[List[Tuple[str, graphql.GraphQLInputField]]]:
    """A helper to select a subset of fields."""
    if not fields:
        # The schema is invalid as there should be at least one field
        # But there should not be an internal error because of it
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


def _has_violation_opportunities(field: Field, custom_scalars: CustomScalarStrategies) -> bool:
    """Check if a field has opportunities for violation injection."""
    # Field has required arguments
    for arg in field.args.values():
        if isinstance(arg.type, graphql.GraphQLNonNull):
            return True
        # Field has built-in scalar arguments (can inject wrong type)
        arg_type = arg.type
        while isinstance(arg_type, graphql.GraphQLWrappingType):
            arg_type = arg_type.of_type
        if isinstance(arg_type, graphql.GraphQLScalarType) and arg_type.name in BUILT_IN_SCALAR_TYPE_NAMES:
            return True
        if isinstance(arg_type, graphql.GraphQLEnumType):
            return True
        if isinstance(arg_type, graphql.GraphQLInputObjectType):
            # Check for required fields in input type
            for input_field in arg_type.fields.values():
                if graphql.is_required_input_field(input_field):
                    return True
    return False


def subset_of_fields_negative(
    fields: Dict[str, Field], custom_scalars: CustomScalarStrategies
) -> st.SearchStrategy[List[Tuple[str, Field]]]:
    """Select fields for negative mode, ensuring at least one field with violation opportunities."""
    field_pairs = sorted(fields.items())
    with_violations = [(n, f) for n, f in field_pairs if _has_violation_opportunities(f, custom_scalars)]

    if not with_violations:
        # No fields have violation opportunities - fall back to regular selection
        return st.lists(st.sampled_from(field_pairs), min_size=1, unique_by=lambda x: x[0])

    # Always include at least one field with violation opportunities
    # Then optionally add more fields from either category
    @st.composite  # type: ignore
    def select_fields(draw: st.DrawFn) -> List[Tuple[str, Field]]:
        # Pick at least one field with violations
        required_field = draw(st.sampled_from(with_violations))
        result = [required_field]

        # Optionally add more fields
        remaining = [f for f in field_pairs if f[0] != required_field[0]]
        if remaining:
            additional = draw(st.lists(st.sampled_from(remaining), unique_by=lambda x: x[0]))
            result.extend(additional)

        return result

    return select_fields()


def _make_strategy(
    schema: graphql.GraphQLSchema,
    *,
    type_: graphql.GraphQLObjectType,
    fields: Optional[Iterable[str]] = None,
    custom_scalars: Optional[CustomScalarStrategies] = None,
    alphabet: st.SearchStrategy[str],
    allow_null: bool = True,
    mode: Mode = Mode.POSITIVE,
) -> st.SearchStrategy[List[graphql.FieldNode]]:
    """Create strategy for GraphQL selections (query/mutation fields).

    Positive mode: Returns selections directly.
    Negative mode: Wraps in composite with fresh ViolationTracker per query,
                   validates at least one violation was injected.
    """
    if fields is not None:
        fields = tuple(fields)
        validation.validate_fields(fields, list(type_.fields))
    if custom_scalars:
        validation.validate_custom_scalars(custom_scalars)

    if mode == Mode.NEGATIVE:

        @st.composite  # type: ignore
        def _with_tracker(draw: st.DrawFn) -> List[graphql.FieldNode]:
            tracker = ViolationTracker()

            strategy_inst = GraphQLStrategy(
                schema=schema,
                alphabet=alphabet,
                custom_scalars=custom_scalars or {},
                allow_null=allow_null,
                violation_tracker=tracker,
            )

            selections = draw(strategy_inst.selections(type_, fields=fields))

            # Verify at least one violation was injected
            if not tracker.has_injected:
                raise InvalidArgument(
                    "Cannot generate invalid queries in NEGATIVE mode: schema has no required "
                    "arguments or built-in scalar types to violate. The schema needs at least "
                    "one field with a required argument (e.g., `field(arg: Int!)`) or an enum type."
                )

            return selections

        return _with_tracker()
    return GraphQLStrategy(
        schema=schema,
        alphabet=alphabet,
        custom_scalars=custom_scalars or {},
        allow_null=allow_null,
    ).selections(type_, fields=fields)


def _build_alphabet(allow_x00: bool = True, codec: Optional[str] = "utf-8") -> st.SearchStrategy[str]:
    return st.characters(
        codec=codec, min_codepoint=0 if allow_x00 else 1, max_codepoint=0xFFFF, blacklist_categories=["Cs"]
    )


@cacheable  # type: ignore
def queries(
    schema: Union[str, graphql.GraphQLSchema],
    *,
    fields: Optional[Iterable[str]] = None,
    custom_scalars: Optional[CustomScalarStrategies] = None,
    print_ast: AstPrinter = graphql.print_ast,
    allow_x00: bool = True,
    allow_null: bool = True,
    codec: Optional[str] = "utf-8",
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
    schema: Union[str, graphql.GraphQLSchema],
    *,
    fields: Optional[Iterable[str]] = None,
    custom_scalars: Optional[CustomScalarStrategies] = None,
    print_ast: AstPrinter = graphql.print_ast,
    allow_x00: bool = True,
    allow_null: bool = True,
    codec: Optional[str] = "utf-8",
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
    schema: Union[str, graphql.GraphQLSchema],
    *,
    fields: Optional[Iterable[str]] = None,
    custom_scalars: Optional[CustomScalarStrategies] = None,
    print_ast: AstPrinter = graphql.print_ast,
    allow_x00: bool = True,
    allow_null: bool = True,
    codec: Optional[str] = "utf-8",
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

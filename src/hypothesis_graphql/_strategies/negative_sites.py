import dataclasses
from typing import List, Optional, Sequence, Tuple

import graphql
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from .. import nodes
from . import primitives
from .builder import SelectionNode
from .oracle import is_leaf, selectable_fields, unwrap
from .strategy import GraphQLStrategy

BUILT_IN = {"Int", "Float", "String", "ID", "Boolean"}
MAX_DEPTH = 10


@dataclasses.dataclass(frozen=True)
class PathStep:
    field_name: str
    on_type: Optional[str]


@dataclasses.dataclass(frozen=True)
class ViolationSite:
    path: Tuple[PathStep, ...]
    arg_name: str
    kinds: Tuple[str, ...]

    @property
    def field_path(self) -> Tuple[str, ...]:
        return tuple(step.field_name for step in self.path)

    @property
    def depth(self) -> int:
        return len(self.path)


def _arg_kinds(arg: graphql.GraphQLArgument) -> Tuple[str, ...]:
    kinds: List[str] = []
    required = isinstance(arg.type, graphql.GraphQLNonNull)
    inner = unwrap(arg.type)
    if required:
        kinds.extend(("missing_required", "null"))
    if isinstance(inner, graphql.GraphQLScalarType) and inner.name in BUILT_IN:
        kinds.append("wrong_type")
        if inner.name == "Int":
            kinds.append("out_of_range")
    if isinstance(inner, graphql.GraphQLEnumType):
        kinds.append("invalid_enum")
    if isinstance(inner, graphql.GraphQLInputObjectType) and any(
        graphql.is_required_input_field(field) for field in inner.fields.values()
    ):
        kinds.append("missing_input_field")
    return tuple(kinds)


def enumerate_violation_sites(schema: graphql.GraphQLSchema, root: graphql.GraphQLNamedType) -> List[ViolationSite]:
    # One representative path per type. Enumerating every route explodes combinatorially on
    # dense recursive schemas; we only need a reachable path to each violatable field.
    sites: List[ViolationSite] = []
    walked: set = set()

    def walk(type_: graphql.GraphQLNamedType, path: Tuple[PathStep, ...]) -> None:
        if type_.name in walked or len(path) > MAX_DEPTH:
            return
        walked.add(type_.name)
        for name, field, on_type in selectable_fields(schema, type_):
            step_path = path + (PathStep(name, on_type),)
            for arg_name, arg in field.args.items():
                kinds = _arg_kinds(arg)
                if kinds:
                    sites.append(ViolationSite(step_path, arg_name, kinds))
            target = unwrap(field.type)
            if not is_leaf(target):
                walk(target, step_path)

    walk(root, ())
    return sites


def _find_field(
    schema: graphql.GraphQLSchema, type_: graphql.GraphQLNamedType, name: str, on_type: Optional[str]
) -> graphql.GraphQLField:
    # The (name, on_type) pair always comes from a previously enumerated path, so it is present.
    return next(
        field
        for candidate_name, field, candidate_on_type in selectable_fields(schema, type_)
        if candidate_name == name and candidate_on_type == on_type
    )


def _input_missing_required(
    draw: st.DrawFn, gql: GraphQLStrategy, input_type: graphql.GraphQLInputObjectType
) -> graphql.ObjectValueNode:
    required = [name for name, field in input_type.fields.items() if graphql.is_required_input_field(field)]
    omit = required[0]
    fields = []
    for name, field in input_type.fields.items():
        if name == omit:
            continue
        if graphql.is_required_input_field(field):
            fields.append(
                graphql.ObjectFieldNode(name=graphql.NameNode(value=name), value=draw(gql.values(field.type)))
            )
    return graphql.ObjectValueNode(fields=tuple(fields))


def _violation_value(
    draw: st.DrawFn, gql: GraphQLStrategy, arg: graphql.GraphQLArgument, kind: str
) -> graphql.ValueNode:
    inner = unwrap(arg.type)
    if kind == "null":
        return nodes.Null
    if kind == "wrong_type":
        return draw(primitives.wrong_type_for(inner.name))
    if kind == "out_of_range":
        return draw(primitives.out_of_range_int())
    if kind == "invalid_enum":
        return draw(primitives.invalid_enum(tuple(inner.values)))
    # Only "missing_input_field" remains.
    return _input_missing_required(draw, gql, inner)


def _corrupt_args(
    draw: st.DrawFn, gql: GraphQLStrategy, field: graphql.GraphQLField, target_arg: str, kind: str
) -> List[graphql.ArgumentNode]:
    others = {name: arg for name, arg in field.args.items() if name != target_arg}
    args = list(draw(gql.list_of_arguments(others)))
    if kind == "missing_required":
        # Omit the required target argument entirely.
        return args
    value = _violation_value(draw, gql, field.args[target_arg], kind)
    args.append(graphql.ArgumentNode(name=graphql.NameNode(value=target_arg), value=value))
    return args


def _extend_to_leaf(
    draw: st.DrawFn,
    schema: graphql.GraphQLSchema,
    gql: GraphQLStrategy,
    type_: graphql.GraphQLNamedType,
    seen: frozenset,
) -> Optional[List[SelectionNode]]:
    if type_.name in seen:
        return None
    seen = seen | {type_.name}
    for name, field, on_type in selectable_fields(schema, type_):
        if is_leaf(unwrap(field.type)):
            return [(name, on_type, [], draw(gql.list_of_arguments(field.args)))]
    for name, field, on_type in selectable_fields(schema, type_):
        child = _extend_to_leaf(draw, schema, gql, unwrap(field.type), seen)
        if child:
            return [(name, on_type, child, draw(gql.list_of_arguments(field.args)))]
    return None


def negative_selection(
    schema: graphql.GraphQLSchema,
    root: graphql.GraphQLObjectType,
    alphabet: st.SearchStrategy[str],
    custom_scalars: Optional[dict] = None,
    allow_null: bool = True,
    fields: Optional[Sequence[str]] = None,
) -> st.SearchStrategy[List[SelectionNode]]:
    # Enumerated once per strategy build; the strategy itself is constructed once.
    sites = enumerate_violation_sites(schema, root)
    if fields is not None:
        allowed = set(fields)
        sites = [site for site in sites if site.path[0].field_name in allowed]
    gql = GraphQLStrategy(schema=schema, alphabet=alphabet, custom_scalars=custom_scalars or {}, allow_null=allow_null)

    @st.composite  # type: ignore
    def _generate(draw: st.DrawFn) -> List[SelectionNode]:
        if not sites:
            raise InvalidArgument(
                "Cannot generate invalid queries in NEGATIVE mode: schema has no required "
                "arguments or built-in scalar types to violate."
            )
        site = draw(st.sampled_from(sites))
        kind = draw(st.sampled_from(site.kinds))

        resolved = []
        cur = root
        for step in site.path:
            field = _find_field(schema, cur, step.field_name, step.on_type)
            resolved.append((step.field_name, step.on_type, field))
            cur = unwrap(field.type)

        *spine, (target_name, target_on_type, target_field) = resolved
        target_args = _corrupt_args(draw, gql, target_field, site.arg_name, kind)
        target_type = unwrap(target_field.type)
        children = [] if is_leaf(target_type) else (_extend_to_leaf(draw, schema, gql, target_type, frozenset()) or [])
        node = (target_name, target_on_type, children, target_args)
        for name, on_type, field in reversed(spine):
            node = (name, on_type, [node], draw(gql.list_of_arguments(field.args)))
        return [node]

    return _generate()

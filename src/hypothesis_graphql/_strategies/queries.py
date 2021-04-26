"""Strategies for GraphQL queries."""
from functools import partial
from typing import Callable, Dict, Generator, Iterable, List, Optional, Tuple, TypeVar, Union

import attr
import graphql
from hypothesis import strategies as st
from hypothesis.strategies._internal.core import defines_strategy

from ..types import Field, InputTypeNode
from . import primitives

T = TypeVar("T")
Draw = Callable[[st.SearchStrategy[T]], T]
FieldTuple = Tuple[str, Field]
FieldTuples = List[FieldTuple]


@attr.s(slots=True)
class Node:
    """Node of an intermediate output tree."""

    name: str = attr.ib()
    type: graphql.GraphQLNamedType = attr.ib()
    children: List["Node"] = attr.ib()
    field: Optional[Field] = attr.ib(default=None)
    args: Optional[List[graphql.ArgumentNode]] = attr.ib(default=None)
    already_extended: bool = attr.ib(default=False)

    @classmethod
    def from_object_type(cls, object_type: graphql.GraphQLObjectType, children: FieldTuples) -> "Node":
        return cls(
            name=object_type.name,
            type=object_type,
            children=cls.into_nodes(children),
        )

    @classmethod
    def from_field(cls, name: str, field: Field, args: Optional[List[graphql.ArgumentNode]] = None) -> "Node":
        return cls(name=name, field=field, type=unwrap_field_type(field), args=args, children=[])

    @classmethod
    def into_nodes(cls, tuples: FieldTuples) -> List["Node"]:
        return [cls.from_field(name, field) for name, field in tuples]

    def __iter__(self) -> Generator["Node", None, None]:
        """Depth-first tree traversal."""
        for child in self.children:
            yield from child
            yield child

    @property
    def is_complete(self) -> bool:
        """Whether this node requires further modifications.

        Unless nodes are complete we can't build a valid GraphQL query from it.
        """
        if isinstance(self.field, graphql.GraphQLField):
            # All not-nullable arguments should be present
            for name, arg in self.field.args.items():
                if graphql.is_non_null_type(arg.type):
                    if self.args:
                        if not any(existing_arg.name.value == name for existing_arg in self.args):
                            return False
                    else:
                        return False
        if isinstance(self.type, graphql.GraphQLObjectType):
            # Objects should have at least one field
            return bool(self.children)
        return True

    def as_field_nodes(self) -> List[graphql.FieldNode]:
        """Convert this intermediate tree node and all its children to GraphQL AST nodes."""
        return [
            graphql.FieldNode(
                name=graphql.NameNode(value=child.name),
                arguments=child.args,
                selection_set=graphql.SelectionSetNode(kind="selection_set", selections=child.as_field_nodes()),
            )
            for child in self.children
        ]


def query(schema: Union[str, graphql.GraphQLSchema], fields: Optional[Iterable[str]] = None) -> st.SearchStrategy[str]:
    """A strategy for generating valid queries for the given GraphQL schema.

    The output query will contain a subset of fields defined in the `Query` type.

    :param schema: GraphQL schema as a string or `graphql.GraphQLSchema`.
    :param fields: Restrict generated fields to ones in this list.
    """
    if isinstance(schema, str):
        parsed_schema = graphql.build_schema(schema)
    else:
        parsed_schema = schema
    query_type = parsed_schema.query_type
    if query_type is None:
        raise ValueError("Query type is not defined in the schema")
    if fields is not None:
        fields = tuple(fields)
        validate_fields(query_type, fields)
    # Building process:
    #  1. Generate an intermediate tree. Each node contains information like field type, arguments, etc
    #  2. Convert that tree to GraphQL AST
    #  3. Convert AST to a string
    return query_tree(query_type, fields).map(tree_to_ast).map(graphql.print_ast)


def validate_fields(query_type: graphql.GraphQLObjectType, fields: Tuple[str, ...]) -> None:
    """Check whether the passed field tuple contains valid field names."""
    if not fields:
        raise ValueError("If you pass `fields`, it should not be empty")
    invalid_fields = tuple(field for field in fields if field not in query_type.fields)
    if invalid_fields:
        raise ValueError(f"Unknown fields: {', '.join(invalid_fields)}")


@defines_strategy()  # type: ignore
def query_tree(
    query_type: graphql.GraphQLObjectType, fields: Optional[Tuple[str, ...]] = None
) -> st.SearchStrategy[Node]:
    """Return an intermediate tree for a GraphQL query type.

    Tree building process:
      1. Create a root node.
      2. Extend it with child nodes
      3. Finish incomplete nodes

    We don't know upfront if some nodes will require at least one child. For example, Object field types require at
    least one field to be present in selection. Therefore we first build an incomplete tree fast, using Hypothesis's
    recursive strategy, and then finish incomplete nodes.
    """
    if fields:
        selection = {name: value for name, value in query_type.fields.items() if name in fields}
    else:
        selection = query_type.fields
    return st.recursive(
        root(query_type, selection),
        extend_tree,
    ).flatmap(finish_tree)


@st.composite  # type: ignore
def root(draw: Draw, object_type: graphql.GraphQLObjectType, selection: Dict[str, graphql.GraphQLField]) -> Node:
    """Create a root node."""
    fields = draw(fields_sample(selection))
    return Node.from_object_type(object_type, fields)


@st.composite  # type: ignore
def extend_tree(draw: Draw, tree_strategy: st.SearchStrategy[Node]) -> Node:
    """Extend generated tree with additional nodes & arguments."""
    tree = draw(tree_strategy)
    for node in tree:
        if not node.already_extended:
            if isinstance(node.type, graphql.GraphQLObjectType):
                node.children = draw(fields_sample(node.type.fields).map(Node.into_nodes))
            if node.field.args:
                node.args = draw(list_of_arguments(node.field.args))
            node.already_extended = True
    return tree


@st.composite  # type: ignore
def finish_tree(draw: Draw, tree: Node) -> Node:
    # It should finish incomplete nodes
    # object types should have at least one field selected - this should run until all nodes are valid
    # try to finish it as soon as possible, as the main growing process happens in `extend_tree`
    for node in tree:
        while not node.is_complete:
            if isinstance(node.field, graphql.GraphQLField) and node.field.args:
                node.args = draw(list_of_arguments(node.field.args))
            if isinstance(node.type, graphql.GraphQLObjectType):
                fields = draw(fields_sample(node.type.fields))
                non_object_fields = [
                    (name, field) for name, field in fields if not isinstance(field, graphql.GraphQLObjectType)
                ]
                if non_object_fields:
                    node.children = Node.into_nodes(non_object_fields)
                else:
                    node.children = Node.into_nodes(fields)
                    finish_tree(node)
    return tree


@defines_strategy()  # type: ignore
def fields_sample(fields: Dict[str, T]) -> st.SearchStrategy[List[Tuple[str, T]]]:
    """Return a list of unique (name, field) pairs drawn from the input fields.

    The results are used to select a subset of possible fields in GraphQL queries.
    """
    if len(fields) == 1:
        # If there is only one field, then we can skip sampling and take this field directly
        pair = tuple(fields.items())[0]
        return st.just([pair])
    pairs = sorted(fields.items())
    samples = st.sampled_from(pairs)

    def by_name(pair: FieldTuple) -> str:
        # pairs should be unique by field name - they will be used to construct a JSON object on the server side
        # and according to RFC 7159 non-unique keys in objects may lead to unpredictable behavior during the parsing
        # step. Often only the latest key will be taken, but we can prevent it here
        return pair[0]

    return st.lists(samples, min_size=1, unique_by=by_name)


def unwrap_field_type(field: Field) -> graphql.GraphQLNamedType:
    """Get the underlying field type which is not wrapped."""
    type_ = field.type
    while isinstance(type_, graphql.GraphQLWrappingType):
        type_ = type_.of_type
    return type_


def tree_to_ast(tree: Node) -> graphql.DocumentNode:
    """Build AST from a generated tree."""
    return graphql.DocumentNode(
        kind="document",
        definitions=[
            graphql.OperationDefinitionNode(
                kind="operation_definition",
                operation=graphql.OperationType.QUERY,
                selection_set=graphql.SelectionSetNode(kind="selection_set", selections=tree.as_field_nodes()),
            )
        ],
    )


def list_of_arguments(arguments: Dict[str, graphql.GraphQLArgument]) -> st.SearchStrategy[List[graphql.ArgumentNode]]:
    """Generate a list `graphql.ArgumentNode` for a field."""
    argument_strategies = []
    for name, argument in arguments.items():
        try:
            argument_strategy = value_nodes(argument.type)
        except TypeError as exc:
            if not isinstance(argument.type, graphql.GraphQLNonNull):
                continue
            raise TypeError("Non-nullable custom scalar types are not supported as arguments") from exc
        argument_strategies.append(
            st.builds(partial(graphql.ArgumentNode, name=graphql.NameNode(value=name)), value=argument_strategy)
        )
    return st.tuples(*argument_strategies).map(list)


def value_nodes(type_: graphql.GraphQLInputType) -> st.SearchStrategy[InputTypeNode]:
    """Generate value nodes of a type, that corresponds to the input type.

    They correspond to all `GraphQLInputType` variants:
        - GraphQLScalarType -> ScalarValueNode
        - GraphQLEnumType -> EnumValueNode
        - GraphQLInputObjectType -> ObjectValueNode

    GraphQLWrappingType[T] is unwrapped:
        - GraphQLList -> ListValueNode[T]
        - GraphQLNonNull -> T (processed with nullable=False)
    """
    type_, nullable = check_nullable(type_)
    # Types without children
    if isinstance(type_, graphql.GraphQLScalarType):
        return primitives.scalar(type_, nullable)
    if isinstance(type_, graphql.GraphQLEnumType):
        return primitives.enum(type_, nullable)
    # Types with children
    if isinstance(type_, graphql.GraphQLList):
        return lists(type_, nullable)
    if isinstance(type_, graphql.GraphQLInputObjectType):
        return objects(type_, nullable)
    raise TypeError(f"Type {type_.__class__.__name__} is not supported.")


def check_nullable(type_: graphql.GraphQLInputType) -> Tuple[graphql.GraphQLInputType, bool]:
    """Get the wrapped type and detect if it is nullable."""
    nullable = True
    if isinstance(type_, graphql.GraphQLNonNull):
        type_ = type_.of_type
        nullable = False
    return type_, nullable


def lists(list_type: graphql.GraphQLList, nullable: bool = True) -> st.SearchStrategy[graphql.ListValueNode]:
    """Generate a `graphql.ListValueNode`."""
    list_value = st.lists(value_nodes(list_type.of_type))
    if nullable:
        list_value |= st.none()
    return st.builds(graphql.ListValueNode, values=list_value)


def objects(
    object_type: graphql.GraphQLInputObjectType, nullable: bool = True
) -> st.SearchStrategy[graphql.ObjectValueNode]:
    """Generate a `graphql.ObjectValueNode`."""
    fields_value = fields_sample(object_type.fields).flatmap(list_of_nodes)
    if nullable:
        fields_value |= st.none()
    return st.builds(graphql.ObjectValueNode, fields=fields_value)


def object_field_nodes(name: str, field: graphql.GraphQLInputField) -> st.SearchStrategy[graphql.ObjectFieldNode]:
    """Generate AST node for an input field."""
    return st.builds(
        partial(graphql.ObjectFieldNode, name=graphql.NameNode(value=name)),
        value=value_nodes(field.type),
    )


def list_of_nodes(
    items: List[Tuple[str, graphql.GraphQLInputField]]
) -> st.SearchStrategy[List[graphql.ObjectFieldNode]]:
    """Strategy for generating lists of AST nodes for input fields."""
    return st.tuples(*(object_field_nodes(name, field) for name, field in items)).map(list)

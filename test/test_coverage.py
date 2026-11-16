import graphql
import pytest
from hypothesis.errors import InvalidArgument

from benchmarks._schemas import SCHEMAS
from hypothesis_graphql._strategies.coverage import covering_operations

BUILT_IN = {"Int", "Float", "String", "ID", "Boolean"}
COMPOSITE = (graphql.GraphQLObjectType, graphql.GraphQLInterfaceType, graphql.GraphQLUnionType)
ONE_OF_SUPPORTED = graphql.version_info >= (3, 2, 7)

BASIC = """
type Query {
  node(id: ID!): Node
  search(term: String!, limit: Int = 10, kind: Kind): [Node!]
}
type Node { id: ID! name: String parent: Node }
enum Kind { A B }
"""
ABSTRACT = """
type Query { thing: Thing pet: Pet }
union Thing = Dog | Rock
interface Pet { name: String }
type Dog implements Pet { name: String barks: Boolean owner: Owner }
type Rock { weight: Float }
type Owner { pets(first: Int): [Pet] }
"""
MUTATIONS = """
type Query { a: Int }
type Mutation {
  create(input: CreateInput!): Result
  delete(id: ID!, force: Boolean): Boolean
}
input CreateInput { name: String! tags: [String!]! meta: Meta nested: Nested! }
input Nested { n: Int! f: Float! opt: Int }
input Meta { key: String! }
type Result { ok: Boolean item: Item }
type Item { id: ID }
"""
CUSTOM_SCALARS = """
scalar Date
type Query {
  events(after: Date): [Event]
  on(day: Date!): Event
  since(day: Date! = "2020-01-01", range: Range): Event
  filtered(filter: Filter!): Hidden
  ok(filter: Lenient!, range: Range): Int
}
input Range { from: Date! to: Date }
input Filter { range: Range! }
input Lenient { range: Range day: Date name: String! }
type Event { id: ID at(zone: Date!): String attendees(since: Date, first: Int): [String] }
type Hidden { secret: String }
"""
LISTS_AND_DEFAULTS = """
type Query {
  items(ids: [ID!]!, tags: [[String]], order: Order = DESC, page: Page = {size: 5}, ratio: Float, flag: Boolean!): [Item!]!
}
enum Order { ASC DESC }
input Page { size: Int! offset: Int = 0 }
type Item { id: ID children(depth: Int! = 1): [Item] }
"""
NO_LEAF = """
type Query { loop: Loop only: Only }
type Loop { next: Loop }
union Only = Loop
"""
MUTATION_ONLY = """
type Mutation { bump(by: Int): Counter reset: Boolean }
type Counter { value: Int history(last: Int): [Int] }
"""
INTERFACE_ARGS = """
type Query { shapes(kind: Kind!): [Shape] }
enum Kind { ROUND FLAT }
interface Shape { area(unit: Unit): Float }
enum Unit { M FT }
type Circle implements Shape { area(unit: Unit, precise: Boolean): Float radius: Float! }
type Square implements Shape { area(unit: Unit): Float side: Int owner: Shape }
"""
ONE_OF = """
type Query { find(by: By!, alt: Alt): Int broken(by: Opaque!): Int }
scalar Blob
input By @oneOf { blob: Blob self: By id: ID name: String }
input Alt @oneOf { by: By }
input Opaque @oneOf { blob: Blob }
"""
SMALL = {
    "basic": BASIC,
    "abstract": ABSTRACT,
    "mutations": MUTATIONS,
    "custom-scalars": CUSTOM_SCALARS,
    "lists-and-defaults": LISTS_AND_DEFAULTS,
    "no-leaf": NO_LEAF,
    "interface-args": INTERFACE_ARGS,
}
if ONE_OF_SUPPORTED:
    SMALL["one-of"] = ONE_OF
ALL = {**{f"bench-{name}": sdl for name, sdl in SCHEMAS.items()}, **SMALL}


def unbuildable(type_, seen=frozenset()):
    # No deterministic literal exists: an unknown custom scalar is required somewhere inside
    if isinstance(type_, graphql.GraphQLNonNull):
        return unbuildable(type_.of_type, seen)
    if isinstance(type_, graphql.GraphQLScalarType):
        return type_.name not in BUILT_IN
    if isinstance(type_, graphql.GraphQLInputObjectType):
        if type_.name in seen:
            return True
        seen = seen | {type_.name}
        if getattr(type_, "is_one_of", False):
            return all(unbuildable(field.type, seen) for field in type_.fields.values())
        return any(
            unbuildable(field.type, seen) for field in type_.fields.values() if graphql.is_required_input_field(field)
        )
    return False


def has_default(arg):
    return arg.ast_node is not None and arg.ast_node.default_value is not None


def expected(schema, fields=None):
    pairs, triples, excluded = set(), set(), set()
    roots = [type_ for type_ in (schema.query_type, schema.mutation_type) if type_ is not None]
    seen = set()
    stack = list(roots)
    while stack:
        type_ = stack.pop()
        if type_.name in seen:
            continue
        seen.add(type_.name)
        if isinstance(type_, graphql.GraphQLUnionType):
            stack.extend(type_.types)
            continue
        if isinstance(type_, graphql.GraphQLInterfaceType):
            stack.extend(schema.get_implementations(type_).objects)
        for name, field in type_.fields.items():
            if fields is not None and type_ in roots and name not in fields:
                continue
            if any(graphql.is_required_argument(arg) and unbuildable(arg.type) for arg in field.args.values()):
                excluded.add((type_.name, name))
                continue
            pairs.add((type_.name, name))
            for arg_name, arg in field.args.items():
                if has_default(arg) or not unbuildable(arg.type):
                    triples.add((type_.name, name, arg_name))
                else:
                    excluded.add((type_.name, name, arg_name))
            target = graphql.get_named_type(field.type)
            if isinstance(target, COMPOSITE):
                stack.append(target)
    return pairs, triples, excluded


def covered(schema, documents):
    pairs, triples = set(), set()
    type_info = graphql.TypeInfo(schema)

    class Visitor(graphql.Visitor):
        def enter_field(self, node, *_):
            if node.name.value == "__typename":
                return
            parent = type_info.get_parent_type().name
            pairs.add((parent, node.name.value))
            for argument in node.arguments:
                triples.add((parent, node.name.value, argument.name.value))

    for document in documents:
        graphql.visit(document, graphql.TypeInfoVisitor(type_info, Visitor()))
    return pairs, triples


def printed(schema, **kwargs):
    return [graphql.print_ast(document) for document in covering_operations(schema, **kwargs)]


def normalized(*queries):
    return [graphql.print_ast(graphql.parse(query)) for query in queries]


def root_fields(document):
    (operation,) = document.definitions
    return operation.operation, operation.selection_set.selections


@pytest.mark.parametrize("sdl", ALL.values(), ids=list(ALL))
def test_covers_every_reachable_field_and_argument(sdl):
    schema = graphql.build_schema(sdl)
    documents = list(covering_operations(schema))
    for document in documents:
        assert graphql.validate(schema, document) == [], graphql.print_ast(document)
    pairs, triples, _ = expected(schema)
    assert covered(schema, documents) == (pairs, triples)


@pytest.mark.parametrize("sdl", ALL.values(), ids=list(ALL))
def test_deterministic(sdl):
    assert printed(sdl) == printed(graphql.build_schema(sdl))


@pytest.mark.parametrize("sdl", ALL.values(), ids=list(ALL))
def test_every_document_adds_coverage(sdl):
    schema = graphql.build_schema(sdl)
    seen = set()
    for document in covering_operations(schema):
        pairs, triples = covered(schema, [document])
        assert not pairs | triples <= seen, graphql.print_ast(document)
        seen |= pairs | triples


@pytest.mark.parametrize("sdl", ALL.values(), ids=list(ALL))
def test_mutations_have_one_root_field(sdl):
    schema = graphql.build_schema(sdl)
    for document in covering_operations(schema):
        operation, selections = root_fields(document)
        root = schema.mutation_type if operation == graphql.OperationType.MUTATION else schema.query_type
        assert all(isinstance(node, graphql.FieldNode) and node.name.value in root.fields for node in selections)
        if operation == graphql.OperationType.MUTATION:
            assert len(selections) == 1


@pytest.mark.parametrize("sdl", ALL.values(), ids=list(ALL))
def test_document_count_is_bounded(sdl):
    schema = graphql.build_schema(sdl)
    pairs, triples, _ = expected(schema)
    types = {type_name for type_name, _ in pairs}
    with_optional = {
        (type_name, name)
        for type_name, name, arg in triples
        if not graphql.is_required_argument(schema.type_map[type_name].fields[name].args[arg])
    }
    mutation_fields = len(schema.mutation_type.fields) if schema.mutation_type else 0
    assert len(printed(schema)) <= len(types) + len(with_optional) + mutation_fields


def test_basic():
    assert printed(BASIC) == normalized(
        '{ node(id: "") { id } search(term: "") { id } }',
        '{ search(term: "", limit: 10, kind: A) { id } }',
        '{ node(id: "") { id name parent { id } } }',
    )


def test_abstract_types_are_reached_through_inline_fragments():
    assert printed(ABSTRACT) == normalized(
        "{ thing { ... on Dog { name } } pet { name } }",
        "{ thing { ... on Dog { name barks owner { pets { name } } } } }",
        "{ thing { ... on Rock { weight } } }",
        "{ thing { ... on Dog { owner { pets(first: 0) { name } } } } }",
    )


def test_mutations():
    create = 'create(input: {name: "", tags: [], nested: {n: 0, f: 0.0}})'
    assert printed(MUTATIONS) == normalized(
        "{ a }",
        f"mutation {{ {create} {{ ok }} }}",
        'mutation { delete(id: "") }',
        'mutation { delete(id: "", force: false) }',
        f"mutation {{ {create} {{ ok item {{ id }} }} }}",
    )


def test_mutation_only():
    assert printed(MUTATION_ONLY) == normalized(
        "mutation { bump { value } }",
        "mutation { reset }",
        "mutation { bump(by: 0) { value } }",
        "mutation { bump { value history } }",
        "mutation { bump { history(last: 0) } }",
    )


def test_lists_and_defaults():
    assert printed(LISTS_AND_DEFAULTS) == normalized(
        "{ items(ids: [], flag: false) { id } }",
        "{ items(ids: [], tags: [], order: DESC, page: {size: 5}, ratio: 0.0, flag: false) { id } }",
        "{ items(ids: [], flag: false) { id children { id } } }",
        "{ items(ids: [], flag: false) { children(depth: 1) { id } } }",
    )


def test_unknown_custom_scalars():
    schema = graphql.build_schema(CUSTOM_SCALARS)
    assert expected(schema)[2] == {
        ("Query", "on"),
        ("Query", "filtered"),
        ("Query", "events", "after"),
        ("Query", "since", "range"),
        ("Query", "ok", "range"),
        ("Event", "at"),
        ("Event", "attendees", "since"),
    }
    assert printed(schema) == normalized(
        '{ events { id } since { id } ok(filter: {name: ""}) }',
        '{ since(day: "2020-01-01") { id } }',
        "{ events { id attendees } }",
        "{ events { attendees(first: 0) } }",
    )


def test_type_without_leaves_is_terminated_with_typename():
    assert printed(NO_LEAF) == normalized(
        "{ loop { __typename } only { __typename } }",
        "{ loop { next { __typename } } }",
    )


@pytest.mark.skipif(not ONE_OF_SUPPORTED, reason="`@oneOf` needs graphql-core >= 3.2.7")
def test_one_of_uses_first_usable_field():
    assert printed(ONE_OF) == normalized(
        '{ find(by: {id: ""}) }',
        '{ find(by: {id: ""}, alt: {by: {id: ""}}) }',
    )


def test_schema_from_introspection():
    schema = graphql.build_client_schema(graphql.introspection_from_schema(graphql.build_schema(LISTS_AND_DEFAULTS)))
    documents = list(covering_operations(schema))
    for document in documents:
        assert graphql.validate(schema, document) == [], graphql.print_ast(document)
    pairs, triples, _ = expected(schema)
    assert covered(schema, documents) == (pairs, triples)


@pytest.mark.parametrize(
    ("fields", "operations"),
    [
        (["delete"], ['mutation { delete(id: "") }', 'mutation { delete(id: "", force: false) }']),
        (["a"], ["{ a }"]),
        (("a", "delete"), ["{ a }", 'mutation { delete(id: "") }', 'mutation { delete(id: "", force: false) }']),
    ],
)
def test_fields(fields, operations):
    assert printed(MUTATIONS, fields=iter(fields)) == normalized(*operations)


@pytest.mark.parametrize("sdl", ALL.values(), ids=list(ALL))
def test_fields_restrict_coverage(sdl):
    schema = graphql.build_schema(sdl)
    root = schema.query_type or schema.mutation_type
    fields = list(root.fields)[:1]
    pairs, triples, _ = expected(schema, fields)
    assert covered(schema, covering_operations(schema, fields=fields)) == (pairs, triples)


@pytest.mark.parametrize(
    ("fields", "message"), [(["a", "x", "y"], "Unknown fields: x, y"), ([], "should not be empty")]
)
def test_invalid_fields(fields, message):
    with pytest.raises(ValueError, match=message):
        covering_operations(MUTATIONS, fields=fields)


def test_no_root_types():
    with pytest.raises(InvalidArgument, match="Query or Mutation type must be provided"):
        covering_operations("type A { a: Int }")

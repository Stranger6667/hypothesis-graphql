import graphql
import pytest
from hypothesis import HealthCheck, Phase, find, given, settings

from benchmarks._schemas import SCHEMAS, custom_scalars_for
from hypothesis_graphql import Mode, from_schema, mutations, queries

# Same response keys under different union members and interface implementations
MERGING = """
type Query { r: [R] n: N }
union R = A | B
interface N { id: ID child: T }
type A implements N { id: ID child: T x: Int other: T }
type B implements N { id: ID child: T x: String other: T on: Int }
type T { x: Int y: String t: T a: Int }
"""
# No response key conflicts, so every alias comes from the syntax variety
RICH = """
type Query { book(id: ID!): Book media(first: Int): [Media] node: Node search(term: String): [Media!] }
type Mutation { rename(id: ID!, title: String!): Book }
type Book implements Node { id: ID title: String author: Author cover: Image }
type Author implements Node { id: ID name: String books: [Book] }
type Image { path: String width: Int }
type Video { duration: Int preview: Image }
union Media = Image | Video
interface Node { id: ID }
"""
ALL = {**SCHEMAS, "merging": MERGING, "rich": RICH}
SETTINGS = {"suppress_health_check": list(HealthCheck), "deadline": None, "phases": [Phase.generate]}


def identity(document):
    return document


class Features(graphql.Visitor):
    def __init__(self):
        super().__init__()
        self.found = set()
        self.spreads = []

    def enter_field(self, node, *_):
        if node.alias:
            self.found.add("alias")
        if node.directives:
            self.found.add("field directive")

    def enter_inline_fragment(self, node, *_):
        if node.directives:
            self.found.add("fragment directive")

    def enter_fragment_spread(self, node, *_):
        self.spreads.append(node.name.value)
        if node.directives:
            self.found.add("fragment directive")

    def enter_fragment_definition(self, node, *_):
        self.found.add(f"fragment on {node.type_condition.name.value}")

    def enter_operation_definition(self, node, *_):
        if node.name:
            self.found.add("name")


def features(document):
    visitor = Features()
    graphql.visit(document, visitor)
    return visitor.found


def collect(strategy, examples):
    documents = []

    @given(strategy)
    @settings(max_examples=examples, **SETTINGS)
    def run(document):
        documents.append(document)

    run()
    return documents


@pytest.mark.parametrize("label", list(ALL))
def test_valid_and_round_trips(label):
    sdl = ALL[label]
    schema = graphql.build_schema(sdl)
    strategy = from_schema(sdl, custom_scalars=custom_scalars_for(sdl), syntax_variety=True, print_ast=identity)

    @given(strategy)
    @settings(max_examples=150, **SETTINGS)
    def run(document):
        assert graphql.validate(schema, document) == []
        printed = graphql.print_ast(document)
        parsed = graphql.parse(printed, no_location=True)
        assert graphql.print_ast(parsed) == printed
        operation, *definitions = document.definitions
        assert isinstance(operation, graphql.OperationDefinitionNode)
        names = [definition.name.value for definition in definitions]
        assert all(isinstance(definition, graphql.FragmentDefinitionNode) for definition in definitions)
        visitor = Features()
        graphql.visit(document, visitor)
        # Unique, and each one is spread exactly once
        assert sorted(visitor.spreads) == sorted(set(names))

    run()


def test_every_feature_is_generated_and_plain_queries_stay_common():
    documents = collect(from_schema(RICH, syntax_variety=True, print_ast=identity), 500)
    found = [features(document) for document in documents]
    seen = set.union(*found)
    # `Book` and `Media` fragments are hoisted sub-selections, `Image` and `Video` are hoisted inline fragments
    assert seen >= {"alias", "field directive", "fragment directive", "name", "fragment on Book", "fragment on Media"}
    assert seen & {"fragment on Image", "fragment on Video"}
    assert sum(not item for item in found) > 0.3 * len(found)
    printed = "\n".join(graphql.print_ast(document) for document in documents)
    for directive in ("@skip(if: true)", "@skip(if: false)", "@include(if: true)", "@include(if: false)"):
        assert directive in printed


@pytest.mark.parametrize("factory", [queries, mutations, from_schema])
def test_plain_by_default(factory):
    for document in collect(factory(RICH, print_ast=identity), 100):
        assert features(document) == set()
        assert len(document.definitions) == 1


# No `merging`: its smallest query may keep an alias that separates conflicting response keys
@pytest.mark.parametrize("label", ["rich", "recursive", "interface-union"])
def test_minimal_example_is_plain(label):
    sdl = ALL[label]
    strategy = from_schema(sdl, custom_scalars=custom_scalars_for(sdl), syntax_variety=True, print_ast=identity)
    assert features(find(strategy, lambda document: True, settings=settings(database=None))) == set()


def kinds(document):
    return {
        "fragment" if feature.startswith("fragment on") else "directive" if feature.endswith("directive") else feature
        for feature in features(document)
    }


def minimal(strategy, condition):
    return find(strategy, condition, settings=settings(database=None))


@pytest.mark.parametrize("kind", ["alias", "directive", "name", "fragment"])
def test_other_syntax_shrinks_away(kind):
    strategy = queries(RICH, syntax_variety=True, print_ast=identity)
    assert kinds(minimal(strategy, lambda document: kind in kinds(document))) == {kind}


class Fields(graphql.Visitor):
    count = 0

    def enter_field(self, *_):
        self.count += 1


def has_five_fields(document):
    visitor = Fields()
    graphql.visit(document, visitor)
    return visitor.count >= 5


def test_syntax_shrinks_away_from_large_queries():
    strategy = queries(RICH, syntax_variety=True, print_ast=identity)
    assert features(minimal(strategy, has_five_fields)) == set()


@pytest.mark.parametrize("factory", [queries, mutations, from_schema])
def test_negative_mode_stays_plain(factory):
    for document in collect(factory(RICH, syntax_variety=True, mode=Mode.NEGATIVE, print_ast=identity), 100):
        assert features(document) == set()
        assert len(document.definitions) == 1

# hypothesis-graphql

[![Build](https://github.com/Stranger6667/hypothesis-graphql/workflows/build/badge.svg)](https://github.com/Stranger6667/hypothesis-graphql/actions)
[![Coverage](https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master/graph/badge.svg)](https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master)
[![Version](https://img.shields.io/pypi/v/hypothesis-graphql.svg)](https://pypi.org/project/hypothesis-graphql/)
[![Python versions](https://img.shields.io/pypi/pyversions/hypothesis-graphql.svg)](https://pypi.org/project/hypothesis-graphql/)
[![Chat](https://img.shields.io/discord/938139740912369755)](https://discord.gg/VnxfdFmBUp)
[![License](https://img.shields.io/pypi/l/hypothesis-graphql.svg)](https://opensource.org/licenses/MIT)

<h4 align="center">
Generate queries matching your GraphQL schema, and use them to verify your backend implementation
</h4>

It is a Python library that provides a set of [Hypothesis](https://github.com/HypothesisWorks/hypothesis/tree/master/hypothesis-python) strategies that
let you write tests parametrized by a source of examples.
Generated queries have arbitrary depth and may contain any subset of GraphQL types defined in the input schema.
They expose edge cases in your code that are unlikely to be found otherwise.

[Schemathesis](https://github.com/schemathesis/schemathesis) provides a higher-level interface around this library and finds server crashes automatically.

## Usage

`hypothesis-graphql` provides the `from_schema` function, which takes a GraphQL schema and returns a Hypothesis strategy for
GraphQL queries matching the schema:

```python
from hypothesis import given
from hypothesis_graphql import from_schema
import requests

# Strings and `graphql.GraphQLSchema` are supported
SCHEMA = """
type Book {
  title: String
  author: Author
}

type Author {
  name: String
  books: [Book]
}

type Query {
  getBooks: [Book]
  getAuthors: [Author]
}

type Mutation {
  addBook(title: String!, author: String!): Book!
  addAuthor(name: String!): Author!
}
"""


@given(from_schema(SCHEMA))
def test_graphql(query):
    # Will generate samples like these:
    #
    # {
    #   getBooks {
    #     title
    #   }
    # }
    #
    # mutation {
    #   addBook(title: "H4Z\u7869", author: "\u00d2"){
    #     title
    #   }
    # }
    response = requests.post("http://127.0.0.1/graphql", json={"query": query})
    assert response.status_code == 200
    assert response.json().get("errors") is None
```

It is also possible to generate queries or mutations separately with `hypothesis_graphql.queries` and `hypothesis_graphql.mutations`.

### Customization

To restrict the set of fields in generated operations use the `fields` argument:

```python
@given(from_schema(SCHEMA, fields=["getAuthors"]))
def test_graphql(query):
    # Only `getAuthors` will be generated
    ...
```

It is also possible to generate custom scalars. For example, `Date`:

```python
from hypothesis import strategies as st, given
from hypothesis_graphql import from_schema, nodes

SCHEMA = """
scalar Date

type Query {
  getByDate(created: Date!): Int
}
"""


@given(
    from_schema(
        SCHEMA,
        custom_scalars={
            # Standard scalars work out of the box, for custom ones you need
            # to pass custom strategies that generate proper AST nodes
            "Date": st.dates().map(nodes.String)
        },
    )
)
def test_graphql(query):
    # Example:
    #
    #  { getByDate(created: "2000-01-01") }
    #
    ...
```

The `hypothesis_graphql.nodes` module includes a few helpers to generate various node types:

- `String` -> `graphql.StringValueNode`
- `Float` -> `graphql.FloatValueNode`
- `Int` -> `graphql.IntValueNode`
- `Object` -> `graphql.ObjectValueNode`
- `List` -> `graphql.ListValueNode`
- `Boolean` -> `graphql.BooleanValueNode`
- `Enum` -> `graphql.EnumValueNode`
- `Null` -> `graphql.NullValueNode` (a constant, not a function)

They exist because classes like `graphql.StringValueNode` can't be directly used in `map` calls due to kwarg-only arguments.

## License

The code in this project is licensed under [MIT license](https://opensource.org/licenses/MIT).
By contributing to `hypothesis-graphql`, you agree that your contributions will be licensed under its MIT license.

# hypothesis-graphql

[![Build](https://github.com/Stranger6667/hypothesis-graphql/workflows/build/badge.svg)](https://github.com/Stranger6667/hypothesis-graphql/actions)
[![Coverage](https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master/graph/badge.svg)](https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master)
[![Version](https://img.shields.io/pypi/v/hypothesis-graphql.svg)](https://pypi.org/project/hypothesis-graphql/)
[![Python versions](https://img.shields.io/pypi/pyversions/hypothesis-graphql.svg)](https://pypi.org/project/hypothesis-graphql/)
[![Chat](https://img.shields.io/discord/938139740912369755)](https://discord.gg/VnxfdFmBUp)
[![License](https://img.shields.io/pypi/l/hypothesis-graphql.svg)](https://opensource.org/licenses/MIT)

Hypothesis strategies for GraphQL operations. Allows you to generate arbitrary GraphQL queries for the given schema.
It starts with simple examples and iteratively goes to more complex ones.

For web API testing, [Schemathesis](https://github.com/schemathesis/schemathesis) provides a higher-level wrapper and can
detect internal server errors.

## Usage

`hypothesis_graphql` exposes the `from_schema` function, which takes a GraphQL schema and returns a Hypothesis strategy for
defined queries and mutations:

```python
from hypothesis import given
from hypothesis_graphql import from_schema

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
    ...
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

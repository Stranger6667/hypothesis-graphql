# hypothesis-graphql

[![Build](https://github.com/Stranger6667/hypothesis-graphql/workflows/build/badge.svg)](https://github.com/Stranger6667/hypothesis-graphql/actions)
[![Coverage](https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master/graph/badge.svg)](https://codecov.io/gh/Stranger6667/hypothesis-graphql/branch/master)
[![Version](https://img.shields.io/pypi/v/hypothesis-graphql.svg)](https://pypi.org/project/hypothesis-graphql/)
[![Python versions](https://img.shields.io/pypi/pyversions/hypothesis-graphql.svg)](https://pypi.org/project/hypothesis-graphql/)
[![Chat](https://img.shields.io/discord/938139740912369755)](https://discord.gg/R9ASRAmHnA)
[![License](https://img.shields.io/pypi/l/hypothesis-graphql.svg)](https://opensource.org/licenses/MIT)

<h4 align="center">
Generate GraphQL queries from your schema and test your server with them
</h4>

`hypothesis-graphql` gives you [Hypothesis](https://github.com/HypothesisWorks/hypothesis/tree/master/hypothesis-python) strategies that build queries and mutations from a GraphQL schema.
Each generated operation selects a random subset of fields at random depth and fills arguments with random values.

For a ready-made tool, try [Schemathesis](https://github.com/schemathesis/schemathesis): it runs on top of this library and reports server crashes without any test code.

## Usage

`from_schema` takes a schema and returns a strategy that yields queries and mutations as strings:

```python
from hypothesis import given
from hypothesis_graphql import from_schema
import requests

# A schema string or a `graphql.GraphQLSchema` instance
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
    # Generates operations like:
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

To generate only one kind of operation, use `hypothesis_graphql.queries` or `hypothesis_graphql.mutations`.

### Customization

Pass `fields` to limit which root fields appear in generated operations:

```python
@given(from_schema(SCHEMA, fields=["getAuthors"]))
def test_graphql(query):
    # Only `getAuthors` will be generated
    ...
```

Two arguments control generated strings:

- `allow_x00` (default `True`): set it to `False` to keep `\x00` out of strings. Some web servers reject requests that contain it.
- `codec` (default `utf-8`): generated strings only contain characters this codec can encode. Use `"ascii"` to stay in the ASCII range.

```python
@given(from_schema(SCHEMA, allow_x00=False, codec="ascii"))
def test_graphql(query):
    assert "\0" not in query
    query.encode("ascii")
```

Set `allow_null=False` to keep `null` out of argument values, including nested input fields and list items.

Built-in scalars (`Int`, `Float`, `String`, `ID`, `Boolean`) work out of the box.
For a custom scalar such as `Date`, pass a strategy that generates AST nodes for it:

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
        custom_scalars={"Date": st.dates().map(nodes.String)},
    )
)
def test_graphql(query):
    # Example:
    #
    #  { getByDate(created: "2000-01-01") }
    #
    ...
```

Without a strategy, `hypothesis-graphql` skips optional arguments of that type and raises `hypothesis.errors.InvalidArgument` if a required argument uses it.

`hypothesis_graphql.nodes` has helpers that build value nodes:

- `String` -> `graphql.StringValueNode` (converts the value with `str()`)
- `Float` -> `graphql.FloatValueNode`
- `Int` -> `graphql.IntValueNode`
- `Object` -> `graphql.ObjectValueNode`
- `List` -> `graphql.ListValueNode`
- `Boolean` -> `graphql.BooleanValueNode`
- `Enum` -> `graphql.EnumValueNode`
- `Null` -> `graphql.NullValueNode` (a constant, not a function)

Use them in `map` calls: `graphql.StringValueNode` and friends accept keyword arguments only.

### Negative Testing

Pass `mode=Mode.NEGATIVE` to generate operations your server must reject:

```python
from hypothesis import given
from hypothesis_graphql import queries, Mode
import requests

SCHEMA = """
type Query {
    getUser(id: Int!, name: String!): User
}

type User {
    id: Int!
    name: String!
}
"""


@given(queries(SCHEMA, mode=Mode.NEGATIVE))
def test_server_rejects_invalid_queries(query):
    # Each query violates the schema in exactly one of these ways:
    # - a value of the wrong type (a string for an `Int`)
    # - a missing required argument
    # - an `Int` outside the 32-bit range
    # - `null` for a non-null argument
    # - an unknown enum value
    # - an input object without one of its required fields
    response = requests.post("http://127.0.0.1/graphql", json={"query": query})

    # The server must answer with an error status or an `errors` list
    if response.status_code == 200:
        assert "errors" in response.json()
```

`queries`, `mutations`, and `from_schema` all accept `mode`.
If no argument in the schema allows any of these violations, negative mode raises `InvalidArgument`.

## License

`hypothesis-graphql` is available under the [MIT license](https://opensource.org/licenses/MIT).
By contributing, you agree to license your contributions under it.

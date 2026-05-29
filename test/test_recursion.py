import graphql
from hypothesis import HealthCheck, Phase, given, settings

from hypothesis_graphql import from_schema

RECURSIVE = """
type Query {
  node(id: ID!): Node
  roots: [Node!]
}

type Node {
  id: ID!
  name: String
  parent: Node
  children: [Node!]
  related(first: Int): [Node!]
}
"""

SCHEMA = graphql.build_schema(RECURSIVE)


@settings(max_examples=300, suppress_health_check=list(HealthCheck), deadline=None, phases=[Phase.generate])
@given(query=from_schema(RECURSIVE))
def test_recursive_queries_terminate_and_validate(query):
    errors = graphql.validate(SCHEMA, graphql.parse(query))
    assert not errors, query

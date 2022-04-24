import attr
import graphql


@attr.s(slots=True)
class Context:
    """The common context for query generation."""

    schema: graphql.GraphQLSchema = attr.ib()

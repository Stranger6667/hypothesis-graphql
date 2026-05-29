from collections.abc import Callable

import graphql
from hypothesis import strategies as st

# Leaf nodes, that don't have children
ScalarValueNode = graphql.IntValueNode | graphql.FloatValueNode | graphql.StringValueNode | graphql.BooleanValueNode
InputTypeNode = ScalarValueNode | graphql.EnumValueNode | graphql.ListValueNode | graphql.ObjectValueNode
Field = graphql.GraphQLField | graphql.GraphQLInputField
InterfaceOrObject = graphql.GraphQLObjectType | graphql.GraphQLInterfaceType
SelectionNodes = list[graphql.SelectionNode]
AstPrinter = Callable[[graphql.Node], str]
CustomScalarStrategies = dict[str, st.SearchStrategy[graphql.ValueNode]]

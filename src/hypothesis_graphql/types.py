from typing import List, Union

import graphql

# Leaf nodes, that don't have children
ScalarValueNode = Union[graphql.IntValueNode, graphql.FloatValueNode, graphql.StringValueNode, graphql.BooleanValueNode]
InputTypeNode = Union[ScalarValueNode, graphql.EnumValueNode, graphql.ListValueNode, graphql.ObjectValueNode]
Field = Union[graphql.GraphQLField, graphql.GraphQLInputField]
InterfaceOrObject = Union[graphql.GraphQLObjectType, graphql.GraphQLInterfaceType]
SelectionNodes = List[graphql.SelectionNode]

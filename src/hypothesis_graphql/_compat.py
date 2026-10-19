import graphql

# `graphql-core` 3.1 only visits lists as AST node sequences, 3.3 only tuples
ast_sequence = list if graphql.version_info < (3, 2) else tuple

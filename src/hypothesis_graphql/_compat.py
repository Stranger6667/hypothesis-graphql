from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, TypeVar

import graphql

T = TypeVar("T")

if TYPE_CHECKING:
    # Typed as `tuple`: 3.3 annotates AST node sequences as tuples, 3.1/3.2 accept any value
    def ast_sequence(items: Iterable[T] = (), /) -> tuple[T, ...]: ...

else:
    # `graphql-core` 3.1 only visits lists as AST node sequences, 3.3 only tuples
    ast_sequence = list if graphql.version_info < (3, 2) else tuple

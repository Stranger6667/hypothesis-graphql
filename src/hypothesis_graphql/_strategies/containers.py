from typing import List, Tuple, TypeVar

T = TypeVar("T")


def flatten(items: Tuple[List[T], T]) -> List[T]:
    output = items[0]
    output.extend(items[1:])
    return output

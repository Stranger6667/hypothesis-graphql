from typing import TYPE_CHECKING

from hypothesis import strategies as st

if TYPE_CHECKING:
    from hypothesis.internal.conjecture.data import ConjectureData


class _WeightedBoolean(st.SearchStrategy):
    def __init__(self, p: float) -> None:
        super().__init__()
        self.p = p

    def do_draw(self, data: "ConjectureData") -> bool:
        return data.draw_boolean(self.p)


def weighted_boolean(p: float) -> st.SearchStrategy:
    return _WeightedBoolean(p)

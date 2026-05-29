from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st

_PROFILE = {
    "phases": [Phase.generate],
    "database": None,
    "deadline": None,
    "derandomize": True,
    "suppress_health_check": list(HealthCheck),
}


def drive(strategy: st.SearchStrategy, examples: int) -> None:
    @settings(max_examples=examples, **_PROFILE)
    @given(strategy)
    def _inner(_value: object) -> None:
        pass

    _inner()


def collect(strategy: st.SearchStrategy[str], examples: int) -> list[str]:
    out: list[str] = []

    @settings(max_examples=examples, **_PROFILE)
    @given(strategy)
    def _inner(value: str) -> None:
        out.append(value)

    _inner()
    return out

import graphql
import pytest

from hypothesis_graphql import Mode, from_schema

from ._generate import drive
from ._schemas import SCHEMAS, custom_scalars_for

POSITIVE_EXAMPLES = 5
NEGATIVE_EXAMPLES = 3


@pytest.fixture(scope="module")
def prepared():
    return {label: (sdl, custom_scalars_for(sdl)) for label, sdl in SCHEMAS.items()}


@pytest.mark.parametrize("label", list(SCHEMAS))
def test_parse(benchmark, label):
    sdl = SCHEMAS[label]
    benchmark(graphql.build_schema, sdl)


@pytest.mark.parametrize("label", list(SCHEMAS))
def test_build(benchmark, prepared, label):
    sdl, custom_scalars = prepared[label]

    def setup():
        # A new schema object per round, as strategies are cached per schema
        return (graphql.build_schema(sdl),), {"custom_scalars": custom_scalars}

    benchmark.pedantic(from_schema, setup=setup)


@pytest.mark.parametrize("label", list(SCHEMAS))
def test_generate_positive(benchmark, prepared, label):
    sdl, custom_scalars = prepared[label]
    strategy = from_schema(sdl, custom_scalars=custom_scalars)
    benchmark(drive, strategy, POSITIVE_EXAMPLES)


@pytest.mark.parametrize("label", list(SCHEMAS))
def test_generate_negative(benchmark, prepared, label):
    sdl, custom_scalars = prepared[label]
    strategy = from_schema(sdl, custom_scalars=custom_scalars, mode=Mode.NEGATIVE)
    benchmark(drive, strategy, NEGATIVE_EXAMPLES)

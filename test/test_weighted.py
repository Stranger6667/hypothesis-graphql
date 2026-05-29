from hypothesis import find, given, settings

from hypothesis_graphql._strategies.weighted import weighted_boolean


@given(weighted_boolean(0.99))
@settings(max_examples=50)
def test_weighted_boolean_is_bool(value):
    assert isinstance(value, bool)


def test_weighted_boolean_shrinks_to_false():
    assert find(weighted_boolean(0.99), lambda b: True) is False

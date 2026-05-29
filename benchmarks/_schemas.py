import json
import pathlib
from typing import Dict, Optional

import graphql
from hypothesis import strategies as st

from hypothesis_graphql import nodes
from hypothesis_graphql._strategies.strategy import BUILT_IN_SCALAR_TYPE_NAMES

_CORPUS_PATH = pathlib.Path(__file__).parent.parent / "test" / "corpus-api-guru-catalog.json"

RECURSIVE_SCHEMA = """
type Query {
  node(id: ID!): Node
  search(term: String!, limit: Int, kind: Kind): [Node!]
}

type Node {
  id: ID!
  name: String
  rank: Int
  parent: Node
  children(first: Int): [Node!]
}

enum Kind { A B C }
"""

_CORPUS_SELECTION = {
    "flat-small": "Planets",
    "flat-medium": "React Finland",
    "interface-union": "TMDB",
    "input-heavy": "MongoDB Northwind demo",
    "large": "MusicBrainz",
}

PLACEHOLDER_STRATEGY = st.just("placeholder").map(nodes.String)


def _load_corpus() -> Dict[str, str]:
    with open(_CORPUS_PATH) as fd:
        return json.load(fd)


def custom_scalars_for(schema: str) -> Optional[Dict[str, st.SearchStrategy]]:
    parsed = graphql.build_schema(schema)
    custom = {
        name: PLACEHOLDER_STRATEGY
        for name, type_ in parsed.type_map.items()
        if name not in BUILT_IN_SCALAR_TYPE_NAMES and isinstance(type_, graphql.GraphQLScalarType)
    }
    return custom or None


def load_schemas() -> Dict[str, str]:
    corpus = _load_corpus()
    schemas = {"recursive": RECURSIVE_SCHEMA}
    for label, name in _CORPUS_SELECTION.items():
        if name in corpus:
            schemas[label] = corpus[name]
    return schemas


SCHEMAS = load_schemas()

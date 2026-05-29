import collections
import sys
import warnings

import graphql

from hypothesis_graphql import Mode, from_schema

from ._generate import collect
from ._schemas import SCHEMAS, custom_scalars_for

warnings.filterwarnings("ignore")


def _children(node: graphql.Node):
    for key in node.keys:
        child = getattr(node, key, None)
        if isinstance(child, graphql.Node):
            yield child
        elif isinstance(child, (list, tuple)):
            yield from (item for item in child if isinstance(item, graphql.Node))


def _annotate(node: graphql.Node, depth: int, out: dict[int, int]) -> None:
    if isinstance(node, graphql.FieldNode):
        depth += 1
    out[id(node)] = depth
    for child in _children(node):
        _annotate(child, depth, out)


def leaf_depths(query: str) -> list[int]:
    document = graphql.parse(query)
    depths: dict[int, int] = {}
    _annotate(document, 0, depths)
    leaves = []

    def visit(node: graphql.Node) -> None:
        if isinstance(node, graphql.FieldNode) and node.selection_set is None:
            leaves.append(depths[id(node)])
        for child in _children(node):
            visit(child)

    visit(document)
    return leaves


def violation_depths(query: str, schema: graphql.GraphQLSchema) -> list[int]:
    document = graphql.parse(query)
    depths: dict[int, int] = {}
    _annotate(document, 0, depths)
    out = []
    for error in graphql.validate(schema, document):
        node_depths = [depths[id(n)] for n in (error.nodes or []) if id(n) in depths]
        if node_depths:
            out.append(min(node_depths))
    return out


def _histogram(values: list[int], width: int = 40) -> str:
    if not values:
        return "  (none)"
    counts = collections.Counter(values)
    peak = max(counts.values())
    lines = []
    for depth in range(min(counts), max(counts) + 1):
        count = counts.get(depth, 0)
        bar = "#" * round(width * count / peak)
        lines.append(f"  depth {depth:2}: {bar:<{width}} {count}")
    return "\n".join(lines)


def _report(label: str, mode: Mode, depths: list[int]) -> None:
    print(f"\n{label} [{mode.name}]  samples={len(depths)}")
    if depths:
        ordered = sorted(depths)
        mean = sum(depths) / len(depths)
        print(f"  min={ordered[0]} max={ordered[-1]} mean={mean:.2f} p50={ordered[len(ordered) // 2]}")
    print(_histogram(depths))


def run(examples: int) -> None:
    for label, sdl in SCHEMAS.items():
        custom_scalars = custom_scalars_for(sdl)
        schema = graphql.build_schema(sdl)

        positive = from_schema(sdl, custom_scalars=custom_scalars)
        leaves: list[int] = []
        for query in collect(positive, examples):
            leaves.extend(leaf_depths(query))
        _report(label, Mode.POSITIVE, leaves)

        sites: list[int] = []
        try:
            negative = from_schema(sdl, custom_scalars=custom_scalars, mode=Mode.NEGATIVE)
            for query in collect(negative, examples):
                sites.extend(violation_depths(query, schema))
        except Exception as exc:  # noqa: BLE001
            print(f"\n{label} [NEGATIVE]  skipped: {type(exc).__name__}")
            continue
        _report(label, Mode.NEGATIVE, sites)


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 50)

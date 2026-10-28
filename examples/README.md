# Minimal input

`small_edges.csv` contains three four-node cliques and three inter-clique links.
`small_nodes.csv` also includes an isolate. It is an inspectable fixture, not a
performance benchmark.

```bash
uv run --no-sync largegraph analyze examples/small_edges.csv \
  --nodes-file examples/small_nodes.csv --truth examples/small_nodes.csv \
  --output runs/fixture --work-dir work/fixture --hierarchy-targets 4 8 --images \
  --max-groups 8 --pixels 256 --reference --memory 256MB
```

The manifest must report 13 nodes, 21 edges and one isolate. The exact partition
recovered by a heuristic is not prescribed; validate its agreement with the
provided planted labels and inspect all three views.

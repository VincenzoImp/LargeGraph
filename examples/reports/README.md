# Interactive examples

Download an HTML file and open it in a browser. It contains its aggregate data,
styles and JavaScript and works offline without a GPU or Python installation.

- [Full-scale synthetic example](full/index.html): 5M nodes, 500M edges, all 512
  detected groups and three coarser cuts. Counts use the entire canonical graph.
- [SNAP Facebook example](facebook/index.html): 4,039 nodes, 88,234 edges, bounded
  Leiden partition. See the [source and comparison](../../docs/comparisons.md).

These are portable aggregate reports. Original-node queries require a local
analysis and its index via `largegraph-viz serve`. Layout/hierarchy are
descriptive; captions disclose link filtering and display conventions.

The release also attaches standalone HTML files for convenient download.

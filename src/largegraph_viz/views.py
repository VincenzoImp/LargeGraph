"""Bounded layouts and quantitative node-link, matrix and raster views."""

from __future__ import annotations

import hashlib
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LogNorm, TwoSlopeNorm

from .aggregate import display_reduction
from .layout import layout, selected_edges
from .numerics import matrix_arrays, raster_edges, raster_points
from .runtime import Monitor, Resources, environment, write_json

BACKGROUND = "#101923"
FOREGROUND = "#e7edf2"
MUTED = "#9cabb8"


def style():
    return matplotlib.rc_context(
        {
            "figure.facecolor": BACKGROUND,
            "axes.facecolor": BACKGROUND,
            "savefig.facecolor": BACKGROUND,
            "text.color": FOREGROUND,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.edgecolor": "#33414e",
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def save_figure(fig, output: Path, name: str):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(output / f"{name}.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def export_display(output: Path, reduction, coords=None):
    import csv

    np.savez_compressed(
        output / "display_data.npz",
        weights=reduction["weights"],
        node_count=reduction["sizes"],
        degree_volume=reduction["volumes"],
        community_to_display=reduction["mapping"],
    )
    with (output / "display_nodes.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["display_id", "label", "node_count", "degree_volume", "artificial", "x", "y"]
        )
        for i, name in enumerate(reduction["names"]):
            xy = coords[i] if coords is not None else ["", ""]
            writer.writerow(
                [
                    i,
                    name,
                    int(reduction["sizes"][i]),
                    int(reduction["volumes"][i]),
                    reduction["artificial_other"] and i == len(reduction["names"]) - 1,
                    *xy,
                ]
            )
    with (output / "display_edges.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["source", "target", "weight"])
        for a, b in zip(*np.nonzero(reduction["weights"]), strict=True):
            writer.writerow([int(a), int(b), int(reduction["weights"][a, b])])


def render_community(
    quotient: Path,
    output: Path,
    resources: Resources,
    max_groups=128,
    max_edges=1200,
    seed=42,
    layout_engine="auto",
):
    output.mkdir(parents=True, exist_ok=True)
    with style(), Monitor(output) as monitor:
        reduction = display_reduction(quotient, max_groups, resources)
        weights, sizes = reduction["weights"], reduction["sizes"]
        coords, engine = layout(weights, seed, layout_engine)
        a, b, w, filtering = selected_edges(weights, max_edges)
        fig, ax = plt.subplots(figsize=(13, 10))
        widths = 0.2 + 3 * np.log1p(w.astype(float)) / max(
            1, float(np.log1p(w.astype(float)).max(initial=0))
        )
        ax.add_collection(
            LineCollection(
                coords[np.column_stack([a, b])],
                linewidths=widths,
                colors="#829bae",
                alpha=0.32,
                zorder=1,
            )
        )
        hues = np.array(
            [
                int(hashlib.sha256(name.encode()).hexdigest()[:12], 16) / 16**12
                for name in reduction["names"]
            ]
        )
        rgb = matplotlib.colors.hsv_to_rgb(
            np.column_stack([hues, np.full(len(hues), 0.65), np.full(len(hues), 0.95)])
        )
        colors = np.column_stack([rgb, np.ones(len(hues))])
        if reduction["artificial_other"]:
            colors[-1] = matplotlib.colors.to_rgba("#9099a2")
        # Area is proportional to group size. No additive size offset.
        max_marker_area = min(1800, max(80, 24000 / len(sizes)))
        areas = sizes.astype(float) / max(1, int(sizes.max())) * max_marker_area
        ax.scatter(*coords.T, s=areas, c=colors, edgecolors="#ecf0f5", linewidths=0.5, zorder=2)
        for i in range(min(12, len(sizes)) if len(sizes) <= 64 else 0):
            ax.annotate(
                reduction["names"][i],
                coords[i],
                xytext=(6, 6),
                textcoords="offset points",
                fontsize=9,
            )
        if reduction["artificial_other"]:
            ax.annotate(
                "Other (artificial)",
                coords[-1],
                xytext=(6, -12),
                textcoords="offset points",
                color=MUTED,
            )
        ax.autoscale()
        ax.margins(0.12)
        ax.set_aspect("equal", adjustable="datalim")
        ax.axis("off")
        reference_sizes = np.unique(
            np.maximum(1, (sizes.max() * np.array([0.25, 0.5, 1])).astype(int))
        )
        handles = [
            ax.scatter(
                [],
                [],
                s=float(value) / int(sizes.max()) * max_marker_area,
                color="#a4b2be",
                edgecolors=FOREGROUND,
                linewidths=0.5,
                label=f"{int(value):,}",
            )
            for value in reference_sizes
        ]
        ax.legend(
            handles=handles,
            title="Nodes per group",
            loc="lower right",
            labelcolor=FOREGROUND,
            facecolor=BACKGROUND,
            edgecolor="#33414e",
            framealpha=0.9,
            fontsize=8,
            title_fontsize=9,
            labelspacing=1.0,
        )
        ax.set_title("Community structure", loc="left", fontsize=25, pad=24, weight="bold")
        fig.text(
            0.13,
            0.87,
            f"{int(sizes.sum()):,} nodes · {int(weights.sum()):,} edges · {reduction['all_communities']:,} detected groups",
            color=MUTED,
        )
        fig.text(
            0.13,
            0.055,
            f"Area ∝ nodes · line width ∝ log(1 + edge count) · omitted external weight: {filtering['omitted_external_edge_weight']:,}\n"
            "Aggregated topology. Distances are layout-dependent; colors identify display groups.",
            color=MUTED,
            fontsize=9,
        )
        save_figure(fig, output, "communities")
        export_display(output, reduction, coords)
    write_json(
        output / "manifest.json",
        {
            "view": "community",
            "quotient": str(quotient.resolve()),
            "max_groups": max_groups,
            "seed": seed,
            "layout": engine,
            "layout_edge_weight": "log1p(raw edge count)",
            "max_marker_area_points_squared": max_marker_area,
            "color_mapping": "SHA-256(display name) to HSV hue, independent of group size",
            "filtering": filtering,
            "artificial_other": reduction["artificial_other"],
            "metrics": monitor.stats,
            "environment": environment(),
        },
    )
    return output


def render_matrix(quotient: Path, output: Path, resources: Resources, max_groups=128):
    output.mkdir(parents=True, exist_ok=True)
    with style(), Monitor(output) as monitor:
        reduction = display_reduction(quotient, max_groups, resources)
        raw, expected, enrichment, density = matrix_arrays(reduction)
        fig, axes = plt.subplots(1, 3, figsize=(19, 7))
        fig.subplots_adjust(left=0.06, right=0.96, top=0.82, bottom=0.20, wspace=0.65)
        max_raw = max(2, int(raw.max(initial=0)))
        images = [
            axes[0].imshow(
                np.ma.masked_equal(raw, 0), cmap="magma", norm=LogNorm(vmin=1, vmax=max_raw)
            ),
            axes[1].imshow(
                density, cmap="viridis", vmin=0, vmax=max(1e-9, float(density.max(initial=0)))
            ),
            axes[2].imshow(
                enrichment,
                cmap="RdBu_r",
                norm=TwoSlopeNorm(
                    vmin=-max(1, float(abs(enrichment).max(initial=0))),
                    vcenter=0,
                    vmax=max(1, float(abs(enrichment).max(initial=0))),
                ),
            ),
        ]
        titles = ["Adjacency mass · log scale", "Edge density", "Degree-adjusted connectivity"]
        bars = [
            "Adjacency entries (diagonal counts twice)",
            "Observed / possible edges",
            "log₂((observed + 1) / (expected + 1))",
        ]
        for ax, image, title, bar in zip(axes, images, titles, bars, strict=True):
            ax.set_title(title, pad=14)
            if len(raw) <= 24:
                ax.set_xticks(range(len(raw)), reduction["names"], rotation=90, fontsize=7)
                ax.set_yticks(range(len(raw)), reduction["names"], fontsize=7)
            else:
                ax.set_xlabel("Display group (ordered by node count)")
                ax.set_ylabel("Display group")
            fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label=bar)
        fig.suptitle(
            "Connectivity beyond the layout", fontsize=24, x=0.07, ha="left", y=0.98, weight="bold"
        )
        fig.text(
            0.07,
            0.02,
            "All edges contribute. Expected adjacency uses the degree-volume configuration null; enrichment is descriptive, not a p-value.\n"
            + (
                "The final group is an artificial collection of smaller communities."
                if reduction["artificial_other"]
                else "No display groups have been merged."
            ),
            color=MUTED,
            fontsize=9,
        )
        save_figure(fig, output, "matrix")
        export_display(output, reduction)
        np.savez_compressed(
            output / "matrices.npz",
            adjacency=raw,
            expected=expected,
            enrichment=enrichment,
            density=density,
        )
    write_json(
        output / "manifest.json",
        {
            "view": "matrix",
            "quotient": str(quotient.resolve()),
            "max_groups": max_groups,
            "artificial_other": reduction["artificial_other"],
            "metrics": monitor.stats,
            "environment": environment(),
            "normalization": "A symmetric, A_ii=2 internal edges; E_ij=volume_i volume_j/(2m); stabilized ratio has pseudocount 1",
        },
    )
    return output


def render_density(
    quotient: Path,
    output: Path,
    resources: Resources,
    levels=(32, 128),
    pixels=1024,
    max_edges=4000,
    seed=42,
    layout_engine="auto",
):
    if not 64 <= pixels <= 4096:
        raise ValueError("pixels must be between 64 and 4096")
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    with style(), Monitor(output) as monitor:
        for level in sorted(set(levels)):
            reduction = display_reduction(quotient, level, resources)
            coords, engine = layout(reduction["weights"], seed, layout_engine)
            minima, maxima = coords.min(axis=0), coords.max(axis=0)
            span = np.maximum(maxima - minima, 1)
            minima, maxima = minima - 0.08 * span, maxima + 0.08 * span
            bounds = [float(minima[0]), float(maxima[0]), float(minima[1]), float(maxima[1])]
            node_grid = raster_points(coords, reduction["sizes"], pixels, bounds)
            if int(node_grid.sum()) != int(reduction["sizes"].sum()):
                raise RuntimeError("Raster node mass is not conserved")
            a, b, w, filtering = selected_edges(reduction["weights"], max_edges)
            edge_grid = raster_edges(coords, a, b, w, pixels, bounds)
            np.save(output / f"node_counts_{level}.npy", node_grid)
            np.save(output / f"edge_weight_{level}.npy", edge_grid)
            # Smoothing is solely a display operation, never used for reported counts.
            from scipy.ndimage import gaussian_filter

            node_field = gaussian_filter(node_grid.astype(float), sigma=max(1, pixels / 170))
            edge_field = gaussian_filter(edge_grid.astype(float), sigma=max(0.5, pixels / 1400))
            fig, axes = plt.subplots(1, 2, figsize=(15, 7))
            for ax, field, title, cmap in zip(
                axes,
                [node_field, edge_field],
                ["Node mass at group positions", "Connections between display groups"],
                ["magma", "cividis"],
                strict=True,
            ):
                positive = field[field > 0]
                norm = (
                    LogNorm(
                        vmin=max(1e-9, float(positive.max()) * 1e-4),
                        vmax=max(1e-8, float(positive.max())),
                    )
                    if len(positive)
                    else None
                )
                image = ax.imshow(
                    np.ma.masked_less(field, norm.vmin if norm else 1e-12),
                    origin="lower",
                    cmap=cmap,
                    norm=norm,
                    extent=bounds,
                )
                ax.axis("off")
                ax.set_title(title, pad=12, color=MUTED)
                fig.colorbar(
                    image, ax=ax, fraction=0.03, pad=0.01, label="Smoothed mass · log scale"
                )
            fig.suptitle(
                f"A multiscale map · cap {level} groups",
                fontsize=24,
                x=0.12,
                ha="left",
                weight="bold",
            )
            fig.text(
                0.12,
                0.04,
                f"Aggregated layout · {int(reduction['sizes'].sum()):,} nodes represented · {len(coords)} display groups\n"
                f"Node mass is exact; smoothing is visual. Edge layer excludes internal edges and {filtering['omitted_external_edge_weight']:,} filtered external edges.\n"
                "Coordinates and distances are layout-dependent. Panels at different scales are laid out independently.",
                color=MUTED,
                fontsize=9,
            )
            save_figure(fig, output, f"density_{level}")
            subdir = output / f"level_{level}"
            subdir.mkdir(exist_ok=True)
            export_display(subdir, reduction, coords)
            reports.append(
                {
                    "level": level,
                    "groups": len(coords),
                    "bounds": bounds,
                    "layout": engine,
                    "filtering": filtering,
                    "node_mass": int(node_grid.sum()),
                    "artificial_other": reduction["artificial_other"],
                }
            )
            del node_grid, edge_grid, node_field, edge_field
    write_json(
        output / "manifest.json",
        {
            "view": "density",
            "quotient": str(quotient.resolve()),
            "levels": reports,
            "pixels": pixels,
            "seed": seed,
            "kind": "aggregated-topology-not-full-node-layout",
            "metrics": monitor.stats,
            "edge_raster_semantics": "Each displayed pair contributes its raw edge count once per traversed pixel. Summing pixels is not the number of graph edges.",
            "environment": environment(),
        },
    )
    return output


def render_coordinates(
    coordinate_file: Path, prepared: Path, output: Path, resources: Resources, pixels=1024
):
    """Rasterize supplied x/y values in batches; require one row per compact node ID.

    Coordinates must be a NumPy N x 2 array in compact node order. There is no
    invented interpolation and no full in-memory coordinate copy.
    """
    from .runtime import fingerprint, read_json

    if not 64 <= pixels <= 4096:
        raise ValueError("pixels must be between 64 and 4096")
    output.mkdir(parents=True, exist_ok=True)
    with style(), Monitor(output) as monitor:
        xy = np.load(coordinate_file, mmap_mode="r")
        n = read_json(prepared / "manifest.json")["nodes"]
        if (
            xy.shape != (n, 2)
            or not np.issubdtype(xy.dtype, np.number)
            or np.issubdtype(xy.dtype, np.complexfloating)
        ):
            raise ValueError("Coordinates must be a numeric N x 2 .npy array in compact node order")
        minima, maxima = np.full(2, np.inf), np.full(2, -np.inf)
        for start in range(0, n, resources.batch_rows):
            block = xy[start : start + resources.batch_rows]
            if not np.isfinite(block).all():
                raise ValueError("Coordinates contain NaN or infinity")
            minima = np.minimum(minima, block.min(axis=0))
            maxima = np.maximum(maxima, block.max(axis=0))
        span = np.maximum(maxima - minima, 1)
        if not np.isfinite(span).all():
            raise ValueError("Coordinate range is too wide for finite float arithmetic")
        minima, maxima = minima - 0.02 * span, maxima + 0.02 * span
        bounds = [float(minima[0]), float(maxima[0]), float(minima[1]), float(maxima[1])]
        grid = np.zeros((pixels, pixels), dtype=np.uint64)
        for start in range(0, n, resources.batch_rows):
            block = xy[start : start + resources.batch_rows]
            grid += raster_points(block, np.ones(len(block), dtype=np.uint64), pixels, bounds)
        if int(grid.sum()) != n:
            raise RuntimeError("Coordinate raster conservation failed")
        np.save(output / "node_counts.npy", grid)
        fig, ax = plt.subplots(figsize=(10, 9))
        image = ax.imshow(
            np.ma.masked_equal(grid, 0),
            origin="lower",
            extent=bounds,
            cmap="magma",
            norm=LogNorm(vmin=1, vmax=max(2, int(grid.max()))),
        )
        fig.colorbar(image, ax=ax, label="Nodes per pixel")
        ax.set_title("Node density · supplied coordinates", fontsize=22, pad=18)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        save_figure(fig, output, "coordinate_density")
    write_json(
        output / "manifest.json",
        {
            "view": "coordinate-density",
            "input": fingerprint(coordinate_file),
            "nodes": n,
            "bounds": bounds,
            "pixels": pixels,
            "node_mass": int(grid.sum()),
            "coordinate_order": "prepared compact node_id order",
            "metrics": monitor.stats,
            "environment": environment(),
        },
    )
    return output

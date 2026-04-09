from __future__ import annotations

from typing import Any


def _cluster_positions(values: list[float], tolerance: float) -> list[float]:
    if not values:
        return []
    sorted_values = sorted(values)
    clusters: list[list[float]] = [[sorted_values[0]]]
    for value in sorted_values[1:]:
        if abs(value - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _nearest_cluster(value: float, clusters: list[float]) -> int:
    if not clusters:
        return 0
    distances = [abs(value - center) for center in clusters]
    return int(min(range(len(clusters)), key=lambda idx: distances[idx]))


def extract_tables_from_ocr_page(
    page: dict[str, Any],
    *,
    row_tolerance: float = 18.0,
    col_tolerance: float = 28.0,
) -> list[dict[str, Any]]:
    """
    Heuristic table extraction from OCR line boxes.
    """
    lines = page.get("lines") or []
    if len(lines) < 4:
        return []

    y_centers: list[float] = []
    x_centers: list[float] = []
    normalized_lines: list[dict[str, Any]] = []
    for line in lines:
        bbox = line.get("bbox") or [0, 0, 0, 0]
        if len(bbox) != 4:
            continue
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            continue
        y_center = y + h / 2.0
        x_center = x + w / 2.0
        y_centers.append(float(y_center))
        x_centers.append(float(x_center))
        normalized_lines.append({"text": str(line.get("text", "")), "x_center": x_center, "y_center": y_center})

    row_centers = _cluster_positions(y_centers, row_tolerance)
    col_centers = _cluster_positions(x_centers, col_tolerance)
    if len(row_centers) < 2 or len(col_centers) < 2:
        return []

    grid = [["" for _ in col_centers] for _ in row_centers]
    for line in normalized_lines:
        row_idx = _nearest_cluster(float(line["y_center"]), row_centers)
        col_idx = _nearest_cluster(float(line["x_center"]), col_centers)
        existing = grid[row_idx][col_idx]
        if existing:
            grid[row_idx][col_idx] = f"{existing} {line['text']}".strip()
        else:
            grid[row_idx][col_idx] = line["text"].strip()

    non_empty_rows = sum(1 for row in grid if any(cell for cell in row))
    if non_empty_rows < 2:
        return []

    return [
        {
            "table_id": "table-1",
            "row_count": len(grid),
            "column_count": len(col_centers),
            "rows": [{"row_index": idx, "cells": row} for idx, row in enumerate(grid)],
        }
    ]

"""
Palletizing Grid Calculations
============================

Calculate place positions for boxes in an N×M grid pattern.
"""

from typing import List, Tuple


def calculate_place_positions(
    rows: int,
    cols: int,
    box_size_mm: Tuple[float, float, float],
    pallet_origin_mm: Tuple[float, float, float],
    spacing_mm: float = 10.0,
) -> List[Tuple[float, float, float]]:
    """
    Calculate TCP positions for placing boxes in a grid pattern.
    
    Args:
        rows: Number of rows (N)
        cols: Number of columns (M)
        box_size_mm: (width, depth, height) of each box in mm
        pallet_origin_mm: (x, y, z) position of the first box placement
        spacing_mm: Gap between adjacent boxes (default 10mm)
    
    Returns:
        List of (x, y, z) TCP target positions, ordered for row-by-row filling.
    """
    res = []
    box_tcp = box_size_mm[0]/2, box_size_mm[1]/2, box_size_mm[2]

    for r in range(rows):
        for c in range(cols):
            x = pallet_origin_mm[0] + c * (box_size_mm[0] + spacing_mm) + box_tcp[0]
            y = pallet_origin_mm[1] + r * (box_size_mm[1] + spacing_mm) + box_tcp[1]
            z = pallet_origin_mm[2] + box_tcp[2]
            res.append((float(x), float(y), float(z)))
    return res

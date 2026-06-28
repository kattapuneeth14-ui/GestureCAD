"""
Geometry module for GestureCAD.
Defines Point, Line, and Polygon primitives with operations like translation,
bounding box, centroid calculation, and hit detection.
"""

from typing import List, Tuple, Optional
import math
import numpy as np


class Point:
    """Represents a 2D point with floating point coordinates."""

    def __init__(self, x: float, y: float) -> None:
        self.x: float = x
        self.y: float = y

    def distance(self, other: "Point") -> float:
        """Calculate Euclidean distance to another point."""
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def translate(self, dx: float, dy: float) -> None:
        """Translate the point by dx, dy."""
        self.x += dx
        self.y += dy

    def to_tuple(self) -> Tuple[int, int]:
        """Convert coordinates to integer tuple for OpenCV drawing."""
        return int(round(self.x)), int(round(self.y))

    def copy(self) -> "Point":
        """Return a copy of this point."""
        return Point(self.x, self.y)

    def __repr__(self) -> str:
        return f"Point({self.x:.1f}, {self.y:.1f})"


class Line:
    """Represents a line segment between two points."""

    def __init__(self, p1: Point, p2: Point) -> None:
        self.p1: Point = p1
        self.p2: Point = p2

    def length(self) -> float:
        """Calculate length of the line segment."""
        return self.p1.distance(self.p2)

    def translate(self, dx: float, dy: float) -> None:
        """Translate both endpoints of the line."""
        self.p1.translate(dx, dy)
        self.p2.translate(dx, dy)

    def distance_to_point(self, pt: Point) -> float:
        """Calculate minimum distance from a point to this line segment."""
        px = self.p2.x - self.p1.x
        py = self.p2.y - self.p1.y
        something = px * px + py * py
        if something == 0:
            return pt.distance(self.p1)

        # Projection factor
        u = ((pt.x - self.p1.x) * px + (pt.y - self.p1.y) * py) / something

        # Clamp projection factor to stay within segment
        if u > 1:
            u = 1
        elif u < 0:
            u = 0

        # Nearest point on segment
        nx = self.p1.x + u * px
        ny = self.p1.y + u * py

        return math.sqrt((pt.x - nx) ** 2 + (pt.y - ny) ** 2)

    def __repr__(self) -> str:
        return f"Line({self.p1} -> {self.p2})"


class Polygon:
    """Represents a 2D Polygon composed of Point vertices."""

    def __init__(self, vertices: Optional[List[Point]] = None) -> None:
        self.vertices: List[Point] = vertices if vertices is not None else []
        self.is_closed: bool = False
        # Style details
        self.color: Tuple[int, int, int] = (0, 255, 0)  # Default BGR: Emerald/Green
        self.line_thickness: int = 2
        self.fill_alpha: float = 0.3

    def add_vertex(self, pt: Point) -> None:
        """Add a vertex to the polygon. Only allowed if not closed."""
        if not self.is_closed:
            self.vertices.append(pt)

    def close(self) -> None:
        """Close the polygon (connect last vertex to the first)."""
        if len(self.vertices) >= 3:
            self.is_closed = True

    def clear(self) -> None:
        """Clear all vertices and reset closed state."""
        self.vertices.clear()
        self.is_closed = False

    def translate(self, dx: float, dy: float) -> None:
        """Translate all vertices by dx and dy."""
        for pt in self.vertices:
            pt.translate(dx, dy)

    def calculate_centroid(self) -> Point:
        """
        Calculate the centroid (center of mass) of the polygon.
        If not closed or simple, returns the arithmetic mean of the vertices.
        """
        if not self.vertices:
            return Point(0, 0)
        
        # Calculate arithmetic mean of vertices
        xs = [pt.x for pt in self.vertices]
        ys = [pt.y for pt in self.vertices]
        return Point(sum(xs) / len(xs), sum(ys) / len(ys))

    def get_bounding_box(self) -> Tuple[Point, Point]:
        """
        Get the bounding box of the polygon.
        Returns (min_point, max_point).
        """
        if not self.vertices:
            return Point(0, 0), Point(0, 0)
        
        xs = [pt.x for pt in self.vertices]
        ys = [pt.y for pt in self.vertices]
        return Point(min(xs), min(ys)), Point(max(xs), max(ys))

    def contains_point(self, pt: Point) -> bool:
        """
        Check if a point is inside the polygon using the Ray-Casting algorithm.
        Only valid if the polygon is closed.
        """
        if not self.is_closed or len(self.vertices) < 3:
            return False

        # Fast bounding box check
        p_min, p_max = self.get_bounding_box()
        # Add a tiny padding to bounding box check
        padding = 10
        if not (p_min.x - padding <= pt.x <= p_max.x + padding and p_min.y - padding <= pt.y <= p_max.y + padding):
            return False

        inside = False
        n = len(self.vertices)
        x, y = pt.x, pt.y
        for i in range(n):
            j = (i + 1) % n
            vi = self.vertices[i]
            vj = self.vertices[j]

            # Standard Ray Casting
            if ((vi.y > y) != (vj.y > y)) and (x < (vj.x - vi.x) * (y - vi.y) / (vj.y - vi.y + 1e-9) + vi.x):
                inside = not inside

        return inside

    def hit_test(self, pt: Point, hover_threshold: float = 15.0) -> bool:
        """
        Perform a hit test on the polygon.
        A polygon is hit if:
        1. The point is inside it (if closed)
        2. The point is close to any of its vertices
        3. The point is close to any of its line segments
        """
        if not self.vertices:
            return False

        # Check vertices proximity
        for v in self.vertices:
            if pt.distance(v) <= hover_threshold:
                return True

        # Check line segments proximity
        n = len(self.vertices)
        limit = n if self.is_closed else n - 1
        for i in range(limit):
            p1 = self.vertices[i]
            p2 = self.vertices[(i + 1) % n]
            line = Line(p1, p2)
            if line.distance_to_point(pt) <= hover_threshold:
                return True

        # If closed, check if inside
        if self.is_closed:
            return self.contains_point(pt)

        return False

    def copy(self) -> "Polygon":
        """Create a deep copy of the polygon."""
        poly = Polygon([pt.copy() for pt in self.vertices])
        poly.is_closed = self.is_closed
        poly.color = self.color
        poly.line_thickness = self.line_thickness
        poly.fill_alpha = self.fill_alpha
        return poly

    def __repr__(self) -> str:
        return f"Polygon(vertices={len(self.vertices)}, closed={self.is_closed})"

"""Read SketchUp .skp files without SketchUp: geometry, materials, dimensions."""

from .extract import Extraction, extract
from .regions import Region, build_regions

__all__ = ["Extraction", "extract", "Region", "build_regions", "__version__"]
__version__ = "0.1.0"

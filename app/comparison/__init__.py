"""Document comparison package."""
from app.comparison.diff import (
    DocumentComparator,
    compare_hierarchies,
    compare_tables,
    compute_word_diff,
)
from app.comparison.models import (
    ComparisonSummary,
    DocumentComparisonResult,
    SectionDiff,
    TableDiff,
    TableRowDiff,
)

__all__ = [
    "DocumentComparator",
    "compare_hierarchies",
    "compare_tables",
    "compute_word_diff",
    "DocumentComparisonResult",
    "ComparisonSummary",
    "SectionDiff",
    "TableDiff",
    "TableRowDiff",
]

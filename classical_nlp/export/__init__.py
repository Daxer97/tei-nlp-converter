"""
Export Module for Classical NLP

Provides HTML report generation with:
- Highlighted text occurrences
- Word cloud visualization
- Statistics and analysis
"""

from .html_generator import HTMLReportGenerator, generate_occurrence_report

__all__ = [
    "HTMLReportGenerator",
    "generate_occurrence_report",
]

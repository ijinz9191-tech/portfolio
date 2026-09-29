"""Offline SLO burn analysis for synthetic five-minute request buckets."""

from .model import BurnError, assess, assess_segments

__all__ = ["BurnError", "assess", "assess_segments"]

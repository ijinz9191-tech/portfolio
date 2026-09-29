"""Offline SLO burn analysis for synthetic five-minute request buckets."""

from .model import BurnError, assess

__all__ = ["BurnError", "assess"]

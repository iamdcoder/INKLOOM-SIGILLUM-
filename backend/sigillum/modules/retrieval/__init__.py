"""Deterministic, provenance-preserving evidence retrieval primitives."""

from sigillum.modules.retrieval.evidence import retrieve_fact_candidates
from sigillum.modules.retrieval.temporal import assess_temporality

__all__ = ["assess_temporality", "retrieve_fact_candidates"]

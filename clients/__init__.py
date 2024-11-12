# clients/__init__.py
"""
Clients package for Airflow Log Analyzer.
Contains clients for external services like Ollama.
"""

from .ollama_client import OllamaClient

__all__ = ["OllamaClient"]

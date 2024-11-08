# Root __init__.py (in airflow_log_analyzer directory)
"""
Airflow Log Analyzer
A tool for analyzing Apache Airflow logs using AI-powered insights.
"""

from services import LogAnalyzer, ReportGenerator
from clients import OllamaClient
from models import MongoJSONEncoder

__version__ = '1.0.0'

__all__ = [
    'LogAnalyzer',
    'ReportGenerator',
    'OllamaClient',
    'MongoJSONEncoder'
]
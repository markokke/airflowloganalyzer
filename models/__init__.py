# models/__init__.py
"""
Models package for Airflow Log Analyzer.
Contains data models and encoders used throughout the application.
"""

from .mongo_encoder import MongoJSONEncoder

__all__ = ['MongoJSONEncoder']
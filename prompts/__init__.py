from .templates import DBT_ANALYSIS_PROMPT  # Added trailing comma
from .templates import (AIRFLOW_LOG_ANALYSIS_PROMPT, ERROR_ANALYSIS_PROMPT,
                        PERFORMANCE_ANALYSIS_PROMPT,
                        POD_LIFECYCLE_ANALYSIS_PROMPT, SUMMARY_TEMPLATE,
                        SYSTEM_PROMPT_TEMPLATE, TEST_FAILURE_ANALYSIS_PROMPT,
                        PromptTemplate)

__all__ = [
    "PromptTemplate",
    "SYSTEM_PROMPT_TEMPLATE",  # Add this line
    "AIRFLOW_LOG_ANALYSIS_PROMPT",
    "ERROR_ANALYSIS_PROMPT",
    "TEST_FAILURE_ANALYSIS_PROMPT",
    "PERFORMANCE_ANALYSIS_PROMPT",
    "POD_LIFECYCLE_ANALYSIS_PROMPT",
    "SUMMARY_TEMPLATE",
    "DBT_ANALYSIS_PROMPT",  # Added trailing comma
]

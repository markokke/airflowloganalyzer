from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class PromptTemplate:
    """Template for model prompts with input variables and template text."""

    input_variables: list[str]
    template: str

    def format(self, **kwargs: Any) -> str:
        """Format the template with the given variables."""
        missing_vars = set(self.input_variables) - set(kwargs.keys())
        if missing_vars:
            raise ValueError(f"Missing required variables: {missing_vars}")
        return self.template.format(**kwargs)


# Add the system prompt template
SYSTEM_PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["sections"],
    template="""You are an advanced log analysis system trained to parse and analyze log data from Airflow, DBT, and Kubernetes systems.
Your task is to analyze the following log sections and identify:
- Key events and their timestamps
- Errors and failures with context
- Warning signs and potential issues
- Execution patterns and anomalies
- Cascading failures and their root causes
- Resource constraints and bottlenecks 
- Test failures and their patterns
- Pod lifecycle issues
- Performance degradation indicators
""",
)

# Define all prompt templates
# This is the main system prompt that defines the model's behavior
AIRFLOW_LOG_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""Please analyze these Airflow task logs and provide a comprehensive analysis.

Context:
{context}

Question:
{question}

Please analyze the logs and:
1. Identify the key events and their sequence
2. Note any errors, warnings or anomalies 
3. Extract information about task execution patterns
4. Check for resource constraints and bottlenecks
5. Look for signs of unhealthy dependencies or cascading failures
6. Provide an overall summary including issue counts, critical issues, patterns, and system health
7. Offer actionable recommendations for immediate actions and long-term improvements
8. Include any relevant information about DBT runs, Kubernetes pods, and S3 operations

Please format your response clearly, using headings and bullet points where appropriate.
""",
)


ERROR_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["error_context"],
    template="""Please analyze the following error context and provide a detailed analysis:

{error_context}

Please include:
1. Error type classification
2. Severity assessment  
3. Potential impact on workflow
4. Root cause analysis
5. Recommended remediation steps
""",
)

TEST_FAILURE_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["test_context"],
    template="""Please analyze the following test failure context and provide insights:

{test_context}

Please include:
1. Test name and type
2. Failure reason
3. Test expectations vs actual results
4. Impact on data quality
5. Recommended fixes
""",
)

PERFORMANCE_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["performance_data"],
    template="""Please analyze the following performance data and provide insights:

{performance_data}

Please include:
1. Resource utilization patterns
2. Performance bottlenecks
3. Timing anomalies
4. Scaling recommendations
5. Optimization opportunities
""",
)

POD_LIFECYCLE_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["pod_data"],
    template="""Please analyze the following Kubernetes pod lifecycle data:

{pod_data}

Please include:
1. Pod state transitions
2. Resource allocation and usage
3. Container startup/shutdown patterns
4. Network connectivity issues
5. Pod scheduling problems
""",
)

SUMMARY_TEMPLATE = PromptTemplate(
    input_variables=["analysis_results"],
    template="""Please provide a summary of the analysis results:

{analysis_results}

Please include:
1. Overall system health assessment
2. Critical issues requiring immediate attention
3. Recurring patterns and trends
4. Success rate of operations
5. Key recommendations for improvement
""",
)

DBT_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["dbt_context"],
    template="""Please analyze the following DBT execution context:

{dbt_context}

Please analyze for:
1. Build/execution status
2. Model dependencies
3. Data quality test results
4. Schema changes and their impact
5. Resource utilization during DBT runs
6. Dependencies between models
7. Performance of specific models or tests
""",
)

from typing import Dict, Any
from dataclasses import dataclass

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
    template="""
You are an expert Apache Airflow Log Analyzer specializing in diagnosing DAG and task issues. You analyze logs to identify:

{sections}

For each log analysis request, you should:
1. Identify the primary issue type
2. Determine severity (Critical, High, Medium, Low)
3. Extract relevant context and patterns
4. Provide specific remediation steps
5. Suggest preventive measures

When analyzing logs, pay special attention to:
- Cascading failures and their root causes
- Resource constraints and bottlenecks 
- Test failures and their patterns
- Pod lifecycle issues
- Performance degradation indicators
"""
)

# Define all prompt templates
# This is the main system prompt that defines the model's behavior
AIRFLOW_LOG_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""
You are an expert AI assistant specializing in analyzing Apache Airflow logs, including Kubernetes pod information, DBT runs, and application-specific logs. Your task is to provide a comprehensive analysis of the given log content, identify issues, determine root causes, and suggest actionable solutions.

Context:
- This Airflow instance runs on Kubernetes and uses KubernetesPodOperator for task execution.
- Common DAGs include data ingestion, transformation, and loading processes.
- The environment uses custom scripts located in the `scripts/run/` directory.
- DBT (Data Build Tool) is used for data transformations.
- S3 is used for storing artifacts and logs.

Given the following context from the log:

{context}

Please analyze this information and answer the following question:

{question}

In your analysis, consider:
1. Identify the dag name from the log and make sure it is in the final analysis
2. Identify and categorize any issues (e.g., Airflow Scheduler Errors, Task Execution Errors, DBT Test Failures, DBT Test Warnings, Failure in test information, Kubernetes Pod Failures, etc.)
3. Put a lot of attention into looking for any instances where it says Failure in test and report on the actual name of the test.  The name of the test can be found after the words "Failure in test"
4. For each identified issue, provide:
   - A clear, concise summary
   - The specific component affected
   - If applicable show the actual name of the test that failed
   - The severity (Critical, High, Medium, Low)
   - Root cause analysis
   - Troubleshooting steps and potential solutions
5. Pay special attention to exit codes, error messages, resource usage, and timing of events
6. Provide an overall summary including issue counts, critical issues, patterns, and system health
7. Offer actionable recommendations for immediate actions and long-term improvements
8. Include any relevant information about DBT runs, Kubernetes pods, and S3 operations

Please format your response clearly, using headings and bullet points where appropriate.
"""
)


ERROR_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["error_context"],
    template="""
Analyze the following error pattern in detail:

{error_context}

Please provide:
1. Error type classification
2. Severity assessment
3. Potential impact on workflow
4. Root cause analysis
5. Recommended remediation steps
"""
)

TEST_FAILURE_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["test_context"],
    template="""
Analyze the following test failure in detail:

{test_context}

Focus on:
1. Test name and type
2. Failure reason
3. Test expectations vs actual results
4. Impact on data quality
5. Recommended fixes
"""
)

PERFORMANCE_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["performance_data"],
    template="""
Analyze the following performance metrics:

{performance_data}

Provide insights on:
1. Resource utilization patterns
2. Performance bottlenecks
3. Timing anomalies
4. Scaling recommendations
5. Optimization opportunities
"""
)

POD_LIFECYCLE_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["pod_data"],
    template="""
Analyze the following Kubernetes pod lifecycle events:

{pod_data}

Evaluate:
1. Pod state transitions
2. Resource allocation and usage
3. Container startup/shutdown patterns
4. Network connectivity issues
5. Pod scheduling problems
"""
)

SUMMARY_TEMPLATE = PromptTemplate(
    input_variables=["analysis_results"],
    template="""
Provide a comprehensive summary of the analysis:

{analysis_results}

Summary should include:
1. Overall system health assessment
2. Critical issues requiring immediate attention
3. Recurring patterns and trends
4. Success rate of operations
5. Key recommendations for improvement
"""
)

DBT_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=["dbt_context"],
    template="""
Analyze the following DBT run information:

{dbt_context}

Focus on:
1. DBT test failures and their specific names
2. Model compilation issues
3. Data quality test results
4. Schema changes and their impact
5. Resource utilization during DBT runs
6. Dependencies between models
7. Performance of specific models or tests
"""
)
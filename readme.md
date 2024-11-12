# Airflow Log Analyzer

An AI-powered tool for analyzing Apache Airflow logs using Ollama models.

## Installation
```bash
pip install -r requirements.txt
```

### Mongo DB Index
```bash
db.DagTaskLogs.createIndex(
  { "LogInfo": "text" },
  {
    "weights": {
      "LogInfo": 1
    },
    "default_language": "english",
    "language_override": "language",
    "sparse": true,
    "background": true,
    "name": "LogInfo_text"
  }
)
```

## Usage

```bash
python main.py
```

## Configuration

Edit `config.yaml` to customize:
- MongoDB connection settings
- Analysis parameters
- Model settings
- Output options

## Project Structure

- `models/`: Data models and encoders
- `clients/`: External service clients
- `services/`: Core business logic
- `prompts/`: Model prompt templates


## Log Analysis Technology Enhancement Options

### Langchain Benefits

- **Memory Management**
  - Maintain conversation history about specific error patterns
  - Enable follow-up analysis on patterns
  
- **Document Loaders**
  - Easy integration with multiple log sources beyond MongoDB
  
- **Chain of Thought**
  - Create sophisticated analysis pipelines:
  ```python
  error_analysis_chain = (
      error_extractor
      >> context_enricher
      >> pattern_matcher
      >> root_cause_analyzer
      >> recommendation_generator
  )
  ```
- **Structured Output Parsing**
  - Enforce strict typing on Ollama's responses
  - Ensure consistent report formatting

## LangGraph Benefits

- **Parallel Processing**
  - Analyze different log patterns concurrently
  
- **Workflow Management**
  - Create dynamic analysis flows:
  ```python
  @graph
  def log_analysis_workflow():
      initial_scan = scan_logs()
      if "error" in initial_scan:
          error_analysis = analyze_errors(initial_scan)
      if "test_failure" in initial_scan:
          test_analysis = analyze_test_failures(initial_scan)
      if needs_historical_context():
          historical = query_vector_db()
      return combine_analyses()

  
- **State Management**
  - Track analysis state
  - Conditionally execute different analysis paths

## Chroma Vector Database Benefits

- **Historical Pattern Recognition**
  - Store historical log patterns and their analyses
  
- **Similar Issue Detection**
  - Find similar past errors and their solutions
  
- **Pattern Evolution**
  - Track how error patterns change over time
  ```python
  # Example of how you might use Chroma
  similar_errors = vector_db.similarity_search(
      "unique_r360_final_stage__risk__risk_stage_hash_setid_cust_id_platform_",
      filter={"pattern_type": "test_failure"}
  )
  ```
  
- **Root Cause Analysis**
  - Build relationships between different types of errors

## When to Consider Adding These Technologies

Consider implementing these technologies when you need:
1. To analyze patterns across time (Chroma)
2. More complex analysis workflows (LangGraph)
3. Sophisticated prompt management and chaining (Langchain)
4. To scale beyond simple pattern matching
5. To maintain historical context of issues

## Example Integration

```python
# Using all three technologies
async def enhanced_analysis():
    # Extract current patterns
    current_patterns = extract_log_patterns()
    
    # Find similar historical patterns
    similar_patterns = chroma_db.similarity_search(current_patterns)
    
    # Create analysis graph
    analysis_graph = Graph()
    analysis_graph.add_node("pattern_matching", your_current_logic)
    analysis_graph.add_node("historical_comparison", compare_with_history)
    analysis_graph.add_node("root_cause", determine_root_cause)
    
    # Chain the analysis steps
    analysis_chain = Chain([
        pattern_extractor,
        context_enricher,
        solution_recommender
    ])
    
    return await analysis_graph.execute()
  ```

## Current Usage Considerations

If your current needs are primarily pattern matching and prompt-based analysis, these technologies might be more than necessary. However, they provide a clear upgrade path when you need to:

- Analyze historical patterns
- Implement complex workflows
- Scale analysis capabilities
- Maintain context across multiple analyses
- Generate more sophisticated insights
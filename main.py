import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from services.log_analyzer import LogAnalyzer
from services.report_generator import ReportGenerator


def load_config(config_path: str) -> Dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration: {str(e)}")
        sys.exit(1)


def setup_logging(config: Dict) -> logging.Logger:
    """
    Set up logging configuration.

    Args:
        config: Configuration dictionary

    Returns:
        Configured logger instance
    """
    try:
        logging.config.dictConfig(config["logging"])
        return logging.getLogger("airflow_log_analyzer")
    except Exception as e:
        print(f"Error setting up logging: {str(e)}")
        sys.exit(1)


def initialize_services(config: Dict):
    """Initialize the main services needed for log analysis."""
    try:
        report_generator = ReportGenerator(config)
        analyzer = LogAnalyzer(config=config, report_generator=report_generator)
        return analyzer, report_generator
    except Exception as e:
        print(f"Error initializing services: {str(e)}")
        sys.exit(1)


def main():
    """Main execution function."""
    try:
        # Load configuration
        config = load_config("config.yaml")

        # Setup logging
        logger = setup_logging(config)
        logger.info("Starting Individual Log Analysis")

        # Initialize services
        analyzer, report_generator = initialize_services(config)

        # Analyze individual logs - reports are generated within this method now
        print("Analyzing individual logs...")
        analysis_results = analyzer.analyze_individual_logs()

        # Log the completion statistics
        logger.info(f"Completed analysis of {len(analysis_results)} logs")
        print(f"\nCompleted analysis of {len(analysis_results)} logs")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\nUnexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

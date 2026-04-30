.PHONY: eval optimize convert check eval-simple eval-layout optimize-simple optimize-layout

eval: eval-simple eval-layout

eval-simple: convert
	adk eval src/agents/simple_agent tests/eval/evalsets/golden_evalset.json --config_file_path tests/eval/eval_config.json --print_detailed_results

eval-layout: convert
	adk eval src/agents/layout_aware_agent tests/eval/evalsets/golden_evalset.json --config_file_path tests/eval/eval_config.json --print_detailed_results

# Run prompt optimization using the official ADK GEPARootAgentPromptOptimizer
optimize: optimize-simple optimize-layout

optimize-simple: convert
	adk optimize src/agents/simple_agent --sampler_config_file_path tests/eval/sampler_config.json --optimizer_config_file_path tests/eval/optimizer_config.json --print_detailed_results

optimize-layout: convert
	adk optimize src/agents/layout_aware_agent --sampler_config_file_path tests/eval/layout_aware_agent_sampler_config.json --optimizer_config_file_path tests/eval/optimizer_config.json --print_detailed_results

convert:
	uv run python scripts/convert_dataset.py

check:
	uv run ruff check src

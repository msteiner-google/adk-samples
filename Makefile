.PHONY: eval optimize convert check test eval-simple eval-layout optimize-simple optimize-layout bench-thinking

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

# Sweep the thinking budget to trade accuracy off against latency and cost.
# AGENT and BUDGETS are overridable: make bench-thinking AGENT=layout_aware_agent
AGENT ?= simple_agent
bench-thinking: convert
	uv run python scripts/thinking_benchmark.py --agent $(AGENT) $(if $(BUDGETS),--budgets $(BUDGETS),)

convert:
	uv run python scripts/convert_dataset.py

check:
	uv run ruff check src scripts
	uv run ruff format --check src scripts

test:
	uv run pytest

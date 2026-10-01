.PHONY: eval optimize convert check test report batch eval-simple eval-layout eval-nl2sql optimize-simple optimize-layout optimize-nl2sql bench-thinking

eval: eval-simple eval-layout eval-nl2sql

eval-simple: convert
	adk eval src/agents/simple_agent tests/eval/evalsets/golden_evalset.json --config_file_path tests/eval/eval_config.json --print_detailed_results

eval-layout: convert
	adk eval src/agents/layout_aware_agent tests/eval/evalsets/golden_evalset.json --config_file_path tests/eval/eval_config.json --print_detailed_results

# The NL2SQL agent runs against its own evalset and its own config, which
# registers the custom result-match and self-healing metrics.
eval-nl2sql: convert
	adk eval src/agents/nl2sql_agent tests/eval/evalsets/nl2sql_evalset.json --config_file_path tests/eval/nl2sql_eval_config.json --print_detailed_results

# Run prompt optimization using the official ADK GEPARootAgentPromptOptimizer
optimize: optimize-simple optimize-layout optimize-nl2sql

optimize-simple: convert
	adk optimize src/agents/simple_agent --sampler_config_file_path tests/eval/sampler_config.json --optimizer_config_file_path tests/eval/optimizer_config.json --print_detailed_results

optimize-layout: convert
	adk optimize src/agents/layout_aware_agent --sampler_config_file_path tests/eval/layout_aware_agent_sampler_config.json --optimizer_config_file_path tests/eval/optimizer_config.json --print_detailed_results

optimize-nl2sql: convert
	adk optimize src/agents/nl2sql_agent --sampler_config_file_path tests/eval/nl2sql_sampler_config.json --optimizer_config_file_path tests/eval/optimizer_config.json --print_detailed_results

# Sweep the thinking budget to trade accuracy off against latency and cost.
# AGENT and BUDGETS are overridable: make bench-thinking AGENT=layout_aware_agent
AGENT ?= simple_agent
bench-thinking: convert
	uv run python scripts/thinking_benchmark.py --agent $(AGENT) $(if $(BUDGETS),--budgets $(BUDGETS),)

# Run the full evaluation matrix, then report on it.
# Override: make batch AGENTS=simple_agent BUDGETS=0,2048 JOBS=2
batch: convert
	uv run python scripts/run_batch_eval.py \
		$(if $(AGENTS),--agents $(AGENTS),) \
		$(if $(BUDGETS),--budgets $(BUDGETS),) \
		$(if $(JOBS),--jobs $(JOBS),)
	$(MAKE) report

# Build a markdown report from results already on disk. Calls no model.
report:
	uv run python scripts/generate_report.py

convert:
	uv run python scripts/convert_dataset.py

check:
	uv run ruff check src scripts
	uv run ruff format --check src scripts

test:
	uv run pytest

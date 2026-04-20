.PHONY: eval optimize convert check

eval: convert
	adk eval src/agents/simple_agent tests/eval/evalsets/golden_evalset.json --config_file_path tests/eval/eval_config.json --print_detailed_results

optimize: convert
	adk optimize src/agents/simple_agent --sampler_config_file_path tests/eval/sampler_config.json --optimizer_config_file_path tests/eval/optimizer_config.json --print_detailed_results

convert:
	uv run python scripts/convert_dataset.py

check:
	uv run ruff check src

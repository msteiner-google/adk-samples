.PHONY: eval convert check

eval: convert
	adk eval src tests/eval/evalsets/golden_evalset.json --config_file_path tests/eval/eval_config.json

convert:
	uv run python scripts/convert_dataset.py

check:
	uv run ruff check src

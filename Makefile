test:
	python3 -m unittest discover tests/

lint:
	ruff check src/ tests/

seed:
	cp data/samples/raw/terraform_issues.json data/samples/raw/terraform_aws_issues.json data/raw/
	cp data/samples/processed/insights.json data/processed/
	cp data/samples/approvals/approvals.json data/approvals/
	@echo "Seeded data/raw, data/processed, and data/approvals from data/samples."

run:
	python3 -m src.pipeline

remind:
	python3 -m src.reminder_runner

dry-run:
	python3 -m src.reminder_runner --dry-run

.PHONY: test lint seed run remind dry-run

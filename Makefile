test:
	python3 -m unittest discover tests/

run:
	python3 src/pipeline.py

remind:
	python3 src/reminder_runner.py

dry-run:
	python3 src/reminder_runner.py --dry-run

.PHONY: test run remind dry-run

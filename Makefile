.PHONY: install test run

install:
	python -m pip install -r requirements.txt

test:
	pytest tests/ -v

run:
	python -m src.main --help

.PHONY: setup test demo dashboard clean
setup:
	python -m pip install -r requirements.txt
test:
	python -m pytest -q
	python -m ruff check src tests scripts
demo:
	python -m src.local_demo --count 5000
	cp data/demo/dashboard.json docs/dashboard.json
	cp data/demo/benchmarks.json docs/benchmarks.json
dashboard:
	python -m http.server 8000 --directory docs
clean:
	rm -rf data .pytest_cache .ruff_cache

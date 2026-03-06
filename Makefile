.PHONY: test test-unit test-integration build publish clean

test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/ -v -m "not integration"

test-integration:
	python -m pytest tests/ -v -m integration

build: clean
	python -m build

publish: build
	twine upload dist/*

clean:
	rm -rf dist/

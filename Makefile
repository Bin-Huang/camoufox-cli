.PHONY: build publish clean

build: clean
	python -m build

publish: build
	twine upload dist/*

clean:
	rm -rf dist/

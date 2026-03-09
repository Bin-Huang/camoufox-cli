.PHONY: test test-unit test-integration build publish publish-pip publish-npm clean

test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/ -v -m "not integration"

test-integration:
	python -m pytest tests/ -v -m integration

build: clean
	python -m build
	cd js && npm run build

publish: publish-pip publish-npm

publish-pip: build
	twine upload dist/*

publish-npm: build
	cd js && npm publish --access public

clean:
	rm -rf dist/
	rm -rf js/dist/

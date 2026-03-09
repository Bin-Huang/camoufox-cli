.PHONY: test test-unit test-integration test-e2e build publish publish-pip publish-npm clean

test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/ -v -m "not integration"

test-integration:
	python -m pytest tests/ -v -m integration

test-e2e:
	python -m pytest tests/test_e2e.py -v
	cd js && npx vitest run tests/e2e.test.ts

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

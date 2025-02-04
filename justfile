build:
    uv build

clear:
    rm -rf dist/*

publish: test clear build
    uv publish

test:
    uv run pytest tests/

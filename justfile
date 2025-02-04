build:
    uv build

clear:
    rm -rf dist/*

publish: clear build
    uv publish

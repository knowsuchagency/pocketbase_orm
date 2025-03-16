build:
    uv build

clear:
    rm -rf dist/*

publish: test clear build
    uv publish

test:
    uv run pytest -xvs tests/

format:
    uvx ruff format .

set-secrets:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
        echo "Error: .env file not found"
        exit 1
    fi
    while IFS='=' read -r key value || [ -n "$key" ]; do
        if [ -n "$key" ] && [ "${key#\#}" = "$key" ]; then
            trimmed_value=$(echo "$value" | xargs)
            echo "Setting $key as a secret..."
            gh secret set "$key" --body="$trimmed_value"
        fi
    done < .env

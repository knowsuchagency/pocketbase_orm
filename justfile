build:
    uv build

clear:
    rm -rf dist/*

publish: test clear build
    uv publish

test:
    uv run pytest -xvs tests/

format:
    uvx ruff@0.11.13 check . --fix && uvx ruff@0.11.13 format .

ruff-ci:
    uvx ruff@0.11.13 check . && uvx ruff@0.11.13 format --check .

# sudo apt install curl unzip
install-pocketbase:
	./scripts/install-pocketbase.sh

clear-pocketbase:
	rm -rf db/pb_data
	rm -rf db/pb_migrations

seed-pocketbase:
	ADMIN_EMAIL=admin@pb.com ADMIN_PASSWORD=mamaistdiebeste ./scripts/seed-pocketbase.sh

start-pocketbase:
	./db/pocketbase serve --dir=./db/pb_data --migrationsDir=./db/pb_migrations --http 127.0.0.1:4419

reset-pocketbase: clear-pocketbase seed-pocketbase start-pocketbase
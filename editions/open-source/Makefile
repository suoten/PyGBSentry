.PHONY: env-dev env-dev-check env-prod env-prod-check compose-dev-up compose-prod-up compose-dev-down compose-prod-down compose-dev-ps compose-prod-ps compose-dev-logs compose-prod-logs compose-dev-logs-follow compose-prod-logs-follow

env-dev:
	python tools/env_manager.py switch --env dev

env-dev-check:
	python tools/env_manager.py validate --env dev

env-prod:
	python tools/env_manager.py switch --env prod

env-prod-check:
	python tools/env_manager.py validate --env prod

compose-dev-up:
	python tools/env_manager.py switch --env dev
	python tools/env_manager.py validate --env dev
	docker compose --profile dev up -d

compose-prod-up:
	python tools/env_manager.py switch --env prod
	python tools/env_manager.py validate --env prod
	docker compose --profile prod up -d

compose-dev-down:
	docker compose --profile dev down

compose-prod-down:
	docker compose --profile prod down

compose-dev-ps:
	docker compose --profile dev ps

compose-prod-ps:
	docker compose --profile prod ps

compose-dev-logs:
	docker compose --profile dev logs --tail 200

compose-prod-logs:
	docker compose --profile prod logs --tail 200

compose-dev-logs-follow:
	docker compose --profile dev logs -f --tail 200

compose-prod-logs-follow:
	docker compose --profile prod logs -f --tail 200

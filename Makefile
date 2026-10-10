# Lab Grader. Run `make help`.
SHELL := /bin/bash
COMPOSE := docker compose
-include .env
export

.PHONY: help init images build up down restart logs ps test test-docker smoke up-ci down-ci google-auth backup clean

help:
	@echo "make init         create .env with random passwords (once)"
	@echo "make up           build everything and start the dashboard"
	@echo "make smoke        end-to-end check of the running stack"
	@echo "make test         all unit tests, inside a container"
	@echo "make test-docker  real sandbox isolation tests (needs 'make images')"
	@echo "make up-ci        also start Jenkins"
	@echo "make google-auth  connect your Google account (run on your own computer)"
	@echo "make logs / ps / down / backup"

init:
	@python3 scripts/init_env.py

images:
	$(COMPOSE) --profile images build runner-python runner-gcc runner-java

build:
	$(COMPOSE) build sandbox mcp app

up: init images build
	$(COMPOSE) up -d db sandbox mcp app
	@echo
	@echo "Dashboard: http://localhost:$${APP_PORT:-8000}   login: $${ADMIN_USER:-ta} / see ADMIN_PASSWORD in .env"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart app mcp sandbox

logs:
	$(COMPOSE) logs -f --tail=100 app mcp sandbox

ps:
	$(COMPOSE) ps

test:
	docker build -f ci/Dockerfile.test -t autograder-test .
	docker run --rm autograder-test

test-docker: images
	docker build -f ci/Dockerfile.test -t autograder-test .
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock autograder-test \
	  bash -c "cd sandbox && python -m pytest -m docker -v tests/test_isolation_docker.py"

smoke:
	python3 scripts/smoke.py http://localhost:$${APP_PORT:-8000} $${ADMIN_USER:-ta} "$${ADMIN_PASSWORD}"

up-ci: init
	$(COMPOSE) --profile ci up -d --build jenkins
	@echo "Jenkins: http://localhost:$${JENKINS_PORT:-8081}   login: $${JENKINS_ADMIN_USER:-admin} / see JENKINS_ADMIN_PASSWORD in .env"

down-ci:
	$(COMPOSE) --profile ci stop jenkins

google-auth:
	python3 -m pip install --user --quiet google-auth-oauthlib google-api-python-client
	python3 scripts/google_auth.py

backup:
	@mkdir -p backups
	$(COMPOSE) exec -T db pg_dump -U grader grader | gzip > backups/grader-$$(date +%F-%H%M).sql.gz
	@ls -1t backups | head -1

clean:
	$(COMPOSE) --profile ci --profile images down -v

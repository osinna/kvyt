.PHONY: up down reset doctor lesson check

# `make lesson 3.2`: the lesson id arrives as a second goal; turn it into a
# variable and a no-op target so make does not try to build it.
ifeq (lesson,$(firstword $(MAKECMDGOALS)))
  LESSON := $(word 2,$(MAKECMDGOALS))
  ifneq ($(LESSON),)
    $(eval $(LESSON):;@:)
  endif
endif

# Brings the long-running services up and waits for their healthchecks, then
# runs the one-off seed container and waits for its exit code. Seed is kept out
# of --wait: compose reports a container that already exited as a failure.
# `make lesson` points COMPOSE at the code of the lesson's release.
COMPOSE ?= docker compose

define start
	$(COMPOSE) build
	$(COMPOSE) up -d --wait --wait-timeout 180 --remove-orphans $$($(COMPOSE) config --services | grep -vx seed)
	$(COMPOSE) up -d seed
	@code=$$(docker wait $$($(COMPOSE) ps -aq seed)); \
	if [ "$$code" != "0" ]; then \
		echo "Seeding failed (exit code $$code). Details: docker compose logs seed"; \
		exit 1; \
	fi
	@echo ""
	@echo "Web:     http://localhost:3000"
	@echo "Gateway: http://localhost:8080"
endef

up: .env
	$(start)

down:
	docker compose down

reset: .env
	docker compose down -v
	$(start)

# Runs the code the lesson was released with, not the current checkout, under
# the same compose project name, so it replaces the running stack and its data.
lesson: .env
	@scenarios=$$(./scripts/lesson-scenarios.sh "$(LESSON)") || exit 1; \
	src=$$(./scripts/lesson-source.sh "$(LESSON)") || exit 1; \
	project=$$(docker compose config | sed -n 's/^name: //p'); \
	echo "Lesson $(LESSON): BUG_SCENARIO=$$scenarios"; \
	BUG_SCENARIO=$$scenarios $(MAKE) --no-print-directory up \
		COMPOSE="docker compose -p $$project -f $$src/docker-compose.yml"

check: .env
	@[ -x scripts/check.sh ] || { echo "Release checks are not part of this copy."; exit 1; }
	@./scripts/check.sh

doctor:
	@./scripts/doctor.sh

.env:
	cp .env.example .env

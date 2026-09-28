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
define start
	docker compose build
	docker compose up -d --wait --wait-timeout 180 $$(docker compose config --services | grep -vx seed)
	docker compose up -d seed
	@code=$$(docker wait $$(docker compose ps -aq seed)); \
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

lesson: .env
	@scenarios=$$(./scripts/lesson-scenarios.sh "$(LESSON)") || exit 1; \
	echo "Lesson $(LESSON): BUG_SCENARIO=$$scenarios"; \
	BUG_SCENARIO=$$scenarios $(MAKE) --no-print-directory up

check: .env
	@[ -x scripts/check.sh ] || { echo "Release checks are not part of this copy."; exit 1; }
	@./scripts/check.sh

doctor:
	@./scripts/doctor.sh

.env:
	cp .env.example .env

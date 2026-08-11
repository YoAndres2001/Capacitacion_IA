DC      := docker compose
DC_PROD := docker compose -f docker-compose.prod.yml
BE      := $(DC) exec backend

.DEFAULT_GOAL := help
.PHONY: help up down restart build logs ps migrate makemigrations seed superuser shell dbshell test lint format prod-up prod-down clean ai-check rebuild-indices

help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

up:  ## Levanta el entorno de desarrollo
	$(DC) up -d

build:  ## Reconstruye las imágenes
	$(DC) build

down:  ## Detiene los contenedores
	$(DC) down

restart:  ## Reinicia los servicios
	$(DC) restart

logs:  ## Sigue los logs
	$(DC) logs -f --tail=100

ps:  ## Estado de los servicios
	$(DC) ps

migrate:  ## Aplica migraciones
	$(BE) python manage.py migrate

makemigrations:  ## Genera migraciones
	$(BE) python manage.py makemigrations

seed:  ## Carga datos de demostración
	$(BE) python manage.py seed_demo

superuser:  ## Crea un superusuario
	$(BE) python manage.py createsuperuser

shell:  ## Shell de Django
	$(BE) python manage.py shell_plus || $(BE) python manage.py shell

dbshell:  ## Consola de PostgreSQL
	$(DC) exec postgres psql -U nexora -d nexora

test:  ## Ejecuta los tests
	$(BE) pytest -v

lint:  ## Linters
	$(BE) ruff check src config
	$(BE) black --check src config
	$(DC) exec frontend npm run lint

format:  ## Formatea el código
	$(BE) ruff check --fix src config
	$(BE) black src config
	$(DC) exec frontend npm run format

ai-check:  ## Diagnostica Groq (LLM) y los embeddings locales
	$(BE) python manage.py ai_bench

rebuild-indices:  ## Reconstruye los índices FAISS tras cambiar EMBEDDING_MODEL
	$(DC) exec celery-ai python manage.py rebuild_indices

prod-up:  ## Levanta el entorno de producción
	$(DC_PROD) up -d --build

prod-down:  ## Detiene el entorno de producción
	$(DC_PROD) down

clean:  ## Elimina contenedores y volúmenes (DESTRUCTIVO)
	$(DC) down -v --remove-orphans

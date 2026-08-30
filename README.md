# QA Router MCP

Локальный STDIO MCP-сервер для Codex Desktop. Gemma создаёт черновики QA-артефактов, а Hermes получает только явно подтверждённые обезличенные предпочтения.

## Граница данных

- Черновики идут напрямую в Ollama на `127.0.0.1`; Hermes не участвует в обработке Jira, кода и логов.
- Router отклоняет секреты и заменяет Jira-ключи, URL, email, commit hash, branch и локальные пути.
- Максимальный входной пакет — 40 000 символов.
- Логи router содержат только имя инструмента, результат, длительность и категорию ошибки.
- Предложения хранятся в `~/.qa-router/proposals.json`: каталог `0700`, файл `0600`.
- Codex остаётся ответственным за доказательства, финальное покрытие, severity, release readiness, изменения кода и внешние операции.

## Инструменты

- `draft_test_cases` — сфокусированные черновики тест-кейсов и чек-листов.
- `summarize_logs` — группировка видимых сигнатур без неподтверждённого root cause.
- `draft_automation_skeleton` — не записывающий файлы skeleton по переданному паттерну.
- `list_learning_proposals` — список обезличенных предложений.
- `approve_learning_proposal` — отправка предложения в Hermes memory после явного подтверждения.
- `reject_learning_proposal` — удаление предложения без вызова Hermes.

## Локальная установка

```bash
cd /Users/andreiviarshko/Projects/qa-router-mcp
uv sync
uv run pytest -q
uv run ruff check .
```

Модель:

```bash
ollama list
```

Ожидаемая запись: `gemma4:12b-it-q4_K_M`.

Запуск Ollama с проверенным профилем:

```bash
OLLAMA_CONTEXT_LENGTH=64000 \
OLLAMA_FLASH_ATTENTION=1 \
OLLAMA_KV_CACHE_TYPE=q8_0 \
OLLAMA_NUM_PARALLEL=1 \
/opt/homebrew/bin/ollama serve
```

## Codex Desktop

Скопировать routing skill:

```bash
mkdir -p /Users/andreiviarshko/.codex/skills/qa-local-routing
cp codex/skills/qa-local-routing/SKILL.md \
  /Users/andreiviarshko/.codex/skills/qa-local-routing/SKILL.md
```

Добавить один блок в `/Users/andreiviarshko/.codex/config.toml`:

```toml
[mcp_servers.qa-router]
command = "/Users/andreiviarshko/Projects/qa-router-mcp/scripts/qa-router-mcp"
args = []
startup_timeout_sec = 30
tool_timeout_sec = 60
```

После изменения перезапустить Codex Desktop.

## Fallback

`local_delegation_disabled`, `ollama_invalid_response`, `ollama_invalid_schema`, `hermes_timeout`, `hermes_failed` и `explicit_approval_required` возвращают управление Codex. Для невалидного JSON допускается ровно одна repair-попытка.

## Отключение

```bash
mkdir -p /Users/andreiviarshko/.qa-router
touch /Users/andreiviarshko/.qa-router/disabled
```

После перезапуска Codex router отвечает `local_delegation_disabled`. Для включения удалить только marker-файл:

```bash
rm /Users/andreiviarshko/.qa-router/disabled
```

## Удаление интеграции

1. Удалить блок `[mcp_servers.qa-router]` из Codex config.
2. Удалить каталог `/Users/andreiviarshko/.codex/skills/qa-local-routing`.
3. Перезапустить Codex Desktop.

Репозиторий и `/Users/andreiviarshko/.qa-router` остаются локально для ручной проверки. Проект не требует push, GitLab, GitHub или публикации.

## Проверенный baseline

На MacBook Pro M5 Pro с 24 GB: Ollama `0.33.0`, Hermes `0.20.6`, Gemma `gemma4:12b-it-q4_K_M`, контекст 64K, `think=false`, flash attention, KV cache `q8_0`, одна параллельная генерация. Во время замеров swap оставался нулевым, свободная память — около 35–39%; live structured router draft занял 3,2–3,4 секунды, warm Hermes-запрос — 1,5 секунды, cold Hermes-запрос с тремя кейсами — 16,1 секунды.

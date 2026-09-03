# QA Router MCP

[English](README.md) | [Deutsch](README.de.md) | **Русский** | [Español](README.es.md)

Локальный MCP-сервер с защитой данных, который передаёт ограниченные и обезличенные черновые QA-задачи из Codex в Qwen3.5-9B через LM Studio и MLX. Codex остаётся главным оркестратором и отвечает за сбор доказательств, итоговую QA-оценку, изменения кода и все записи во внешние системы.

![Архитектура QA-процесса](docs/assets/qa-workflow-architecture.png)

## Архитектура

- **Главный оркестратор:** Codex с GPT-5.6 Terra и уровнем reasoning `medium`.
- **Локальные рутинные черновики:** Qwen3.5-9B через LM Studio/MLX, доступный только по loopback.
- **Сложная эскалация:** один опциональный read-only агент `qa_deep` на GPT-5.6 Sol с reasoning `high`.
- **Системы-источники:** Jira, GitLab, TestRail, Sentry, Grafana, OpenSearch, Slack и Confluence остаются под управлением Codex через соответствующие MCP-интеграции.
- **Навигация по коду:** Codex использует CodeGraph, если для проекта существует подходящий индекс.

Router не обучает модель, не хранит историю диалога и не создаёт постоянную QA-память. Каждый локальный результат считается непроверенным черновиком и должен быть проверен Codex.

## Что передаётся локально

| Инструмент | Назначение | Лимит входа | Максимальный выход |
|---|---|---:|---:|
| `draft_test_cases` | Разворачивает утверждённую Terra coverage map в текст тест-кейсов | 20 000 символов | 3 072 токена |
| `summarize_logs` | Группирует видимые сигнатуры логов без выдумывания причин | 40 000 символов | 1 536 токенов |
| `draft_automation_skeleton` | Создаёт не записывающий файлы skeleton по явному паттерну проекта | 20 000 символов | 3 072 токена |
| `translate_text` | Переводит обезличенный текст с сохранением терминологии | 12 000 символов | 1 536 токенов |
| `rewrite_text` | Сокращает, исправляет или меняет стиль без добавления фактов | 12 000 символов | 1 536 токенов |
| `explain_short` | Кратко объясняет стабильную тему | 6 000 символов | 512 токенов |
| `summarize_text` | Создаёт выжимку только из переданного источника | 24 000 символов | 2 048 токенов |

Автоматическая маршрутизация намеренно выборочная:

- 4–12 тест-кейсов;
- логи от 6 000 символов;
- source-bound summary от 4 000 символов;
- перевод или rewrite от 2 000 символов;
- automation skeleton только при наличии явного проектного паттерна и многошагового сценария.

Меньшие задачи остаются в Terra. `explain_short` используется локально только по явному запросу. Явный запрос локальной модели может переопределить порог размера, но не policy-ограничения.

## Границы безопасности

- Секреты и признаки PII или платёжных данных отклоняются.
- Ключи задач, URL, email, commit hash, ветки и локальные пути заменяются до локального запроса.
- Полный обезличенный prompt токенизируется выбранной локальной моделью до генерации.
- Prompt, адаптивный выходной бюджет и резерв 512 токенов должны помещаться в проверенный контекст 16K.
- Логи содержат только метаданные и счётчики, но не текст запросов или ответов.
- Нельзя передавать credentials, cookies, tokens, персональные или платёжные данные, полные репозитории и неограниченные корпоративные документы.
- Codex проверяет evidence, coverage, severity, release readiness, изменения кода и внешние действия.

## Требования

- macOS на Apple Silicon;
- Python 3.12 или новее;
- [`uv`](https://docs.astral.sh/uv/);
- LM Studio с CLI `lms`;
- Codex Desktop;
- модель `qwen/qwen3.5-9b`, загруженная в LM Studio.

## Установка

### 1. Клонирование и проверка

```bash
git clone https://github.com/Rbkmen/qa-router-mcp.git
cd qa-router-mcp
uv sync
uv run pytest -q
uv run ruff check .
```

### 2. Запуск локального runtime

При необходимости установи официальный headless runtime LM Studio:

```bash
curl -fsSL https://lmstudio.ai/install.sh | bash
lms daemon up
lms server start
```

Проверь наличие модели:

```bash
lms ls
```

Загрузи эталонный профиль:

```bash
lms load qwen/qwen3.5-9b \
  --context-length 16384 \
  --gpu max \
  --parallel 1 \
  --ttl 300 \
  -y
```

API должен слушать только `127.0.0.1:1234`. JIT-загрузка позволяет загрузить модель при первом запросе и выгрузить после пяти минут бездействия.

### 3. Опционально: запуск llmster при входе в систему

```bash
mkdir -p "$HOME/Library/LaunchAgents"
cp launchd/com.qa-router.llmster.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.qa-router.llmster.plist"
```

### 4. Установка routing skill для Codex

```bash
mkdir -p "$HOME/.codex/skills/qa-local-routing"
cp codex/skills/qa-local-routing/SKILL.md \
  "$HOME/.codex/skills/qa-local-routing/SKILL.md"
```

### 5. Регистрация MCP-сервера в Codex

Получи абсолютный путь клона командой `pwd`, затем добавь следующий блок в конфигурацию Codex:

```toml
[mcp_servers.qa-router]
command = "/absolute/path/to/qa-router-mcp/scripts/qa-router-mcp"
args = []
startup_timeout_sec = 30
tool_timeout_sec = 120
```

После изменения конфигурации перезапусти Codex Desktop.

## Настройка runtime

Launcher использует безопасные значения по умолчанию и поддерживает следующие переменные окружения:

| Переменная | Значение по умолчанию |
|---|---|
| `QA_ROUTER_MODEL` | `qwen/qwen3.5-9b` |
| `QA_ROUTER_CONTEXT` | `16384` |
| `QA_ROUTER_MAX_OUTPUT` | `3072` |
| `QA_ROUTER_LMSTUDIO_URL` | `http://127.0.0.1:1234` |
| `QA_ROUTER_TIMEOUT` | `90` |
| `QA_ROUTER_TTL_SECONDS` | `300` |
| `QA_ROUTER_CONTEXT_RESERVE` | `512` |
| `QA_ROUTER_DATA_DIR` | `$HOME/.qa-router` |

Модель, контекст, loopback endpoint и последовательная генерация зафиксированы в проверенном профиле.

## Валидация и fallback

- Transport-ошибка повторяется один раз.
- Для невалидного JSON допускается не более одной schema-repair попытки.
- Для неполного QA-черновика допускается не более одной semantic-repair попытки.
- Результат с тест-кейсами должен соответствовать длине coverage map и обязательным полям.
- Automation skeleton отклоняется при наличии явных записей во внешние системы.
- Ошибки policy, контекстного бюджета, tokenizer, transport, truncation, schema и validation возвращают управление Codex.

## Метрики

Обезличенные рабочие события сохраняются в `$HOME/.qa-router/metrics.jsonl`. Текст prompt, черновики, ключи задач, код, логи и пути не записываются.

Сформировать отчёт за семь дней:

```bash
uv run qa-router-report
```

Запустить опциональный live regression benchmark из 28 сценариев:

```bash
QA_ROUTER_BENCHMARK=1 uv run pytest -q tests/test_live_benchmark.py -s
```

Сохранить benchmark-метрики рядом с interactive-метриками:

```bash
QA_ROUTER_DATA_DIR="$HOME/.qa-router" \
QA_ROUTER_BENCHMARK=1 \
uv run pytest -q tests/test_live_benchmark.py -s
```

## Отключение локальной маршрутизации

```bash
mkdir -p "$HOME/.qa-router"
touch "$HOME/.qa-router/disabled"
```

Перезапусти Codex Desktop. Для повторного включения удали marker-файл.

## Удаление интеграции

1. Выполни boot out для `com.qa-router.llmster` и удали plist из `$HOME/Library/LaunchAgents`.
2. Удали блок `[mcp_servers.qa-router]` из конфигурации Codex.
3. Удали `$HOME/.codex/skills/qa-local-routing`.
4. Перезапусти Codex Desktop.

## Эталонный профиль

Текущий regression-профиль использует Qwen3.5-9B 4-bit, логический контекст 16K, одну последовательную генерацию, отключённый thinking и TTL 300 секунд. Он проверен на Apple Silicon с 24 GB unified memory, LM Studio 0.4.23 и MLX runtime 1.11.0.

Live regression suite проверяет структуру результата, соблюдение policy, source-bound поведение, fallback-контракты и отсутствие постоянной application memory. Она не заменяет экспертное QA-ревью.

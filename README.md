# QA Router MCP

Локальный STDIO MCP-сервер для Codex Desktop. Qwen создаёт только
ограниченные черновики QA-артефактов и безопасных текстовых задач. Codex остаётся
единственным оркестратором и принимает финальные решения.

## Архитектура

- Основной чат: `gpt-5.6-terra` с `medium` reasoning.
- Локальная рутина: `qwen/qwen3.5-9b` через loopback LM Studio/llmster и MLX.
- Сложный анализ: один read-only `qa_deep` на `gpt-5.6-sol` с `high` reasoning.
- Router не обучает модель, не ведёт application-level историю и не создаёт постоянную QA-память.
- Jira, GitLab, TestRail, Sentry, Grafana и OpenSearch остаются за Codex и соответствующими MCP.

## Граница данных

- Router отклоняет секреты и заменяет Jira-ключи, URL, email, commit hash, branch и локальные пути.
- Входные и выходные бюджеты задаются отдельно для каждого инструмента; общий
  верхний предел входа — 40 000 символов.
- После sanitization router считает полный prompt точным tokenizer выбранной модели
  через локальный LM Studio. Запрос
  уходит в модель, только если prompt + выходной бюджет + резерв 512 tokens
  укладываются в проверенный контекст 16K; иначе возвращается
  `token_budget_exceeded` без вызова backend.
- Логи содержат только время, имя инструмента, маршрут, результат, длительность,
  счётчики токенов/запросов и категорию ошибки. Текст запросов и ответов не пишется.
- Нельзя передавать credentials, cookies, tokens, персональные или платёжные данные, полные репозитории и неограниченные корпоративные документы.
- Codex проверяет каждый локальный результат и отвечает за evidence, coverage, severity, release readiness, изменения кода и внешние операции.

## Инструменты

- `draft_test_cases` — сфокусированные черновики тест-кейсов и чек-листов.
- `summarize_logs` — группировка видимых сигнатур без неподтверждённого root cause.
- `draft_automation_skeleton` — не записывающий файлы skeleton по переданному паттерну.
- `translate_text` — перевод обезличенного текста с сохранением терминов.
- `rewrite_text` — сокращение, исправление или изменение стиля без новых фактов.
- `explain_short` — краткое объяснение стабильной темы без внешнего исследования.
- `summarize_text` — выжимка только из переданного текста.

| Инструмент | Вход, символов | Максимальный выход, tokens |
|---|---:|---:|
| `draft_test_cases` | 20 000 | 3 072 |
| `summarize_logs` | 40 000 | 1 536 |
| `draft_automation_skeleton` | 20 000 | 3 072 |
| `translate_text` / `rewrite_text` | 12 000 | 1 536 |
| `explain_short` | 6 000 | 512 |
| `summarize_text` | 24 000 | 2 048 |

Router v5 выбирает фактический выходной бюджет ниже этого потолка:

- тест-кейсы: 1–3 — 1 024, 4–6 — 2 048, 7–12 — 3 072 tokens;
- automation skeleton: до 6 000 символов — 1 536, больше — 3 072;
- summary: до 6 000 символов — 768, больше — 2 048;
- логи: до 8 000 символов — 768, до 24 000 — 1 024, больше — 1 536;
- перевод и rewrite: до 1 000 символов — 512, до 6 000 — 1 024,
  больше — 1 536;
- короткое объяснение — 512 tokens.

Глобальный `QA_ROUTER_MAX_OUTPUT` остаётся последним верхним ограничителем.

## Локальная установка

```bash
cd /Users/andreiviarshko/Projects/qa-router-mcp
uv sync
uv run pytest -q
uv run ruff check .
```

Установить официальный headless runtime и запустить локальный API:

```bash
curl -fsSL https://lmstudio.ai/install.sh | bash
lms daemon up
lms server start
```

Ожидаемые MLX-модели:

```bash
lms ls
```

- `qwen/qwen3.5-9b` — основной маршрут.

Проверенный профиль:

```bash
lms load qwen/qwen3.5-9b \
  --context-length 16384 \
  --gpu max \
  --parallel 1 \
  --ttl 300 \
  -y
```

JIT загрузка включена: первая задача загружает выбранную модель, неактивная модель
выгружается через пять минут, а при переключении остаётся только последняя JIT-модель.
API слушает только `127.0.0.1:1234`; CORS, запись файловых server logs и вывод
содержимого запросов отключены.

Для запуска llmster при входе в macOS используется
`launchd/com.qa-router.llmster.plist`.

```bash
cp launchd/com.qa-router.llmster.plist \
  /Users/andreiviarshko/Library/LaunchAgents/com.qa-router.llmster.plist
launchctl bootstrap gui/$(id -u) \
  /Users/andreiviarshko/Library/LaunchAgents/com.qa-router.llmster.plist
```

## Codex Desktop

Установить routing skill:

```bash
mkdir -p /Users/andreiviarshko/.codex/skills/qa-local-routing
cp codex/skills/qa-local-routing/SKILL.md \
  /Users/andreiviarshko/.codex/skills/qa-local-routing/SKILL.md
```

Конфигурация MCP:

```toml
[mcp_servers.qa-router]
command = "/Users/andreiviarshko/Projects/qa-router-mcp/scripts/qa-router-mcp"
args = []
startup_timeout_sec = 30
tool_timeout_sec = 120
```

После изменения конфигурации перезапустить Codex Desktop.

## Fallback

`local_delegation_disabled`, `token_budget_exceeded`, `local_tokenizer_error`,
`requested_case_count_too_large`,
`local_model_invalid_response`,
`local_model_invalid_schema`, `local_model_invalid_draft`, `local_model_truncated`
и `local_model_transport_error` возвращают
управление Codex.

- Transport-ошибка повторяется один раз; policy- и response-ошибки не повторяются.
- Для невалидного JSON допускается одна schema-repair попытка.
- Для неполного QA-черновика допускается одна semantic-repair попытка.
- `draft_test_cases` проверяет число кейсов и наличие Title, Preconditions, Steps и
  Expected Result у каждого кейса. Запросы свыше 12 кейсов возвращаются Codex для
  разбиения на меньшие пакеты.
- `explain_short` проверяется на лимит 120 слов, а automation skeleton — на отсутствие
  явных внешних записей.

## Метрики и regression gate

Обезличенные события сохраняются в `~/.qa-router/metrics.jsonl`. Короткий отчёт за
последние семь дней:

```bash
cd /Users/andreiviarshko/Projects/qa-router-mcp
.venv/bin/qa-router-report
```

События Router v5 помечаются моделью, версией профиля и источником
`interactive`, `benchmark` или `smoke`. Отчёт показывает отдельно для каждого
источника, модели и профиля: outcomes, оценку входного бюджета, фактические
prompt/output tokens, число запросов и p50/p95 длительности. Старые события
остаются читаемыми в группе `legacy`; текст запросов и ответов не сохраняется.
Отчёт не является QA-памятью.
Токены Terra/Sol router измерить не может, поэтому экономию нужно оценивать сравнением
одинаковых задач в Codex.

Regression corpus содержит четыре synthetic sanitized примера для каждого из семи
инструментов, а также отдельные policy/fallback проверки. Он запускается вместе с
`pytest` после изменения модели, prompt или routing-кода.

Полный opt-in прогон всех 28 примеров через Qwen:

```bash
QA_ROUTER_BENCHMARK=1 uv run pytest -q tests/test_live_benchmark.py -s
```

Чтобы сохранить benchmark рядом с interactive-метриками для сравнения в отчёте:

```bash
QA_ROUTER_DATA_DIR=/Users/andreiviarshko/.qa-router \
QA_ROUTER_BENCHMARK=1 \
uv run pytest -q tests/test_live_benchmark.py -s
```

Он намеренно не запускается по умолчанию. Сравнение с прямым Terra остаётся ручным:
локальный router не имеет доступа к usage основного Codex-чата.

## Отключение

```bash
mkdir -p /Users/andreiviarshko/.qa-router
touch /Users/andreiviarshko/.qa-router/disabled
```

После перезапуска router отвечает `local_delegation_disabled`. Для включения удалить marker-файл.

## Удаление интеграции

1. Остановить LaunchAgent `com.qa-router.llmster`.
2. Удалить его plist из `~/Library/LaunchAgents`.
3. Удалить блок `[mcp_servers.qa-router]` из Codex config.
4. Удалить skill `~/.codex/skills/qa-local-routing`.
5. Перезапустить Codex Desktop.

Репозиторий локальный: push, GitLab, GitHub и публикация не требуются.

## Проверенный профиль

MacBook Pro M5 Pro с 24 GB unified memory, LM Studio `0.4.23`, MLX runtime `1.11.0`,
контекст router 16K, thinking отключён, router сериализует генерации, TTL 300 секунд.

У MLX runtime контекст выделяется динамически, поэтому `lms ps` может показывать
автоматически рассчитанный максимум выше 16K. Фактическую границу router сохраняют
отдельные входные бюджеты: максимальный проверенный пакет укладывается в логический
профиль 16K.

Live benchmark использует 28 synthetic sanitized примеров: по четыре для каждого из
семи инструментов. Это regression gate формата, policy и source-bounded поведения,
но не замена экспертной QA-оценке результата. Отдельно проверяются secret refusal,
fallback-контракт и отсутствие постоянной памяти.

Проверенный Qwen baseline 2026-09-02:

- 28/28 основных сценариев за 58,46 секунды на прогретой модели;
- 3/3 расширенных сценария за 30,25 секунды: восемь тест-кейсов, 30 525 символов
  логов и 17 420 символов source-bound summary;
- 20 000 символов плотного synthetic ASCII корректно отклонены до генерации:
  exact prompt count 14 992 tokens, backend requests — 0;
- холодная загрузка после установки runtime — 7,64 секунды, размер загруженной
  модели — 5,57 GiB;
- все 31 генерация прошла без repair, fallback и truncation.

Качественный synthetic spot-check подтверждает ту же границу: Qwen лучше отмечает
неподтверждённые допущения, группирует повторяющиеся log signatures и сохраняет смысл
короткого rewrite. Automation skeleton любой локальной модели остаётся только
непроверенным черновиком: Codex обязан сверить реальные API, helpers и паттерны проекта.

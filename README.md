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

- Router отклоняет секреты и признаки PII/payment data, включая player/session ID,
  IP, UUID, телефон, PAN/card number и IBAN. Jira-ключи, URL, email, commit hash,
  branch и локальные пути заменяются до локального вызова.
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

- `draft_test_cases` — разворачивает утверждённую Terra coverage map в черновики
  тест-кейсов; не выбирает покрытие самостоятельно.
- `summarize_logs` — группировка видимых сигнатур без неподтверждённого root cause.
- `draft_automation_skeleton` — не записывающий файлы skeleton по переданному паттерну.
- `translate_text` — перевод обезличенного текста с сохранением терминов.
- `rewrite_text` — сокращение, исправление или изменение стиля без новых фактов.
- `explain_short` — краткое объяснение стабильной темы без внешнего исследования.
- `summarize_text` — выжимка только из переданного текста.
- `record_canary_feedback` — обезличенная оценка проверенного локального черновика;
  принимает выданный `draft_id`, результат проверки и категорию основной правки.
- `record_qa_task_outcome` — одна обезличенная итоговая запись QA-задачи: тип и
  результат задачи, счётчики source MCP/CodeGraph, Qwen/Sol, findings и повторных чтений.

| Инструмент | Вход, символов | Максимальный выход, tokens |
|---|---:|---:|
| `draft_test_cases` | 20 000 | 3 072 |
| `summarize_logs` | 40 000 | 1 536 |
| `draft_automation_skeleton` | 20 000 | 3 072 |
| `translate_text` / `rewrite_text` | 12 000 | 1 536 |
| `explain_short` | 6 000 | 512 |
| `summarize_text` | 24 000 | 2 048 |

Router v9 выбирает фактический выходной бюджет ниже этого потолка:

- тест-кейсы: 1–3 — 1 024, 4–6 — 2 048, 7–12 — 3 072 tokens;
- automation skeleton: до 6 000 символов — 1 536, больше — 3 072;
- summary: до 6 000 символов — 768, больше — 2 048;
- логи: до 8 000 символов — 768, до 24 000 — 1 024, больше — 1 536;
- перевод и rewrite: до 1 000 символов — 512, до 6 000 — 1 024,
  больше — 1 536;
- короткое объяснение — 512 tokens.

Глобальный `QA_ROUTER_MAX_OUTPUT` остаётся последним верхним ограничителем.

Автоматическая маршрутизация отправляет в Qwen только задачи, достаточно большие,
чтобы локальный черновик экономил контекст основного чата:

- 4–12 тест-кейсов;
- логи от 6 000 символов;
- source-bound summary от 4 000 символов;
- перевод или rewrite от 2 000 символов;
- automation skeleton только при наличии явного проектного паттерна и
  многошагового сценария.

Меньшие задачи остаются в Terra. `explain_short` используется локально только по
явному запросу пользователя. Явный запрос локальной модели может переопределить
порог размера, но не policy-ограничения.

Перед `draft_test_cases` Terra определяет финальное покрытие и передаёт
`coverage_map` из 1–12 элементов — ровно один purpose/source/state branch/expected
invariant на кейс. Router выводит из длины карты точное количество кейсов, а Qwen
только заполняет Title, Preconditions, Steps и Expected Result. Дополнительные,
объединённые или потерянные сценарии исправляет Terra.

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
`sensitive_data_detected`,
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

События Router v9 помечаются моделью, версией профиля и источником
`interactive`, `benchmark` или `smoke`. Отчёт показывает отдельно для каждого
источника, модели и профиля: outcomes, оценку входного бюджета, фактические
prompt/output tokens, число запросов и p50/p95 длительности. Старые события
остаются читаемыми в группе `legacy`; текст запросов и ответов не сохраняется.
Отчёт не является QA-памятью.
Токены Terra/Sol router измерить не может, поэтому экономию нужно оценивать сравнением
одинаковых задач в Codex.

После завершения QA review/planning задачи Terra может записать одно событие
`qa_task_outcome`. Оно содержит только фиксированные категории и неотрицательные
счётчики: тип/result задачи, количество вызовов source MCP и CodeGraph, использование
Qwen/Sol, identified/confirmed/rejected findings, Qwen edits и повторные чтения
источника. Jira-ключи, названия, source text, код, логи, пути и черновики интерфейс
не принимает. Семидневный отчёт агрегирует эти записи отдельно в `qa_tasks`.

`source_mcp_calls` считает только обращения к источникам через Jira, GitLab,
TestRail, Sentry, Grafana, OpenSearch, Slack и Confluence MCP. CodeGraph, qa-router
и сама запись метрики в этот счётчик не входят.

Canary собирает ровно одну оценку для каждого выданного `draft_id`: `accepted`,
`edited` или `rejected` и, при правке/отклонении, одну категорию причины. Запись и
проверка выполняются под общим файловым lock, поэтому несколько чатов используют
единое состояние и не принимают дубли или feedback без соответствующего черновика.
Текст задачи и черновика в metrics не попадает.

Выборка каждой версии профиля из 50 оценок стратифицирована: 15 test-case, 10 log, 10 automation,
10 summary, 3 rewrite и 2 translation drafts. Маршрут перестаёт запрашивать
feedback после заполнения квоты текущей версии. Прогресс canary считается за всё
время отдельно для каждого `profile_version` и отдельно от семидневных
generation-метрик.

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

Проверка профиля Router v9 от 2026-09-03:

- 28/28 synthetic regression-сценариев прошли за 77,15 секунды без repair,
  fallback и truncation;
- live smoke подтвердил генерацию, `secret_detected` и `token_budget_exceeded` до
  обращения к генерации;
- `lms ps` показал Qwen3.5-9B 4-bit размером 5,98 GB и TTL 300 секунд;
- отдельный qualitative canary был отклонён как `factual`: Qwen добавил не заданные
  UI-сообщения и не пометил их `unverified`.

Поэтому проверка Terra — обязательная граница, а не формальность. Test cases и
automation skeleton остаются непроверенными черновиками: Codex сверяет каждый пункт
с coverage map, реальными API, helpers и паттернами проекта.

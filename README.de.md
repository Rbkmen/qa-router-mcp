# QA Router MCP

[English](README.md) | **Deutsch** | [Русский](README.ru.md) | [Español](README.es.md)

Ein datenschutzorientierter lokaler MCP-Server, der klar begrenzte und bereinigte QA-Entwurfsaufgaben aus Codex über LM Studio und MLX an Qwen3.5-9B delegiert. Codex bleibt der primäre Orchestrator und ist für Evidenzbeschaffung, abschließende QA-Bewertung, Codeänderungen und sämtliche Schreibvorgänge in externen Systemen verantwortlich.

![Architektur des QA-Workflows](docs/assets/qa-workflow-architecture.png)

## Architektur

- **Primärer Orchestrator:** Codex mit GPT-5.6 Terra und Reasoning-Stufe `medium`.
- **Lokale Routineentwürfe:** Qwen3.5-9B über LM Studio/MLX mit reinem Loopback-Zugriff.
- **Komplexe Eskalation:** ein optionaler schreibgeschützter `qa_deep`-Agent mit GPT-5.6 Sol und Reasoning-Stufe `high`.
- **Quellsysteme:** Jira, GitLab, TestRail, Sentry, Grafana, OpenSearch, Slack und Confluence bleiben über ihre MCP-Integrationen unter der Kontrolle von Codex.
- **Code-Navigation:** Codex verwendet CodeGraph, wenn ein passender Projektindex vorhanden ist.

Der Router trainiert das Modell nicht, speichert keinen Gesprächsverlauf und erstellt kein dauerhaftes QA-Gedächtnis. Jedes lokale Ergebnis ist ein ungeprüfter Entwurf, den Codex kontrollieren muss.

## Lokal weitergeleitete Aufgaben

| Tool | Zweck | Eingabelimit | Maximale Ausgabe |
|---|---|---:|---:|
| `draft_test_cases` | Erweitert eine von Terra genehmigte Coverage Map zu Testfalltexten | 20.000 Zeichen | 3.072 Tokens |
| `summarize_logs` | Gruppiert sichtbare Log-Signaturen, ohne Ursachen zu erfinden | 40.000 Zeichen | 1.536 Tokens |
| `draft_automation_skeleton` | Erstellt ein nicht schreibendes Gerüst nach einem expliziten Projektmuster | 20.000 Zeichen | 3.072 Tokens |
| `translate_text` | Übersetzt bereinigten Text unter Beibehaltung der Terminologie | 12.000 Zeichen | 1.536 Tokens |
| `rewrite_text` | Kürzt, korrigiert oder formuliert um, ohne Fakten hinzuzufügen | 12.000 Zeichen | 1.536 Tokens |
| `explain_short` | Erklärt ein stabiles Thema kurz | 6.000 Zeichen | 512 Tokens |
| `summarize_text` | Erstellt eine ausschließlich quellgebundene Zusammenfassung | 24.000 Zeichen | 2.048 Tokens |

Die automatische Weiterleitung ist bewusst selektiv:

- 4–12 Testfälle;
- Logs ab 6.000 Zeichen;
- quellgebundene Zusammenfassungen ab 4.000 Zeichen;
- Übersetzungen oder Umformulierungen ab 2.000 Zeichen;
- Automatisierungsgerüste nur mit einem expliziten Projektmuster und einem mehrstufigen Szenario.

Kleinere Aufgaben bleiben in Terra. `explain_short` wird nur auf ausdrücklichen Wunsch lokal verwendet. Eine explizite Anfrage an das lokale Modell kann Größenschwellen überschreiben, niemals jedoch Sicherheitsrichtlinien.

## Sicherheitsgrenzen

- Geheimnisse und Hinweise auf personenbezogene oder Zahlungsdaten werden abgewiesen.
- Ticket-Schlüssel, URLs, E-Mail-Adressen, Commit-Hashes, Branches und lokale Pfade werden vor einer lokalen Anfrage ersetzt.
- Der vollständige bereinigte Prompt wird vor der Generierung mit dem ausgewählten lokalen Modell tokenisiert.
- Prompt-Tokens, adaptives Ausgabebudget und eine Reserve von 512 Tokens müssen in den geprüften 16K-Kontext passen.
- Logs enthalten nur Metadaten und Zähler, niemals Prompt- oder Antworttexte.
- Zugangsdaten, Cookies, Tokens, personenbezogene oder Zahlungsdaten, vollständige Repositorys und uneingeschränkte Unternehmensdokumente dürfen niemals lokal weitergeleitet werden.
- Codex validiert Evidenz, Abdeckung, Schweregrad, Release-Bereitschaft, Codeänderungen und externe Aktionen.

## Voraussetzungen

- macOS auf Apple Silicon;
- Python 3.12 oder neuer;
- [`uv`](https://docs.astral.sh/uv/);
- LM Studio mit der `lms`-CLI;
- Codex Desktop;
- das in LM Studio heruntergeladene Modell `qwen/qwen3.5-9b`.

## Installation

### 1. Klonen und prüfen

```bash
git clone https://github.com/Rbkmen/qa-router-mcp.git
cd qa-router-mcp
uv sync
uv run pytest -q
uv run ruff check .
```

### 2. Lokale Laufzeit starten

Installiere bei Bedarf die offizielle Headless-Laufzeit von LM Studio:

```bash
curl -fsSL https://lmstudio.ai/install.sh | bash
lms daemon up
lms server start
```

Prüfe, ob das Modell verfügbar ist:

```bash
lms ls
```

Lade das Referenzprofil:

```bash
lms load qwen/qwen3.5-9b \
  --context-length 16384 \
  --gpu max \
  --parallel 1 \
  --ttl 300 \
  -y
```

Die API darf nur auf `127.0.0.1:1234` lauschen. Durch JIT-Laden wird das Modell bei der ersten Anfrage geladen und nach fünf Minuten Inaktivität entladen.

### 3. Optional: llmster bei der Anmeldung starten

```bash
mkdir -p "$HOME/Library/LaunchAgents"
cp launchd/com.qa-router.llmster.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.qa-router.llmster.plist"
```

### 4. Codex-Routing-Skill installieren

```bash
mkdir -p "$HOME/.codex/skills/qa-local-routing"
cp codex/skills/qa-local-routing/SKILL.md \
  "$HOME/.codex/skills/qa-local-routing/SKILL.md"
```

### 5. MCP-Server in Codex registrieren

Ermittle mit `pwd` den absoluten Pfad des Klons und füge der Codex-Konfiguration folgenden Block hinzu:

```toml
[mcp_servers.qa-router]
command = "/absolute/path/to/qa-router-mcp/scripts/qa-router-mcp"
args = []
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Starte Codex Desktop nach der Konfigurationsänderung neu.

## Laufzeitkonfiguration

Der Launcher verwendet sichere Standardwerte und akzeptiert folgende Umgebungsvariablen:

| Variable | Standardwert |
|---|---|
| `QA_ROUTER_MODEL` | `qwen/qwen3.5-9b` |
| `QA_ROUTER_CONTEXT` | `16384` |
| `QA_ROUTER_MAX_OUTPUT` | `3072` |
| `QA_ROUTER_LMSTUDIO_URL` | `http://127.0.0.1:1234` |
| `QA_ROUTER_TIMEOUT` | `90` |
| `QA_ROUTER_TTL_SECONDS` | `300` |
| `QA_ROUTER_CONTEXT_RESERVE` | `512` |
| `QA_ROUTER_DATA_DIR` | `$HOME/.qa-router` |

Modell, Kontext, Loopback-Endpunkt und serielle Generierung sind auf das geprüfte Profil festgelegt.

## Validierung und Fallback

- Transportfehler werden einmal wiederholt.
- Ungültiges JSON erhält höchstens einen Schema-Reparaturversuch.
- Unvollständige QA-Entwürfe erhalten höchstens einen semantischen Reparaturversuch.
- Die Testfallausgabe muss der Länge der Coverage Map und den Pflichtfeldern entsprechen.
- Automatisierungsgerüste mit expliziten externen Schreibvorgängen werden abgewiesen.
- Fehler bei Richtlinien, Kontextbudget, Tokenizer, Transport, Kürzung, Schema oder Validierung geben die Kontrolle an Codex zurück.

## Metriken

Anonymisierte Betriebsereignisse werden in `$HOME/.qa-router/metrics.jsonl` gespeichert. Prompt-Texte, Entwürfe, Ticket-Schlüssel, Code, Logs und Pfade werden nicht aufgezeichnet.

Sieben-Tage-Bericht erzeugen:

```bash
uv run qa-router-report
```

Optionalen Live-Regression-Benchmark mit 28 Fällen ausführen:

```bash
QA_ROUTER_BENCHMARK=1 uv run pytest -q tests/test_live_benchmark.py -s
```

Benchmark-Metriken gemeinsam mit interaktiven Metriken speichern:

```bash
QA_ROUTER_DATA_DIR="$HOME/.qa-router" \
QA_ROUTER_BENCHMARK=1 \
uv run pytest -q tests/test_live_benchmark.py -s
```

## Lokale Delegation deaktivieren

```bash
mkdir -p "$HOME/.qa-router"
touch "$HOME/.qa-router/disabled"
```

Starte Codex Desktop neu. Lösche die Marker-Datei, um die lokale Delegation wieder zu aktivieren.

## Integration deinstallieren

1. Entferne `com.qa-router.llmster` aus launchd und lösche die plist aus `$HOME/Library/LaunchAgents`.
2. Entferne den Block `[mcp_servers.qa-router]` aus der Codex-Konfiguration.
3. Entferne `$HOME/.codex/skills/qa-local-routing`.
4. Starte Codex Desktop neu.

## Referenzprofil

Das aktuelle Regressionsprofil verwendet Qwen3.5-9B 4-bit, einen logischen 16K-Kontext, eine serielle Generierung, deaktiviertes Thinking und eine TTL von 300 Sekunden. Es wurde auf Apple Silicon mit 24 GB Unified Memory, LM Studio 0.4.23 und MLX Runtime 1.11.0 validiert.

Die Live-Regressionssuite prüft Ausgabestruktur, Richtliniendurchsetzung, quellgebundenes Verhalten, Fallback-Verträge und das Fehlen eines dauerhaften Anwendungsspeichers. Sie ersetzt keine fachkundige QA-Prüfung.

# Agent Forge

AI-powered test generation agent that analyzes GitHub PR diffs, identifies untested code paths, generates targeted test cases, runs them, and self-corrects through a reflexion loop.

Built with **LangGraph** (Python) using a **Plan-and-Execute + Reflexion** architecture.

## How It Works

```
PR Diff → Code Analysis → Coverage Check → Test Generation → Test Execution → Self-Correction
```

1. **Fetches** the PR diff from GitHub via `gh` CLI
2. **Parses** changed files with [tree-sitter](https://tree-sitter.github.io/) to extract method signatures, annotations, and dependencies
3. **Detects** the build tool (Gradle/Maven) and existing test coverage
4. **Generates** targeted JUnit 5 test cases using GPT-4o, based on uncovered code paths
5. **Compiles and runs** the tests using the project's own build tool (`./gradlew test`)
6. **Self-corrects** — if tests fail, the critic analyzes errors and the generator fixes them (up to 3 iterations)

## Prerequisites

- **Python 3.12+**
- **GitHub CLI** (`gh`) — authenticated
- **Java 21** — for running generated tests against Java projects
- **OpenAI API key** — for LLM-powered test generation

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/rkp4u/test_agent.git
cd test_agent
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
make dev
```

Or manually:

```bash
pip install -e ".[dev]"
```

### 4. Configure environment

Copy the example and add your OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENAI_API_KEY=sk-proj-your-key-here
```

### 5. Authenticate GitHub CLI

```bash
brew install gh    # macOS
gh auth login      # follow the prompts
```

Verify:

```bash
gh auth status
```

## Usage

### Full pipeline — analyze, generate, run, and report

```bash
agent-forge run owner/repo --pr 42
```

### With verbose output

```bash
agent-forge run owner/repo --pr 42 -v
```

### Example output

```
╭─────────────────── Agent Forge — Test Generation ────────────────────╮
│ Repository: rkp4u/agent_demo                                         │
│ PR: #1 — Add TransactionMetrics for investigation performance        │
╰──────────────────────────────────────────────────────────────────────╯

  ✓ [1/7] Planning
  ✓ [2/7] Fetching PR diff (1 files changed)
  ✓ [3/7] Analyzing code (tree-sitter)
    ├── 6 new/modified methods found
  ✓ [4/7] Checking existing coverage
    ├── Existing: 0% line coverage
    └── 1/1 changed files have no test file
  ✓ [5/7] Generating tests
    ├── 1 test files generated
    └── 7 test methods targeting uncovered paths
  ✓ [6/7] Running tests
    ├── 5 passed, 2 failed
    └── Entering reflexion loop...
  ✓ [5/7] Regenerating tests (iteration 2/3)
  ✓ [6/7] Running tests
    ├── 7 passed, 0 failed
    └── All tests passing
  ✓ [7/7] Generating report

╭────────────────────────── Results ───────────────────────────────────╮
│ Tests generated:  7 (in 1 files)                                     │
│ Iterations:       2/3                                                │
│ Results:          7 passed, 0 failed ✓                               │
╰──────────────────────────────────────────────────────────────────────╯
```

### CLI commands

| Command | Description |
|---|---|
| `agent-forge run <repo> --pr <num>` | Full pipeline: analyze, generate, run, report |
| `agent-forge analyze <repo> --pr <num>` | Analysis only (no test generation) |
| `agent-forge version` | Show version |

### CLI options

| Option | Description |
|---|---|
| `--pr`, `-p` | PR number (required) |
| `--max-iterations`, `-m` | Max reflexion iterations (default: 3) |
| `--verbose`, `-v` | Show detailed output |
| `--dry-run` | Analyze and generate without running tests |

## Architecture

```
                                      Plan-and-Execute + Reflexion

START → [Planner] → [Diff Fetcher] → [Code Analyzer] → [Coverage Checker] → [Test Generator]
                                                                                    ↓
                                                                              [Test Runner]
                                                                                    ↓
                                                                                [Critic]
                                                                              ↙        ↘
                                                                     (fail)              (pass)
                                                                       ↓                   ↓
                                                              [Test Generator]        [Reporter] → END
                                                               (reflexion)
```

**Key design decisions:**
- **LangGraph** for stateful workflow orchestration with conditional edges
- **tree-sitter** for multi-language AST parsing (Java supported, Python/TypeScript planned)
- **gh CLI** for GitHub auth — no tokens stored in code
- **Reflexion loop** capped at 3 iterations to balance quality vs. cost

## Project Structure

```
src/agent_forge/
├── cli/                    # Typer CLI with Rich terminal output
│   ├── app.py              # Commands: run, analyze, version
│   └── display.py          # Rich panels, progress, tables
├── config/                 # Pydantic Settings (.env + yaml + CLI)
├── engine/
│   ├── graph.py            # LangGraph StateGraph definition
│   ├── state.py            # AgentState TypedDict
│   ├── nodes/              # 8 graph nodes (planner, diff_fetcher, etc.)
│   └── prompts/            # LLM prompt templates
├── tools/
│   ├── github/             # GitHub client (gh CLI + PyGithub fallback)
│   ├── analysis/           # tree-sitter AST analyzer + language handlers
│   ├── coverage/           # Build tool detector, JaCoCo parser (planned)
│   ├── runners/            # Gradle/Maven test runners
│   └── static_analysis/    # Semgrep integration (planned: pen testing)
└── models/                 # Dataclasses: CodeAnalysis, TestPlan, RunReport
```

## Configuration

Agent Forge reads configuration from multiple sources (lowest to highest priority):

1. Built-in defaults
2. `.env` file in the project directory
3. Environment variables with `AGENT_FORGE_` prefix
4. CLI flags

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | (required) |
| `AGENT_FORGE_MODEL` | LLM model | `gpt-4o` |
| `AGENT_FORGE_TEMPERATURE` | LLM temperature | `0.2` |
| `AGENT_FORGE_MAX_REFLEXION_ITERATIONS` | Max retry loops | `3` |
| `AGENT_FORGE_TEST_TIMEOUT_SECONDS` | Test execution timeout | `300` |
| `GITHUB_TOKEN` | GitHub PAT (fallback if gh CLI unavailable) | (optional) |

## Supported Languages

| Language | AST Parsing | Test Generation | Test Execution |
|---|---|---|---|
| Java (JUnit 5 + Mockito) | ✅ tree-sitter | ✅ GPT-4o | ✅ Gradle |
| Python (pytest) | Planned | Planned | Planned |
| TypeScript (Jest) | Planned | Planned | Planned |
| Kotlin (JUnit 5) | Planned | Planned | Planned |

## Development

### Running tests

```bash
make test          # Unit tests
make test-all      # All tests
make test-e2e      # End-to-end (requires API keys)
```

### Linting and formatting

```bash
make lint          # Check with ruff
make format        # Auto-fix with ruff
make typecheck     # mypy type checking
```

## Roadmap

- [ ] JaCoCo coverage collection (real line-level coverage deltas)
- [ ] Maven runner support
- [ ] Python + TypeScript language handlers
- [ ] `--output json` for CI integration
- [ ] Report persistence and `agent-forge report <id>` command
- [ ] GitHub Actions integration
- [ ] Penetration testing agent profile (semgrep-based)
- [ ] Web UI with streaming progress

## License

Apache 2.0

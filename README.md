# Agent Forge

AI-powered test generation agent that analyzes GitHub PR diffs, identifies untested code paths, generates targeted tests, runs them, and self-corrects through a reflexion loop.

Two modes: **coverage** (fill gaps in existing tests) and **mutation** (find bugs your tests miss).

Built with **LangGraph** (Python) using a **Plan-and-Execute + Reflexion** architecture, inspired by Meta's Automated Compliance Hardening (ACH) research.

---

## Modes

### Coverage Mode (default)
Generates tests targeting uncovered code paths. Measures line coverage and improves it.

```bash
agent-forge run owner/repo --pr 42
# or explicitly:
agent-forge run owner/repo --pr 42 --mode coverage
```

### Mutation Mode
Injects realistic bugs into changed code, runs existing tests to find which bugs go undetected (surviving mutants), then generates targeted killing tests to catch them. Reports a **mutation score** — a better quality metric than line coverage.

```bash
agent-forge run owner/repo --pr 42 --mode mutation
```

---

## How It Works

### Coverage Pipeline

```
PR Diff → Code Analysis → Coverage Check → Test Generation → Test Execution → Self-Correction → Report
```

1. **Fetches** the PR diff from GitHub
2. **Parses** changed files with [tree-sitter](https://tree-sitter.github.io/) to extract method signatures, annotations, and dependencies
3. **Detects** the build tool (Gradle/Maven) and existing test coverage
4. **Generates** targeted JUnit 5 tests using GPT-4o, based on uncovered code paths
5. **Compiles and runs** tests using `./gradlew test`
6. **Self-corrects** — if tests fail, a critic analyzes errors and the generator fixes them (up to 3 iterations)

### Mutation Pipeline (extends coverage)

```
[Coverage phase completes]
    ↓
Mutation Generator → Equivalence Detector → Mutation Runner
    ↓
Killing Test Generator → 3-Stage Filter → Mutation Critic → Report
```

7. **Generates mutations** — realistic bugs in changed code (off-by-one, wrong operator, missing null check, etc.) using `gpt-4o-mini` at temperature 0.7 — a *different* model/temperature than the test generator to prevent AI blind spots
8. **Filters equivalents** — LLM-as-judge removes mutations that are logically identical to original code
9. **Runs mutation tests** — injects each mutation, runs all tests, records killed vs. survived
10. **Generates killing tests** — for each surviving mutant, writes a test that *passes on original code* but *fails on the mutant*
11. **3-stage filter** — each killing test must: compile → pass original → fail mutant
12. **Reflexion loop** — up to 2 iterations to fix rejected killing tests

---

## Prerequisites

- **Python 3.12+**
- **GitHub CLI** (`gh`) — authenticated
- **Java 21** — for running generated tests against Java projects
- **OpenAI API key** — for LLM-powered test generation

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/rkp4u/test_agent.git
cd test_agent
python3 -m venv .venv
source .venv/bin/activate
make dev
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENAI_API_KEY=sk-proj-your-key-here
GITHUB_TOKEN=ghp_your-token-here   # optional, gh CLI preferred
```

### 3. Authenticate GitHub CLI

```bash
brew install gh    # macOS
gh auth login
gh auth status     # verify
```

---

## Usage

### Run coverage mode

```bash
agent-forge run owner/repo --pr 42
```

### Run mutation mode

```bash
agent-forge run owner/repo --pr 42 --mode mutation -v
```

### CLI options

| Option | Description | Default |
|---|---|---|
| `--mode` | `coverage` or `mutation` | `coverage` |
| `--pr`, `-p` | PR number (required) | — |
| `--max-iterations`, `-m` | Max reflexion iterations | `3` |
| `--verbose`, `-v` | Show detailed output | off |
| `--dry-run` | Analyze without running tests | off |

---

## Example Output

### Coverage mode

```
╭──────────────── Agent Forge — Test Generation ─────────────────╮
│ Repository: rkp4u/agent_demo                                    │
│ PR: #1 — Add TransactionMetrics for investigation performance   │
╰─────────────────────────────────────────────────────────────────╯

  ✓ [1/7] Planning
  ✓ [2/7] Fetching PR diff (1 files changed)
  ✓ [3/7] Analyzing code (tree-sitter)
    ├── 6 new/modified methods found
  ✓ [4/7] Checking existing coverage
  ✓ [5/7] Generating tests
    ├── 1 test files generated
    └── 7 test methods targeting uncovered paths
  ✓ [6/7] Running tests
    ├── 5 passed, 2 failed
    └── Entering reflexion loop...
  ✓ [5/7] Regenerating tests (iteration 2/3)
  ✓ [6/7] Running tests — 7 passed, 0 failed
  ✓ [7/7] Generating report

╭────────────────── Results ───────────────────╮
│ Tests generated:  7 (in 1 files)             │
│ Iterations:       2/3                        │
│ Results:          7 passed, 0 failed ✓       │
╰──────────────────────────────────────────────╯
```

### Mutation mode

```
  ✓ [1-7] Coverage phase (7 tests, all passing)
  ✓ [8/12] Generating mutations (6 mutants)
  ✓ [9/12] Filtering equivalent mutants (6 remain, 0 removed)
  ✓ [10/12] Running tests against mutants
    ├── 6 killed, 0 survived, 0 build failures
    └── All mutants caught by existing tests!
  ✓ [11/12] Generating killing tests (0 needed)
  ✓ [12/12] Generating report

╭──────────────── Mutation Testing Results ────────────────╮
│   Mutation score:  100% (6/6 mutants killed)             │
│ Killed by existing: 6                                    │
│ Killed by new tests: 0                                   │
│    Still surviving: 0                                    │
│  Equivalent (filtered): 0                               │
╰──────────────────────────────────────────────────────────╯
```

---

## Architecture

### Full graph (mutation mode)

```
START → Planner → Diff Fetcher → Code Analyzer → Coverage Checker
    → Test Generator → Test Runner → Critic
                                         ↙ (fail, max 3)    ↘ (pass)
                               Test Generator           [MODE ROUTER]
                                                      ↙               ↘
                                              (coverage)           (mutation)
                                                  ↓                    ↓
                                              Reporter        Mutation Generator
                                                 ↓                    ↓
                                                END         Equivalence Detector
                                                                       ↓
                                                            Mutation Runner
                                                                       ↓
                                                       Killing Test Generator
                                                                       ↓
                                                        Killing Test Runner
                                                                       ↓
                                                          Mutation Critic
                                                        ↙ (retry, max 2)  ↘ (done)
                                             Killing Test Generator      Reporter → END
```

**Key design decisions:**
- **LangGraph** for stateful workflow with conditional edges and two independent reflexion loops
- **Different models per phase** — mutation generator uses `gpt-4o-mini` at temp 0.7, test generator uses `gpt-4o` at temp 0.2 — prevents AI blind spots
- **String-based mutation injection** — replaces exact code snippets rather than line numbers for robustness
- **3-stage filter** for killing tests — compile → pass original → fail mutant (eliminates false positives)
- **tree-sitter** for multi-language AST parsing

---

## Project Structure

```
src/agent_forge/
├── cli/
│   ├── app.py              # Commands: run, analyze, version. --mode flag
│   └── display.py          # Rich panels, mutation score tables, surviving mutants
├── config/
│   └── settings.py         # All settings including mutation model/temperature
├── engine/
│   ├── graph.py            # LangGraph StateGraph with mode_router conditional edge
│   ├── state.py            # AgentState — 20+ fields including mutation state
│   ├── nodes/
│   │   ├── planner.py
│   │   ├── diff_fetcher.py
│   │   ├── code_analyzer.py
│   │   ├── coverage_checker.py
│   │   ├── test_generator.py
│   │   ├── test_runner.py
│   │   ├── critic.py
│   │   ├── reporter.py
│   │   ├── mutation_generator.py     # Generates realistic bugs via LLM
│   │   ├── equivalence_detector.py  # LLM-as-judge filtering
│   │   ├── mutation_runner.py        # Injects mutations, runs tests
│   │   ├── killing_test_generator.py # Generates bug-catching tests
│   │   ├── killing_test_runner.py    # 3-stage filter pipeline
│   │   └── mutation_critic.py        # Rule-based reflexion feedback
│   └── prompts/
│       ├── test_generation.py
│       └── mutation.py               # 6 prompt builders for mutation pipeline
├── tools/
│   ├── github/             # GitHub client (gh CLI + PyGithub fallback)
│   ├── analysis/           # tree-sitter AST analyzer
│   └── runners/
│       ├── gradle.py
│       └── mutation_injector.py      # Context manager: inject → test → restore
└── models/
    ├── ...
    └── mutation.py                   # Mutant, MutationRunResult, KillingTestResult
```

---

## Configuration

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | (required) |
| `GITHUB_TOKEN` | GitHub PAT (fallback if gh CLI unavailable) | (optional) |
| `AGENT_FORGE_MODEL` | Model for test generation | `gpt-4o` |
| `AGENT_FORGE_TEMPERATURE` | Temperature for test generation | `0.2` |
| `AGENT_FORGE_MAX_REFLEXION_ITERATIONS` | Coverage reflexion iterations | `3` |
| `AGENT_FORGE_TEST_TIMEOUT_SECONDS` | Test execution timeout (seconds) | `300` |
| `AGENT_FORGE_MUTATION_MODEL` | Model for mutation generation | `gpt-4o-mini` |
| `AGENT_FORGE_MUTATION_TEMPERATURE` | Temperature for mutation generation | `0.7` |
| `AGENT_FORGE_EQUIVALENCE_MODEL` | Model for equivalence detection | `gpt-4o-mini` |
| `AGENT_FORGE_MAX_MUTANTS_PER_PR` | Cap on mutations generated per PR | `12` |
| `AGENT_FORGE_MAX_MUTATION_ITERATIONS` | Killing test reflexion iterations | `2` |

---

## Model Strategy

| Node | Model | Temp | Rationale |
|---|---|---|---|
| Test generator | gpt-4o | 0.2 | Precision — tests must be syntactically correct |
| Mutation generator | gpt-4o-mini | 0.7 | Creative — different model prevents AI blind spots |
| Equivalence detector | gpt-4o-mini | 0.0 | Cheap binary classification |
| Killing test generator | gpt-4o | 0.2 | Precision — must compile and pass 3-stage filter |

Using the same model that writes tests to also generate mutations creates a systematic blind spot — it tends to generate bugs the model "knows" to avoid. Separating models is key to mutation effectiveness.

---

## Supported Languages

| Language | AST Parsing | Test Generation | Mutation Testing |
|---|---|---|---|
| Java (JUnit 5 + Gradle) | ✅ tree-sitter | ✅ GPT-4o | ✅ |
| Python (pytest) | Planned | Planned | Planned |
| TypeScript (Jest) | Planned | Planned | Planned |
| Kotlin (JUnit 5) | Planned | Planned | Planned |

---

## Roadmap

- [ ] JaCoCo coverage collection (real line-level coverage deltas)
- [ ] Maven runner support
- [ ] Python + TypeScript language handlers
- [ ] `--output json` for CI integration
- [ ] GitHub Actions integration — post mutation score as PR comment
- [ ] Report persistence and `agent-forge report <id>` command
- [ ] Penetration testing profile (semgrep-based static analysis)

---

## Development

```bash
make test          # Unit tests
make lint          # Check with ruff
make format        # Auto-fix with ruff
make typecheck     # mypy
```

---

## License

Apache 2.0

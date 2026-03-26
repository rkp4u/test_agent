"""Mutation testing data models."""

from dataclasses import dataclass, field


@dataclass
class Mutant:
    """A single code mutation (realistic bug) generated from the PR diff."""

    mutant_id: str              # "M001", "M002", ...
    file_path: str              # Relative path in repo
    original_code: str          # Exact snippet to find-and-replace
    mutated_code: str           # Replacement (the bug)
    mutation_description: str   # Human-readable: "Off-by-one in retry limit check"
    mutation_type: str          # "off_by_one" | "wrong_operator" | "missing_null_check" |
                                # "swapped_args" | "wrong_return" | "missing_boundary" |
                                # "wrong_exception" | "wrong_condition"
    line_start: int             # Approximate start line (informational)
    line_end: int               # Approximate end line (informational)
    is_equivalent: bool = False              # Set by equivalence detector
    equivalence_confidence: float = 0.0     # 0.0–1.0


@dataclass
class MutationRunResult:
    """Result of running the existing test suite against a single mutant."""

    mutant_id: str
    killed: bool                            # True if any test failed on this mutant
    killing_test: str | None = None         # Name of the test that killed it
    survived: bool = False                  # True if all tests passed (mutant undetected)
    build_failed: bool = False              # True if mutant itself didn't compile


@dataclass
class KillingTestResult:
    """Result of the 3-stage filter for a killing test candidate."""

    test_name: str
    mutant_id: str
    builds: bool = False            # Stage 1: test compiles
    passes_original: bool = False   # Stage 2: test passes on unmodified code
    fails_mutant: bool = False      # Stage 3: test fails on mutated code
    accepted: bool = False          # All 3 stages passed
    error_message: str = ""


@dataclass
class MutationReport:
    """Summary of the mutation testing phase."""

    total_mutants_generated: int
    equivalent_filtered: int
    mutants_tested: int
    killed_by_existing: int     # Killed by coverage-phase tests
    killed_by_new: int          # Killed by new killing tests
    survived: int               # Still surviving after both phases
    mutation_score: float       # (killed_by_existing + killed_by_new) / mutants_tested
    killing_tests: list[dict] = field(default_factory=list)
    surviving_mutant_details: list[dict] = field(default_factory=list)

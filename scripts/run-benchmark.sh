#!/usr/bin/env bash
# =============================================================================
# Local benchmark runner — fire and forget
# Usage: ./scripts/run-benchmark.sh [--mode mutation|coverage]
# Results written to: results/benchmark-<timestamp>/
# =============================================================================
set -euo pipefail

MODE="${1:-mutation}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/benchmark-${TIMESTAMP}"
mkdir -p "${RESULTS_DIR}"

# Default test matrix — edit as needed
declare -a REPOS=(
  "spring-projects/spring-petclinic:2310"
  "thombergs/buckpal:46"
  "google/gson:3000"
  "iluwatar/java-design-patterns:3454"
)

echo "============================================"
echo "  Agent Forge Benchmark"
echo "  Mode: ${MODE}"
echo "  Repos: ${#REPOS[@]}"
echo "  Output: ${RESULTS_DIR}/"
echo "============================================"
echo ""

SUMMARY_FILE="${RESULTS_DIR}/summary.md"
echo "| Repo | PR | Duration | Exit Code |" > "${SUMMARY_FILE}"
echo "|------|-----|----------|-----------|" >> "${SUMMARY_FILE}"

TOTAL_START=$(date +%s)

for entry in "${REPOS[@]}"; do
  REPO="${entry%%:*}"
  PR="${entry##*:}"
  SAFE_NAME=$(echo "${REPO}" | tr '/' '_')
  LOG_FILE="${RESULTS_DIR}/${SAFE_NAME}_pr${PR}.log"

  echo ">>> Testing ${REPO} PR#${PR}..."
  START=$(date +%s)

  agent-forge run "${REPO}" --pr "${PR}" --mode "${MODE}" \
    --max-iterations 2 \
    > "${LOG_FILE}" 2>&1 || true

  END=$(date +%s)
  DURATION=$(( END - START ))
  EXIT_CODE=$?
  MINS=$(( DURATION / 60 ))
  SECS=$(( DURATION % 60 ))

  echo "    Done in ${MINS}m${SECS}s (exit: ${EXIT_CODE})"
  echo "| ${REPO} | #${PR} | ${MINS}m${SECS}s | ${EXIT_CODE} |" >> "${SUMMARY_FILE}"
done

TOTAL_END=$(date +%s)
TOTAL=$(( TOTAL_END - TOTAL_START ))
TOTAL_MINS=$(( TOTAL / 60 ))
TOTAL_SECS=$(( TOTAL % 60 ))

echo "" >> "${SUMMARY_FILE}"
echo "**Total time:** ${TOTAL_MINS}m${TOTAL_SECS}s" >> "${SUMMARY_FILE}"

echo ""
echo "============================================"
echo "  Benchmark complete in ${TOTAL_MINS}m${TOTAL_SECS}s"
echo "  Results: ${RESULTS_DIR}/"
echo "  Summary: ${RESULTS_DIR}/summary.md"
echo "============================================"
cat "${SUMMARY_FILE}"

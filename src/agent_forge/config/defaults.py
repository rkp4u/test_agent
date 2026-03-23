"""Default configuration mappings."""

from agent_forge.models.enums import BuildTool, Language, TestFramework

# Language → default test framework
DEFAULT_TEST_FRAMEWORKS: dict[Language, TestFramework] = {
    Language.JAVA: TestFramework.JUNIT5,
    Language.PYTHON: TestFramework.PYTEST,
    Language.TYPESCRIPT: TestFramework.JEST,
    Language.KOTLIN: TestFramework.JUNIT5,
}

# Language → file extension
LANGUAGE_EXTENSIONS: dict[Language, list[str]] = {
    Language.JAVA: [".java"],
    Language.PYTHON: [".py"],
    Language.TYPESCRIPT: [".ts", ".tsx"],
    Language.KOTLIN: [".kt", ".kts"],
    Language.GO: [".go"],
}

# Language → test file patterns
TEST_FILE_PATTERNS: dict[Language, list[str]] = {
    Language.JAVA: ["*Test.java", "*Tests.java", "*Spec.java"],
    Language.PYTHON: ["test_*.py", "*_test.py"],
    Language.TYPESCRIPT: ["*.test.ts", "*.spec.ts"],
    Language.KOTLIN: ["*Test.kt", "*Tests.kt"],
}

# Build tool → test command
TEST_COMMANDS: dict[BuildTool, list[str]] = {
    BuildTool.GRADLE: ["./gradlew", "test"],
    BuildTool.MAVEN: ["./mvnw", "test"],
    BuildTool.PIP: ["pytest"],
    BuildTool.NPM: ["npm", "test"],
}

# Test source directory conventions
TEST_SOURCE_DIRS: dict[Language, str] = {
    Language.JAVA: "src/test/java",
    Language.PYTHON: "tests",
    Language.TYPESCRIPT: "__tests__",
    Language.KOTLIN: "src/test/kotlin",
}

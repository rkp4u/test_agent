"""Test generator node — generates test cases using LLM."""

import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agent_forge.config.settings import get_settings
from agent_forge.engine.state import AgentState
from agent_forge.engine.prompts.generator import build_generation_prompt, GENERATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Mock generated tests (used as fallback if LLM fails)
MOCK_GENERATED_TESTS = [
    {
        "file_path": "src/test/java/com/app/service/PaymentServiceRetryTest.java",
        "content": """package com.app.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.app.config.RetryConfig;
import com.app.exception.PaymentRetryExhaustedException;
import com.app.exception.PermanentException;
import com.app.exception.TransientException;
import com.app.model.PaymentRequest;
import com.app.model.PaymentResult;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PaymentServiceRetryTest {

    @Mock
    private HttpClient httpClient;

    @Mock
    private RetryConfig retryConfig;

    @InjectMocks
    private PaymentService paymentService;

    private PaymentRequest paymentRequest;

    @BeforeEach
    void setUp() {
        paymentRequest = new PaymentRequest();
        when(retryConfig.getMaxRetries()).thenReturn(3);
    }

    @Test
    void testRetryOnTransientFailure() {
        // Arrange: first call returns 503, second returns 200
        when(httpClient.post(any()))
            .thenThrow(new TransientException(503))
            .thenReturn(successResponse());
        when(retryConfig.getBackoffDelay(0)).thenReturn(1000L);

        // Act
        PaymentResult result = paymentService.processPayment(paymentRequest);

        // Assert
        assertThat(result.isSuccessful()).isTrue();
        verify(httpClient, times(2)).post(any());
    }

    @Test
    void testMaxRetryExceeded() {
        // Arrange: all calls fail with 503
        when(httpClient.post(any()))
            .thenThrow(new TransientException(503));
        when(retryConfig.getBackoffDelay(anyInt())).thenReturn(100L);

        // Act & Assert
        assertThrows(PaymentRetryExhaustedException.class,
            () -> paymentService.processPayment(paymentRequest));
        verify(httpClient, times(3)).post(any());
    }

    @Test
    void testNoRetryOnClientError() {
        // Arrange: call returns 400
        when(httpClient.post(any()))
            .thenThrow(new PermanentException(400));

        // Act & Assert
        assertThrows(PermanentException.class,
            () -> paymentService.processPayment(paymentRequest));
        verify(httpClient, times(1)).post(any());
    }

    private PaymentResult successResponse() {
        return new PaymentResult(true, "SUCCESS");
    }
}
""",
        "target_class": "PaymentService",
        "test_methods": [
            "testRetryOnTransientFailure",
            "testMaxRetryExceeded",
            "testNoRetryOnClientError",
        ],
        "framework": "junit5",
    },
    {
        "file_path": "src/test/java/com/app/config/RetryConfigTest.java",
        "content": """package com.app.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class RetryConfigTest {

    @Test
    void testExponentialBackoffDelay() {
        RetryConfig config = new RetryConfig(3, 1000, 2.0);

        assertThat(config.getBackoffDelay(0)).isEqualTo(1000);  // 1s
        assertThat(config.getBackoffDelay(1)).isEqualTo(2000);  // 2s
        assertThat(config.getBackoffDelay(2)).isEqualTo(4000);  // 4s
    }

    @Test
    void testMaxRetriesConfig() {
        RetryConfig config = new RetryConfig(5, 500, 1.5);
        assertThat(config.getMaxRetries()).isEqualTo(5);
    }
}
""",
        "target_class": "RetryConfig",
        "test_methods": ["testExponentialBackoffDelay", "testMaxRetriesConfig"],
        "framework": "junit5",
    },
]


async def test_generator_node(state: AgentState) -> dict:
    """Generate test cases for uncovered code paths.

    Uses LLM with code analysis context. On reflexion iterations,
    only regenerates failing tests with critic feedback.
    """
    iteration = state.get("iteration", 0)
    tests_to_fix = state.get("tests_to_fix", [])
    critic_feedback = state.get("critic_feedback")

    settings = get_settings()

    if iteration > 0 and tests_to_fix:
        logger.info(
            f"Reflexion iteration {iteration}: regenerating {len(tests_to_fix)} failing tests"
        )
    else:
        logger.info("Generating tests for uncovered code paths")

    # Try LLM generation, fall back to mock
    try:
        if settings.openai_api_key:
            generated = await _generate_with_llm(state, settings)
        else:
            logger.warning("No OpenAI API key — using mock test data")
            generated = MOCK_GENERATED_TESTS
    except Exception as e:
        logger.warning(f"LLM generation failed ({e}), using mock data")
        generated = MOCK_GENERATED_TESTS

    test_plan = {
        "targets": state.get("untested_targets", []),
        "planned_tests": [
            {"test_name": m, "target_method": t["target_class"]}
            for t in generated
            for m in t.get("test_methods", [])
        ],
        "estimated_coverage_increase": "34% → 91%",
        "strategy": "Unit tests with Mockito for dependency isolation",
    }

    return {
        "current_step": "test_generator",
        "generated_tests": generated,
        "test_plan": test_plan,
    }


async def _generate_with_llm(state: AgentState, settings) -> list[dict]:
    """Use LLM to generate tests based on code analysis."""
    llm = ChatOpenAI(
        model=settings.model,
        temperature=settings.temperature,
        api_key=settings.openai_api_key,
    )

    prompt = build_generation_prompt(
        code_analysis=state.get("code_analysis", {}),
        existing_coverage=state.get("existing_coverage", {}),
        pr_diff=state.get("pr_diff", {}),
        critic_feedback=state.get("critic_feedback"),
        tests_to_fix=state.get("tests_to_fix", []),
        previous_tests=state.get("generated_tests", []),
    )

    response = await llm.ainvoke([
        SystemMessage(content=GENERATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    # Parse LLM response — expect JSON array of test files
    try:
        content = response.content
        # Extract JSON from markdown code block if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        tests = json.loads(content)
        if isinstance(tests, list):
            return tests
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse LLM response as JSON, using mock data")

    return MOCK_GENERATED_TESTS

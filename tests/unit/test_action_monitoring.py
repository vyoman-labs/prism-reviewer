"""
Unit tests for optional telemetry dependencies and GitHub Action monitoring logic.
"""

import subprocess
import tomllib
from pathlib import Path


def test_pyproject_optional_dependencies_defined():
    """Verify pyproject.toml defines langfuse, otel, and monitoring optional-dependencies."""
    pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    optional_deps = data.get("project", {}).get("optional-dependencies", {})
    assert "langfuse" in optional_deps, "pyproject.toml missing [project.optional-dependencies] langfuse extra"
    assert "otel" in optional_deps, "pyproject.toml missing [project.optional-dependencies] otel extra"
    assert "monitoring" in optional_deps, "pyproject.toml missing [project.optional-dependencies] monitoring extra"

    assert any("langfuse" in req for req in optional_deps["langfuse"])
    assert any("opentelemetry-api" in req for req in optional_deps["otel"])
    assert any("opentelemetry-sdk" in req for req in optional_deps["otel"])
    assert any("opentelemetry-exporter-otlp" in req for req in optional_deps["otel"])
    assert len(optional_deps["monitoring"]) >= 4


def test_action_monitoring_shell_script_logic(tmp_path: Path):
    """
    Test the bash auto-detection logic used in action.yml's Install Telemetry Dependencies step.
    """
    bash_script = """
    CALLBACKS_LOWER=$(echo "${PRISM_MONITORING_LITELLM_CALLBACKS}" | tr '[:upper:]' '[:lower:]')
    MONITORING_LOWER=$(echo "${ENABLE_MONITORING}" | tr '[:upper:]' '[:lower:]')

    if [ "$MONITORING_LOWER" = "false" ]; then
      echo "SKIPPED_EXPLICIT_FALSE"
      exit 0
    fi

    NEED_LANGFUSE=false
    NEED_OTEL=false

    if [[ "$CALLBACKS_LOWER" == *"langfuse"* ]] || [ -n "$LANGFUSE_PUBLIC_KEY" ] || [ -n "$LANGFUSE_SECRET_KEY" ]; then
      NEED_LANGFUSE=true
    fi

    if [[ "$CALLBACKS_LOWER" == *"otel"* ]] || [[ "$CALLBACKS_LOWER" == *"opentelemetry"* ]] || [ -n "$OTEL_EXPORTER_OTLP_ENDPOINT" ]; then
      NEED_OTEL=true
    fi

    if [ "$MONITORING_LOWER" = "true" ] && [ "$NEED_LANGFUSE" = "false" ] && [ "$NEED_OTEL" = "false" ]; then
      NEED_LANGFUSE=true
      NEED_OTEL=true
    fi

    if [ "$NEED_LANGFUSE" = "true" ] && [ "$NEED_OTEL" = "true" ]; then
      echo "INSTALL_MONITORING"
    elif [ "$NEED_LANGFUSE" = "true" ]; then
      echo "INSTALL_LANGFUSE"
    elif [ "$NEED_OTEL" = "true" ]; then
      echo "INSTALL_OTEL"
    else
      echo "SKIPPED_NO_CALLBACKS"
    fi
    """

    script_file = tmp_path / "check.sh"
    script_file.write_text(bash_script)

    def run_check(env_vars: dict[str, str]) -> str:
        res = subprocess.run(
            ["bash", str(script_file)],
            env=env_vars,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()

    # 1. Default (no monitoring env or inputs) -> SKIPPED
    out = run_check({"ENABLE_MONITORING": "auto"})
    assert out == "SKIPPED_NO_CALLBACKS"

    # 2. Explicit false -> SKIPPED_EXPLICIT_FALSE
    out = run_check({"ENABLE_MONITORING": "false", "PRISM_MONITORING_LITELLM_CALLBACKS": "langfuse"})
    assert out == "SKIPPED_EXPLICIT_FALSE"

    # 3. Langfuse via PRISM_MONITORING_LITELLM_CALLBACKS
    out = run_check({"ENABLE_MONITORING": "auto", "PRISM_MONITORING_LITELLM_CALLBACKS": "langfuse"})
    assert out == "INSTALL_LANGFUSE"

    # 4. Langfuse via LANGFUSE_PUBLIC_KEY
    out = run_check({"ENABLE_MONITORING": "auto", "LANGFUSE_PUBLIC_KEY": "pk-123"})
    assert out == "INSTALL_LANGFUSE"

    # 5. OTel via OTEL_EXPORTER_OTLP_ENDPOINT
    out = run_check({"ENABLE_MONITORING": "auto", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"})
    assert out == "INSTALL_OTEL"

    # 6. Both Langfuse and OTel
    out = run_check({"ENABLE_MONITORING": "auto", "PRISM_MONITORING_LITELLM_CALLBACKS": "langfuse,otel"})
    assert out == "INSTALL_MONITORING"

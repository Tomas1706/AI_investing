import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _load_dotenv(dotenv_path: Path) -> None:
    """Simple .env loader: parses KEY=VALUE lines and updates os.environ.
    - Ignores blank lines and lines starting with '#'.
    - Strips surrounding quotes from values.
    - Does not override existing environment variables.
    """
    if not dotenv_path.exists():
        return
    try:
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes if present
            if (value.startswith("\"") and value.endswith("\"")) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            # Do not override existing env vars
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        # Fail silently for now; downstream code will handle missing values
        pass


@dataclass
class Config:
    app_env: str = "development"
    sec_user_agent: str = "ai-investing/cli contact@example.com"
    output_dir: Path = Path("reports")
    override_cik: Optional[str] = None
    bdmcp_api_key: Optional[str] = None  # later phase
    bdmcp_api_base: Optional[str] = None  # later phase
    alpha_vantage_api_key: Optional[str] = None


def load_config() -> Config:
    # Load from .env (if present) without overriding existing env vars
    _load_dotenv(Path(".env"))

    app_env = os.getenv("APP_ENV", "development")
    sec_user_agent = os.getenv(
        "SEC_USER_AGENT", "ai-investing/cli contact@example.com"
    )
    output_dir = Path(os.getenv("OUTPUT_DIR", "reports")).resolve()
    override_cik = os.getenv("OVERRIDE_CIK") or None
    bdmcp_api_key = os.getenv("BDMCP_API_KEY") or None
    bdmcp_api_base = os.getenv("BDMCP_API_BASE") or None
    alpha_vantage_api_key = os.getenv("ALPHAVANTAGE_API_KEY") or None

    # Simple warnings for missing/placeholder values
    if sec_user_agent in ("", "ai-investing/cli contact@example.com"):
        print(
            "[config] Warning: SEC_USER_AGENT is not set to a descriptive identifier. "
            "Set it in .env as '<org>/<app> <contact-email>'."
        )

    # Ensure output dir exists (best-effort)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(
            f"[config] Warning: Failed to create output dir '{output_dir}': {e}. "
            "Falling back to './reports'."
        )
        output_dir = Path("reports").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        app_env=app_env,
        sec_user_agent=sec_user_agent,
        output_dir=output_dir,
        override_cik=override_cik,
        bdmcp_api_key=bdmcp_api_key,
        bdmcp_api_base=bdmcp_api_base,
        alpha_vantage_api_key=alpha_vantage_api_key,
    )

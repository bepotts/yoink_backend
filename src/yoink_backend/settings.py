# Selects isolated PostgreSQL databases for development and production.
"""Environment-specific database settings loaded at application startup."""

from typing import Literal

from pydantic import Field, PostgresDsn, TypeAdapter
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class DatabaseSettings(BaseSettings):
    """Select the active database without falling back to another environment."""

    # Hides credential-bearing input from validation error strings.
    model_config = SettingsConfigDict(hide_input_in_errors=True)
    # Selects the same environment used by backend S3 configuration.
    app_env: Literal["development", "production"] = "development"
    # Configures local or hosted development storage without exposing credentials.
    database_dev_url: str = Field(default="", repr=False)
    # Configures production storage independently of development credentials.
    database_prod_url: str = Field(default="", repr=False)

    # Validates the active URL and prevents both environments sharing a database.
    @property
    def database_url(self) -> PostgresDsn:
        """Require the active environment's explicit PostgreSQL destination."""
        value = (
            self.database_prod_url
            if self.app_env == "production"
            else self.database_dev_url
        )
        variable = f"DATABASE_{'PROD' if self.app_env == 'production' else 'DEV'}_URL"
        if not value.strip():
            raise ValueError(f"Configure {variable} on the backend.")
        selected = TypeAdapter(PostgresDsn).validate_python(value.strip())
        if self.database_dev_url.strip() and self.database_prod_url.strip():
            development = make_url(self.database_dev_url.strip())
            production = make_url(self.database_prod_url.strip())
            if (
                development.host,
                development.port or 5432,
                development.database,
            ) == (production.host, production.port or 5432, production.database):
                raise ValueError(
                    "Development and production must use different databases."
                )
        return selected

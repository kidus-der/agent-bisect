"""Health, build meta, and search response models (page group 7 — global)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agent_bisect.server.schemas_common import DataSource


class HealthPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str


class MetaPayload(BaseModel):
    """`/api/meta`: what data backs this server process, and what built it."""

    model_config = ConfigDict(frozen=True)

    data_source: DataSource
    simulated: bool
    package_version: str
    tau2_commit: str
    agent_model: str
    user_model: str
    generated_at: str


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    """"run" | "page"."""
    id: str
    title: str
    subtitle: str | None = None
    href: str


class SearchResults(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    hits: tuple[SearchHit, ...]


class NotAvailable(BaseModel):
    """A typed placeholder for data `real_repository` cannot yet serve.

    Never a stand-in for a real number: any endpoint returning this must
    never also invent a plausible-looking value for the same field.
    """

    model_config = ConfigDict(frozen=True)

    status: str = "not_available"
    reason: str

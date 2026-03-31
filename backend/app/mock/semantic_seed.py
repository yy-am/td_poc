"""Compatibility wrapper for semantic asset seeds."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.mock.semantic_assets import SEMANTIC_MODEL_RECORDS, SEMANTIC_YAML_MAP, seed_semantic_model_assets


async def seed_semantic_yaml_definitions(session: AsyncSession) -> None:
    await seed_semantic_model_assets(session)


__all__ = ["SEMANTIC_MODEL_RECORDS", "SEMANTIC_YAML_MAP", "seed_semantic_yaml_definitions"]

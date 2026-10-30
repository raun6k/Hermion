"""Basket lines from accepted evaluations; confirm; merchant review and in-person edits. Built in Stage 1."""

import uuid


async def add_from_evaluation(session_id: uuid.UUID, evaluation_id: uuid.UUID) -> None:
    raise NotImplementedError


async def confirm(session_id: uuid.UUID) -> None:
    raise NotImplementedError

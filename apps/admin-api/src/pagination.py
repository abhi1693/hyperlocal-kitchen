"""Bounded SQL filtering and deterministic admin lists, following DevFeed."""

from typing import Annotated

from fastapi import Depends, Query
from kitchen_core.errors import DomainError
from pydantic import BaseModel
from sqlalchemy import func, select


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ListQuery:
    def __init__(
        self,
        q: str = Query("", max_length=200, pattern=r"^[^\x00]*$"),
        sort: str | None = Query(None, max_length=50),
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0, le=10_000),
    ):
        self.q, self.sort, self.limit, self.offset = q.strip(), sort, limit, offset


Listing = Annotated[ListQuery, Depends()]


def paginate(session, statement, query, sorting, default="created_at"):
    order = query.sort or default
    column = sorting.get(order.removeprefix("-"))
    if column is None:
        raise DomainError(422, "invalid_sort", "Choose a supported sort field.")
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    model = statement.column_descriptions[0]["entity"]
    rows = list(
        session.scalars(
            statement.order_by(
                column.desc() if order.startswith("-") else column.asc(),
                *model.__mapper__.primary_key,
            )
            .offset(query.offset)
            .limit(query.limit)
        )
    )
    return {"items": rows, "total": total or 0, "limit": query.limit, "offset": query.offset}


def record(session, model, identifier, *, lock=False):
    statement = select(model).where(model.id == identifier)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    value = session.scalar(statement)
    if value is None:
        raise DomainError(404, "not_found", "The requested record was not found.")
    return value

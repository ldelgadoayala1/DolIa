"""
Modelos SQLAlchemy para el historial de búsquedas, el log estructurado
por job y el catálogo de proveedores de búsqueda.

Este paquete se monta como volumen de solo lectura en api/ y worker/
(ver docker-compose.yml), igual que config/, para no duplicar código
entre ambos servicios.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SearchProvider(Base):
    """Catálogo de fuentes de búsqueda soportadas (activas, pendientes o bloqueadas)."""

    __tablename__ = "search_providers"

    slug: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rate_limit_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SearchQuery(Base):
    """Historial de búsquedas: un registro por job_id creado en POST /search."""

    __tablename__ = "search_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # == job_id
    query: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    max_results: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    posts_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logs: Mapped[list["JobLog"]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )


class JobLog(Base):
    """Log estructurado por etapa del pipeline (reemplaza los print() sueltos del worker)."""

    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("search_queries.id"), index=True)
    stage: Mapped[str] = mapped_column(String(30))
    level: Mapped[str] = mapped_column(String(10), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    query: Mapped["SearchQuery"] = relationship(back_populates="logs")

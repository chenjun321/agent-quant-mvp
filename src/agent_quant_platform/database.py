from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import BacktestResult

DEFAULT_DATABASE_URL = "sqlite:///runs/agent_quant_platform.db"

try:
    from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
    from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

    SQLALCHEMY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised through runtime guard.
    SQLALCHEMY_AVAILABLE = False


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


if SQLALCHEMY_AVAILABLE:
    class Base(DeclarativeBase):
        pass


    class RunRecord(Base):
        __tablename__ = "runs"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
        symbol: Mapped[str] = mapped_column(String(32), index=True)
        requested_source: Mapped[str] = mapped_column(String(32))
        actual_source: Mapped[str] = mapped_column(String(32))
        start_equity: Mapped[float] = mapped_column(Float)
        end_equity: Mapped[float] = mapped_column(Float)
        total_return_pct: Mapped[float] = mapped_column(Float)
        max_drawdown_pct: Mapped[float] = mapped_column(Float)
        win_rate_pct: Mapped[float] = mapped_column(Float)
        total_trades: Mapped[int] = mapped_column(Integer)
        total_fees: Mapped[float] = mapped_column(Float, default=0.0)
        rejected_orders: Mapped[int] = mapped_column(Integer, default=0)
        skipped_steps: Mapped[int] = mapped_column(Integer, default=0)
        forced_liquidations: Mapped[int] = mapped_column(Integer, default=0)
        halt_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
        halted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
        summary_json: Mapped[dict[str, Any]] = mapped_column(JSON)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

        trades: Mapped[list["TradeRecord"]] = relationship(cascade="all, delete-orphan", back_populates="run")
        fills: Mapped[list["FillRecord"]] = relationship(cascade="all, delete-orphan", back_populates="run")
        rejected_order_rows: Mapped[list["RejectedOrderRecord"]] = relationship(
            cascade="all, delete-orphan", back_populates="run"
        )
        trace_rows: Mapped[list["TraceRecord"]] = relationship(cascade="all, delete-orphan", back_populates="run")


    class TradeRecord(Base):
        __tablename__ = "trades"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
        ts: Mapped[datetime] = mapped_column(DateTime, index=True)
        symbol: Mapped[str] = mapped_column(String(32), index=True)
        side: Mapped[str] = mapped_column(String(16))
        price: Mapped[float] = mapped_column(Float)
        position_pct: Mapped[float] = mapped_column(Float)
        equity_after_trade: Mapped[float] = mapped_column(Float)
        payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)

        run: Mapped["RunRecord"] = relationship(back_populates="trades")


    class FillRecord(Base):
        __tablename__ = "fills"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
        ts: Mapped[datetime] = mapped_column(DateTime, index=True)
        symbol: Mapped[str] = mapped_column(String(32), index=True)
        action: Mapped[str] = mapped_column(String(16))
        price: Mapped[float] = mapped_column(Float)
        base_qty: Mapped[float] = mapped_column(Float)
        quote_qty: Mapped[float] = mapped_column(Float)
        fee: Mapped[float] = mapped_column(Float)
        cash_after: Mapped[float] = mapped_column(Float)
        base_after: Mapped[float] = mapped_column(Float)
        equity_after: Mapped[float] = mapped_column(Float)
        reason: Mapped[str] = mapped_column(Text, default="")
        payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)

        run: Mapped["RunRecord"] = relationship(back_populates="fills")


    class RejectedOrderRecord(Base):
        __tablename__ = "rejected_orders"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
        ts: Mapped[datetime] = mapped_column(DateTime, index=True)
        symbol: Mapped[str] = mapped_column(String(32), index=True)
        action: Mapped[str] = mapped_column(String(16))
        requested_quote_amount: Mapped[float] = mapped_column(Float)
        status: Mapped[str] = mapped_column(String(16))
        reason: Mapped[str] = mapped_column(Text)
        payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)

        run: Mapped["RunRecord"] = relationship(back_populates="rejected_order_rows")


    class TraceRecord(Base):
        __tablename__ = "traces"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
        ts: Mapped[datetime] = mapped_column(DateTime, index=True)
        symbol: Mapped[str] = mapped_column(String(32), index=True)
        close: Mapped[float] = mapped_column(Float)
        payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)

        run: Mapped["RunRecord"] = relationship(back_populates="trace_rows")


class DatabaseRunStore:
    def __init__(self, database_url: str = DEFAULT_DATABASE_URL) -> None:
        if not SQLALCHEMY_AVAILABLE:
            raise RuntimeError(
                "sqlalchemy is required for database persistence. Install project dependencies before using DatabaseRunStore."
            )

        self.database_url = database_url
        self._ensure_local_sqlite_directory()
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def write_run(self, run_id: str, result: BacktestResult) -> str:
        summary_payload = {
            "symbol": result.symbol,
            "requested_source": result.requested_source,
            "actual_source": result.data_source,
            "start_equity": result.start_equity,
            "end_equity": result.end_equity,
            "stats": _jsonable(result.stats),
            "halt_reason": result.halt_reason,
            "halted_at": _jsonable(result.halted_at),
        }

        with Session(self.engine) as session:
            existing = session.scalar(select(RunRecord).where(RunRecord.run_id == run_id))
            if existing is not None:
                raise ValueError(f"run_id already exists: {run_id}")

            run_row = RunRecord(
                run_id=run_id,
                symbol=result.symbol,
                requested_source=result.requested_source,
                actual_source=result.data_source,
                start_equity=result.start_equity,
                end_equity=result.end_equity,
                total_return_pct=result.stats.total_return_pct,
                max_drawdown_pct=result.stats.max_drawdown_pct,
                win_rate_pct=result.stats.win_rate_pct,
                total_trades=result.stats.total_trades,
                total_fees=result.stats.total_fees,
                rejected_orders=result.stats.rejected_orders,
                skipped_steps=result.stats.skipped_steps,
                forced_liquidations=result.stats.forced_liquidations,
                halt_reason=result.halt_reason,
                halted_at=result.halted_at,
                summary_json=summary_payload,
            )

            run_row.trades = [
                TradeRecord(
                    ts=trade.ts,
                    symbol=trade.symbol,
                    side=trade.side,
                    price=trade.price,
                    position_pct=trade.position_pct,
                    equity_after_trade=trade.equity_after_trade,
                    payload_json=_jsonable(trade),
                )
                for trade in result.trades
            ]
            run_row.fills = [
                FillRecord(
                    ts=fill.ts,
                    symbol=fill.symbol,
                    action=fill.action,
                    price=fill.price,
                    base_qty=fill.base_qty,
                    quote_qty=fill.quote_qty,
                    fee=fill.fee,
                    cash_after=fill.cash_after,
                    base_after=fill.base_after,
                    equity_after=fill.equity_after,
                    reason=fill.reason,
                    payload_json=_jsonable(fill),
                )
                for fill in result.fills
            ]
            run_row.rejected_order_rows = [
                RejectedOrderRecord(
                    ts=order.ts,
                    symbol=order.symbol,
                    action=order.action,
                    requested_quote_amount=order.requested_quote_amount,
                    status=order.status,
                    reason=order.reason,
                    payload_json=_jsonable(order),
                )
                for order in result.rejected_orders
            ]
            run_row.trace_rows = [
                TraceRecord(
                    ts=trace.ts,
                    symbol=trace.symbol,
                    close=trace.close,
                    payload_json=_jsonable(trace),
                )
                for trace in result.traces
            ]

            session.add(run_row)
            session.commit()

        return run_id

    def _ensure_local_sqlite_directory(self) -> None:
        sqlite_prefix = "sqlite:///"
        if not self.database_url.startswith(sqlite_prefix):
            return

        sqlite_path = self.database_url[len(sqlite_prefix) :]
        if not sqlite_path or sqlite_path == ":memory:":
            return

        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

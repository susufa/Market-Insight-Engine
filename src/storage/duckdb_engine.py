"""
storage/duckdb_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~
High-performance analytical SQL query engine backed by embedded DuckDB.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

logger = logging.getLogger(__name__)


class DuckDBEngine:
    """Embedded analytical OLAP query engine over Parquet data."""

    def __init__(self, production_dir: Path) -> None:
        self.production_dir = production_dir
        self._con: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        """Initialize in-memory DuckDB connection."""
        self._con = duckdb.connect(database=":memory:")
        # Optimize memory and thread limits
        self._con.execute("PRAGMA threads=4;")

    def close(self) -> None:
        """Close DuckDB connection."""
        if self._con:
            self._con.close()
            self._con = None

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            raise RuntimeError("DuckDB connection is not open. Call connect() first.")
        return self._con

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> pl.DataFrame:
        """
        Execute an analytical SQL query against the local Parquet data lake.
        Runs in a background thread to prevent blocking asyncio loop.
        """

        def _exec() -> pl.DataFrame:
            con = self.connection
            if params:
                if "?" in sql and "$" not in sql:
                    arrow_tbl = con.execute(sql, list(params.values())).to_arrow_table()
                else:
                    arrow_tbl = con.execute(sql, params).to_arrow_table()
                df = pl.from_arrow(arrow_tbl)
                if isinstance(df, pl.DataFrame):
                    return df
                return pl.DataFrame()
            else:
                rel = con.sql(sql)
                if rel is None:
                    return pl.DataFrame()
                df = rel.pl()
                if isinstance(df, pl.DataFrame):
                    return df
                return pl.DataFrame()

        return await asyncio.to_thread(_exec)

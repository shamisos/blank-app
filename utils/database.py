from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session


DEFAULT_DATABASE_URL_ENV = "DATABASE_URL"


class Base(DeclarativeBase):
    pass


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    sessions: Mapped[List["AnalysisSession"]] = relationship(back_populates="facility", cascade="all, delete-orphan")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    treatment_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ethnicity: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    immigration_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    material_deprivation: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    residential_instability: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dependency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ethnic_concentration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    facility_id: Mapped[Optional[int]] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    facility: Mapped[Optional[Facility]] = relationship(back_populates="sessions")

    filter_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# Engine and Session helpers

def get_engine(database_url: Optional[str] = None) -> Engine:
    """Create a SQLAlchemy engine for PostgreSQL (or any SQLAlchemy-supported URL)."""
    url = database_url or os.getenv(DEFAULT_DATABASE_URL_ENV)
    if not url:
        raise ValueError("Database URL not provided. Set DATABASE_URL env or pass database_url explicitly.")
    engine = create_engine(url, future=True, pool_pre_ping=True)
    return engine


def create_all_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)


# CRUD operations

def save_patients(engine: Engine, patients_df: pd.DataFrame) -> int:
    """Bulk insert patient records. Returns number of rows inserted."""
    nullable_cols = {c for c in patients_df.columns}
    insert_cols = [
        "external_id",
        "name",
        "latitude",
        "longitude",
        "treatment_type",
        "gender",
        "ethnicity",
        "immigration_status",
        "material_deprivation",
        "residential_instability",
        "dependency",
        "ethnic_concentration",
        "distance_km",
        "distance_category",
    ]

    with Session(engine) as session:
        objects: List[Patient] = []
        for _, row in patients_df.iterrows():
            patient_kwargs = {}
            for col in insert_cols:
                if col in nullable_cols:
                    val = row.get(col)
                    if pd.isna(val):
                        val = None
                    patient_kwargs[col] = val
            objects.append(Patient(**patient_kwargs))
        session.add_all(objects)
        session.commit()
        return len(objects)


def load_patients(engine: Engine) -> pd.DataFrame:
    with Session(engine) as session:
        rows = session.scalars(select(Patient)).all()
        data = []
        for p in rows:
            data.append(
                {
                    "id": p.id,
                    "external_id": p.external_id,
                    "name": p.name,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "treatment_type": p.treatment_type,
                    "gender": p.gender,
                    "ethnicity": p.ethnicity,
                    "immigration_status": p.immigration_status,
                    "material_deprivation": p.material_deprivation,
                    "residential_instability": p.residential_instability,
                    "dependency": p.dependency,
                    "ethnic_concentration": p.ethnic_concentration,
                    "distance_km": p.distance_km,
                    "distance_category": p.distance_category,
                }
            )
        return pd.DataFrame(data)


def save_facility(engine: Engine, name: Optional[str], latitude: float, longitude: float, address: Optional[str] = None) -> int:
    with Session(engine) as session:
        f = Facility(name=name, latitude=float(latitude), longitude=float(longitude), address=address)
        session.add(f)
        session.commit()
        return f.id


def list_facilities(engine: Engine) -> List[Tuple[int, str, float, float]]:
    with Session(engine) as session:
        rows = session.scalars(select(Facility)).all()
        return [(f.id, f.name or f"Facility #{f.id}", f.latitude, f.longitude) for f in rows]


def save_analysis_session(engine: Engine, facility_id: Optional[int], filter_state: Dict[str, Any], summary: Dict[str, Any], notes: Optional[str] = None) -> int:
    with Session(engine) as session:
        s = AnalysisSession(
            facility_id=facility_id,
            filter_state=filter_state,
            summary=summary,
            notes=notes,
        )
        session.add(s)
        session.commit()
        return s.id
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    external_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="user"
    )
    memories: Mapped[list["UserMemory"]] = relationship(
    back_populates="user",
    cascade="all, delete-orphan",
)



class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    location: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    cuisine: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="restaurant"
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reservation_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    restaurant_id: Mapped[str] = mapped_column(
        ForeignKey("restaurants.id"),
        nullable=False,
    )

    date: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    party_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="confirmed",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user: Mapped["User | None"] = relationship(
        back_populates="reservations"
    )

    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="reservations"
    )

    events: Mapped[list["ReservationEvent"]] = relationship(
        back_populates="reservation",
        cascade="all, delete-orphan",
    )


class ReservationEvent(Base):
    __tablename__ = "reservation_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    reservation: Mapped["Reservation"] = relationship(
        back_populates="events"
    )

class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    memory_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    memory_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    memory_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="memories"
    )


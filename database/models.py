from datetime import datetime
from sqlalchemy import (
    BigInteger, String, Float, Integer,
    DateTime, ForeignKey, Enum, Text, Boolean
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    PASSENGER = "passenger"
    DRIVER = "driver"


class DriverStatus(str, enum.Enum):
    PENDING = "pending"       # Admin tasdiqlashini kutmoqda
    APPROVED = "approved"     # Tasdiqlangan
    REJECTED = "rejected"     # Rad etilgan


class OrderStatus(str, enum.Enum):
    PENDING = "pending"       # Kutmoqda (hali hech kim olmagan)
    CLAIMED = "claimed"       # Haydovchi tomonidan olingan
    CANCELLED = "cancelled"   # Bekor qilingan
    COMPLETED = "completed"   # Yakunlangan


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[UserRole | None] = mapped_column(Enum(UserRole), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Eski bazada mavjud ustun — NOT NULL constraint bor, shuning uchun default beramiz
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=True)

    driver: Mapped["Driver | None"] = relationship("Driver", back_populates="user", uselist=False)
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="passenger", foreign_keys="Order.passenger_id")


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), unique=True)
    full_name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str] = mapped_column(String(20))
    car_model: Mapped[str] = mapped_column(String(64))
    car_number: Mapped[str] = mapped_column(String(20))
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[DriverStatus] = mapped_column(Enum(DriverStatus), default=DriverStatus.PENDING)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="driver")
    claimed_orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="driver",
        primaryjoin="Driver.user_id == Order.driver_id",
        foreign_keys="[Order.driver_id]",
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passenger_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    driver_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    from_location: Mapped[str] = mapped_column(String(256))
    to_location: Mapped[str] = mapped_column(String(256))
    passenger_phone: Mapped[str] = mapped_column(String(20))
    passenger_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.PENDING)
    commission_charged: Mapped[float] = mapped_column(Float, default=0.0)
    channel_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    passenger: Mapped["User"] = relationship("User", back_populates="orders", foreign_keys=[passenger_id])
    driver: Mapped["Driver | None"] = relationship(
        "Driver",
        back_populates="claimed_orders",
        primaryjoin="Order.driver_id == Driver.user_id",
        foreign_keys="[Order.driver_id]",
    )


class Settings(Base):
    """Tizim sozlamalari: komissiya va boshqa dinamik qiymatlar."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

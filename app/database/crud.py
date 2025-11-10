from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import User, Package, Order, ProcessedImage, SupportTicket, Admin


# ==================== USER OPERATIONS ====================

async def get_or_create_user(session: AsyncSession, telegram_id: int, username: Optional[str] = None,
                             first_name: Optional[str] = None, free_images_count: int = 3) -> User:
    """Get existing user or create new one"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            free_images_left=free_images_count
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def get_user_balance(session: AsyncSession, telegram_id: int) -> dict:
    """Get user's balance (free + paid images)"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return {"free": 0, "paid": 0, "total": 0}

    # Count paid images from successful orders
    paid_result = await session.execute(
        select(func.sum(Package.images_count))
        .join(Order, Order.package_id == Package.id)
        .where(and_(Order.user_id == user.id, Order.status == "paid"))
    )
    paid_total = paid_result.scalar() or 0

    # Count used paid images
    used_result = await session.execute(
        select(func.count(ProcessedImage.id))
        .where(and_(ProcessedImage.user_id == user.id, ProcessedImage.is_free == False))
    )
    used_paid = used_result.scalar() or 0

    paid_left = max(0, paid_total - used_paid)

    return {
        "free": user.free_images_left,
        "paid": paid_left,
        "total": user.free_images_left + paid_left
    }


async def decrease_balance(session: AsyncSession, telegram_id: int) -> bool:
    """Decrease user's balance (prioritize free images)"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return False

    if user.free_images_left > 0:
        user.free_images_left -= 1
        await session.commit()
        return True

    # Check if user has paid images
    balance = await get_user_balance(session, telegram_id)
    if balance["paid"] > 0:
        return True

    return False


async def add_paid_images(session: AsyncSession, telegram_id: int, count: int):
    """This is tracked through orders, no direct operation needed"""
    pass


async def update_user_stats(session: AsyncSession, telegram_id: int):
    """Update user's total images processed counter"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user:
        user.total_images_processed += 1
        user.updated_at = datetime.utcnow()
        await session.commit()


# ==================== PACKAGE OPERATIONS ====================

async def get_all_packages(session: AsyncSession) -> List[Package]:
    """Get all active packages"""
    result = await session.execute(
        select(Package).where(Package.is_active == True).order_by(Package.images_count)
    )
    return result.scalars().all()


async def get_package_by_id(session: AsyncSession, package_id: int) -> Optional[Package]:
    """Get package by ID"""
    result = await session.execute(
        select(Package).where(Package.id == package_id)
    )
    return result.scalar_one_or_none()


# ==================== ORDER OPERATIONS ====================

async def create_order(session: AsyncSession, telegram_id: int, package_id: int,
                       invoice_id: str, amount: float) -> Order:
    """Create new order"""
    # Get user
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    order = Order(
        user_id=user.id,
        package_id=package_id,
        robokassa_invoice_id=invoice_id,
        amount=amount,
        status="pending"
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)

    return order


async def get_order_by_invoice_id(session: AsyncSession, invoice_id: str) -> Optional[Order]:
    """Get order by Robokassa invoice ID"""
    result = await session.execute(
        select(Order).where(Order.robokassa_invoice_id == invoice_id)
    )
    return result.scalar_one_or_none()


async def mark_order_paid(session: AsyncSession, invoice_id: str) -> Optional[Order]:
    """Mark order as paid"""
    order = await get_order_by_invoice_id(session, invoice_id)

    if order:
        order.status = "paid"
        order.paid_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)

    return order


async def get_user_orders(session: AsyncSession, telegram_id: int, limit: int = 10) -> List[Order]:
    """Get user's orders"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return []

    result = await session.execute(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .options(selectinload(Order.package))
    )
    return result.scalars().all()


# ==================== PROCESSED IMAGE OPERATIONS ====================

async def save_processed_image(session: AsyncSession, telegram_id: int, original_file_id: str,
                               processed_file_id: str, prompt_used: str, is_free: bool = False):
    """Save processed image record"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return

    processed_image = ProcessedImage(
        user_id=user.id,
        original_file_id=original_file_id,
        processed_file_id=processed_file_id,
        prompt_used=prompt_used,
        is_free=is_free
    )
    session.add(processed_image)
    await session.commit()


# ==================== SUPPORT TICKET OPERATIONS ====================

async def create_support_ticket(session: AsyncSession, telegram_id: int, message: str,
                                order_id: Optional[int] = None) -> SupportTicket:
    """Create new support ticket"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    ticket = SupportTicket(
        user_id=user.id,
        order_id=order_id,
        message=message,
        status="open"
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)

    return ticket


async def get_open_tickets(session: AsyncSession) -> List[SupportTicket]:
    """Get all open support tickets"""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.status.in_(["open", "in_progress"]))
        .order_by(SupportTicket.created_at.desc())
        .options(selectinload(SupportTicket.user))
    )
    return result.scalars().all()


async def resolve_ticket(session: AsyncSession, ticket_id: int, admin_response: str):
    """Resolve support ticket"""
    result = await session.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if ticket:
        ticket.status = "resolved"
        ticket.admin_response = admin_response
        ticket.resolved_at = datetime.utcnow()
        await session.commit()


# ==================== ADMIN OPERATIONS ====================

async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
    """Check if user is admin"""
    result = await session.execute(
        select(Admin).where(Admin.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none() is not None


async def get_statistics(session: AsyncSession) -> dict:
    """Get bot statistics"""
    # Total users
    users_result = await session.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0

    # Total processed images
    images_result = await session.execute(select(func.count(ProcessedImage.id)))
    total_processed = images_result.scalar() or 0

    # Total revenue
    revenue_result = await session.execute(
        select(func.sum(Order.amount))
        .where(Order.status == "paid")
    )
    revenue = revenue_result.scalar() or 0

    # Active orders (pending)
    active_orders_result = await session.execute(
        select(func.count(Order.id))
        .where(Order.status == "pending")
    )
    active_orders = active_orders_result.scalar() or 0

    # Open tickets
    open_tickets_result = await session.execute(
        select(func.count(SupportTicket.id))
        .where(SupportTicket.status.in_(["open", "in_progress"]))
    )
    open_tickets = open_tickets_result.scalar() or 0

    return {
        "total_users": total_users,
        "total_processed": total_processed,
        "revenue": float(revenue),
        "active_orders": active_orders,
        "open_tickets": open_tickets
    }

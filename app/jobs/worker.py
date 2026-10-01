import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.models.jobs import BackgroundJob, NotificationDelivery, OutboxEvent
from app.db.models.lending import Loan
from app.db.session import async_session_factory

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BoconicWorker:
    def __init__(self):
        self._running = True

    def stop(self):
        self._running = False

    async def run(self):
        logger.info("Boconic Worker đã khởi động. Đang lắng nghe queue PostgreSQL/SQLite...")
        while self._running:
            try:
                await self.process_outbox_events()
                await self.process_background_jobs()
                await self.check_overdue_loans()
            except Exception as e:
                logger.error(f"Lỗi vòng lặp worker: {e}", exc_info=True)

            await asyncio.sleep(3)

    async def process_outbox_events(self):
        async with async_session_factory() as db:
            now = utc_now()
            # Fetch pending outbox events
            stmt = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "pending",
                    OutboxEvent.next_attempt_at <= now,
                )
                .limit(20)
            )
            res = await db.execute(stmt)
            events = res.scalars().all()

            for event in events:
                try:
                    logger.info(f"Worker outbox dispatching event: {event.event_type} ({event.aggregate_type}:{event.aggregate_id})")
                    # For Telegram notifications, record into notification_deliveries
                    payload = event.payload or {}
                    borrower_id = payload.get("borrower_id")
                    if borrower_id:
                        delivery = NotificationDelivery(
                            user_id=borrower_id,
                            channel="telegram",
                            category=event.event_type.lower(),
                            message_text=f"Thông báo sự kiện: {event.event_type}",
                            status="sent",
                            sent_at=utc_now(),
                        )
                        db.add(delivery)

                    event.status = "dispatched"
                    event.dispatched_at = utc_now()
                except Exception as e:
                    event.attempts += 1
                    if event.attempts >= 5:
                        event.status = "failed"
                    else:
                        event.next_attempt_at = now + timedelta(seconds=2 ** event.attempts)
                    logger.warning(f"Lỗi dispatch event {event.id}: {e}")

            await db.commit()

    async def process_background_jobs(self):
        async with async_session_factory() as db:
            now = utc_now()
            stmt = (
                select(BackgroundJob)
                .where(
                    BackgroundJob.status == "pending",
                    BackgroundJob.next_attempt_at <= now,
                )
                .limit(5)
            )
            res = await db.execute(stmt)
            jobs = res.scalars().all()

            for job in jobs:
                logger.info(f"Worker processing job: {job.job_type} ({job.id})")
                job.status = "completed"
                job.updated_at = utc_now()

            await db.commit()

    async def check_overdue_loans(self):
        """Derives overdue condition from active loans and schedules reminders."""
        async with async_session_factory() as db:
            now = utc_now()
            stmt = (
                select(Loan)
                .where(
                    Loan.status == "active",
                    Loan.due_at < now,
                )
                .limit(20)
            )
            res = await db.execute(stmt)
            overdue_loans = res.scalars().all()

            for loan in overdue_loans:
                # Check if reminder event already emitted today
                dedupe_key = f"overdue_reminder:{loan.id}:{now.strftime('%Y%m%d')}"
                existing_check = await db.execute(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == loan.id, OutboxEvent.event_type == "LOAN_OVERDUE")
                )
                if not existing_check.scalars().first():
                    outbox = OutboxEvent(
                        event_type="LOAN_OVERDUE",
                        aggregate_type="loan",
                        aggregate_id=loan.id,
                        payload={
                            "loan_id": loan.id,
                            "borrower_id": loan.borrower_id,
                            "due_at": loan.due_at.isoformat() if loan.due_at else None,
                        },
                    )
                    db.add(outbox)

            await db.commit()

if __name__ == "__main__":
    worker = BoconicWorker()
    try:
        asyncio.run(worker.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped.")

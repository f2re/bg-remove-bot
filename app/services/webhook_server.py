"""
Webhook server for Robokassa payment notifications
This should be run as a separate service alongside the bot
"""
import logging
from aiohttp import web
from typing import Optional

from app.database import get_db, init_db
from app.database.crud import mark_order_paid, get_order_by_invoice_id
from app.services.robokassa import RobokassaService
from app.config import settings

logger = logging.getLogger(__name__)


async def handle_robokassa_result(request: web.Request) -> web.Response:
    """
    Handle Robokassa ResultURL callback
    This is called after successful payment

    Expected parameters:
    - OutSum: Payment amount
    - InvId: Invoice ID (order ID in our system)
    - SignatureValue: MD5 signature
    """
    try:
        # Get parameters from query string
        out_sum = request.query.get('OutSum')
        inv_id = request.query.get('InvId')
        signature = request.query.get('SignatureValue')

        if not all([out_sum, inv_id, signature]):
            logger.error("Missing required parameters in Robokassa callback")
            return web.Response(text="Missing parameters", status=400)

        # Convert types
        try:
            out_sum = float(out_sum)
            inv_id = int(inv_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid parameter types: OutSum={out_sum}, InvId={inv_id}")
            return web.Response(text="Invalid parameters", status=400)

        # Verify signature
        robokassa = RobokassaService()
        if not robokassa.verify_result_signature(out_sum, inv_id, signature):
            logger.error(f"Invalid signature for invoice {inv_id}")
            return web.Response(text="Invalid signature", status=403)

        # Mark order as paid
        db = get_db()
        async with db.get_session() as session:
            # Find order by Robokassa invoice ID
            # Note: Robokassa uses InvId, we need to find our order
            from app.database.models import Order
            from sqlalchemy import select

            result = await session.execute(
                select(Order).where(Order.id == inv_id)
            )
            order = result.scalar_one_or_none()

            if not order:
                logger.error(f"Order not found for InvId {inv_id}")
                return web.Response(text="Order not found", status=404)

            if order.status == 'paid':
                logger.info(f"Order {inv_id} already marked as paid")
                return web.Response(text=f"OK{inv_id}")

            # Mark as paid
            await mark_order_paid(session, order.robokassa_invoice_id)
            logger.info(f"Order {inv_id} marked as paid successfully")

            # Send notifications (this will be handled by the bot via polling)
            # The bot will check for new paid orders and send notifications

        # Return success response (required by Robokassa)
        return web.Response(text=f"OK{inv_id}")

    except Exception as e:
        logger.error(f"Error processing Robokassa callback: {str(e)}")
        return web.Response(text="Internal error", status=500)


async def handle_robokassa_success(request: web.Request) -> web.Response:
    """
    Handle Robokassa SuccessURL callback
    This is where user is redirected after successful payment
    """
    # This is just a user-facing page, no processing needed
    return web.Response(
        text="<html><body><h1>Оплата прошла успешно!</h1><p>Изображения будут начислены на ваш баланс в течение минуты.</p></body></html>",
        content_type='text/html'
    )


async def handle_robokassa_fail(request: web.Request) -> web.Response:
    """
    Handle Robokassa FailURL callback
    This is where user is redirected after failed payment
    """
    return web.Response(
        text="<html><body><h1>Оплата не прошла</h1><p>Попробуйте еще раз или свяжитесь с поддержкой.</p></body></html>",
        content_type='text/html'
    )


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint"""
    return web.Response(text="OK")


def create_app() -> web.Application:
    """Create aiohttp application for webhook server"""
    app = web.Application()

    # Add routes
    app.router.add_get('/robokassa/result', handle_robokassa_result)
    app.router.add_post('/robokassa/result', handle_robokassa_result)
    app.router.add_get('/robokassa/success', handle_robokassa_success)
    app.router.add_get('/robokassa/fail', handle_robokassa_fail)
    app.router.add_get('/health', health_check)

    return app


async def run_webhook_server(host: str = '0.0.0.0', port: int = 8080):
    """Run webhook server"""
    # Initialize database
    logger.info("Initializing database for webhook server...")
    init_db(settings.database_url)

    app = create_app()

    logger.info(f"Starting webhook server on {host}:{port}")
    logger.info(f"Robokassa ResultURL: http://{host}:{port}/robokassa/result")
    logger.info(f"Robokassa SuccessURL: http://{host}:{port}/robokassa/success")
    logger.info(f"Robokassa FailURL: http://{host}:{port}/robokassa/fail")

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info("Webhook server started successfully")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_webhook_server())
    loop.run_forever()

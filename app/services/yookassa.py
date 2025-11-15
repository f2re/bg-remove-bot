"""YooKassa payment integration service"""
import uuid
from decimal import Decimal
from typing import Dict, Optional
import logging

from yookassa import Configuration, Payment
from yookassa.domain.notification import WebhookNotification

from app.config import settings

logger = logging.getLogger(__name__)


class YookassaService:
    """Service for YooKassa payment integration"""

    def __init__(self):
        """Initialize YooKassa configuration"""
        Configuration.configure(
            account_id=settings.YOOKASSA_SHOP_ID,
            secret_key=settings.YOOKASSA_SECRET_KEY
        )
        self.return_url = settings.YOOKASSA_RETURN_URL

    def create_payment(
        self,
        amount: float,
        description: str,
        order_id: str,
        user_email: Optional[str] = None,
        user_phone: Optional[str] = None
    ) -> Dict:
        """
        Create a new payment

        Args:
            amount: Payment amount in rubles
            description: Payment description
            order_id: Unique order identifier (used as idempotence key)
            user_email: User's email (optional)
            user_phone: User's phone (optional)

        Returns:
            Dict with payment info including confirmation URL and payment_id
        """
        try:
            # Prepare payment data
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": self.return_url
                },
                "capture": True,  # Auto-capture payment
                "description": description,
                "metadata": {
                    "order_id": order_id
                }
            }

            # Add receipt for fiscal law compliance (54-ФЗ)
            receipt = self._generate_receipt(
                amount=amount,
                description=description,
                user_email=user_email,
                user_phone=user_phone
            )
            if receipt:
                payment_data["receipt"] = receipt

            # Create payment with idempotence key
            idempotence_key = str(uuid.uuid4())
            payment = Payment.create(payment_data, idempotence_key)

            logger.info(f"Payment created: {payment.id} for order {order_id}")

            return {
                "payment_id": payment.id,
                "confirmation_url": payment.confirmation.confirmation_url,
                "status": payment.status,
                "amount": float(payment.amount.value)
            }

        except Exception as e:
            logger.error(f"Failed to create payment: {str(e)}")
            raise

    def get_payment_status(self, payment_id: str) -> Dict:
        """
        Get payment status by payment ID

        Args:
            payment_id: YooKassa payment ID

        Returns:
            Dict with payment status and details
        """
        try:
            payment = Payment.find_one(payment_id)

            return {
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.paid,
                "amount": float(payment.amount.value) if payment.amount else 0,
                "metadata": payment.metadata
            }

        except Exception as e:
            logger.error(f"Failed to get payment status: {str(e)}")
            raise

    def verify_webhook_notification(self, notification_data: dict) -> Optional[Dict]:
        """
        Verify and parse webhook notification from YooKassa

        Args:
            notification_data: Raw notification data from webhook

        Returns:
            Dict with payment info if valid, None otherwise
        """
        try:
            # YooKassa SDK automatically validates the notification
            notification = WebhookNotification(notification_data)
            payment = notification.object

            logger.info(f"Webhook received for payment {payment.id}, status: {payment.status}")

            return {
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.paid,
                "amount": float(payment.amount.value) if payment.amount else 0,
                "metadata": payment.metadata,
                "order_id": payment.metadata.get("order_id") if payment.metadata else None
            }

        except Exception as e:
            logger.error(f"Failed to verify webhook notification: {str(e)}")
            return None

    def cancel_payment(self, payment_id: str) -> bool:
        """
        Cancel a payment

        Args:
            payment_id: YooKassa payment ID

        Returns:
            True if cancelled successfully
        """
        try:
            idempotence_key = str(uuid.uuid4())
            Payment.cancel(payment_id, idempotence_key)
            logger.info(f"Payment {payment_id} cancelled")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel payment {payment_id}: {str(e)}")
            return False

    def _generate_receipt(
        self,
        amount: float,
        description: str,
        user_email: Optional[str] = None,
        user_phone: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Generate receipt data for Russian fiscal law (54-ФЗ)

        Args:
            amount: Payment amount in rubles
            description: Item description
            user_email: User's email
            user_phone: User's phone

        Returns:
            Receipt dictionary or None if no contact info provided
        """
        # Receipt requires either email or phone
        if not user_email and not user_phone:
            logger.warning("No email or phone provided, skipping receipt generation")
            return None

        receipt = {
            "customer": {},
            "items": [
                {
                    "description": description,
                    "quantity": "1",
                    "amount": {
                        "value": f"{amount:.2f}",
                        "currency": "RUB"
                    },
                    "vat_code": 1,  # НДС по ставке 20%
                    "payment_mode": "full_payment",
                    "payment_subject": "service"
                }
            ]
        }

        # Add customer contact info
        if user_email:
            receipt["customer"]["email"] = user_email
        if user_phone:
            receipt["customer"]["phone"] = user_phone

        return receipt

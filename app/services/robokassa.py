import hashlib
from typing import Dict
from urllib.parse import urlencode

from app.config import settings


class RobokassaService:
    """Service for Robokassa payment integration"""

    def __init__(self):
        self.login = settings.ROBOKASSA_LOGIN
        self.password1 = settings.ROBOKASSA_PASSWORD1
        self.password2 = settings.ROBOKASSA_PASSWORD2
        self.test_mode = settings.ROBOKASSA_TEST_MODE

    def generate_payment_link(self, order_id: int, amount: float, description: str,
                            user_email: str = None) -> str:
        """
        Generate payment link for Robokassa

        Args:
            order_id: Unique order ID
            amount: Payment amount in rubles
            description: Payment description
            user_email: User's email (optional)

        Returns:
            Payment URL
        """
        # Calculate signature
        signature = self._calculate_signature(amount, order_id, self.password1)

        # Build payment parameters
        params = {
            'MerchantLogin': self.login,
            'OutSum': f"{amount:.2f}",
            'InvId': order_id,
            'Description': description,
            'SignatureValue': signature,
            'IsTest': '1' if self.test_mode else '0'
        }

        if user_email:
            params['Email'] = user_email

        # Build URL
        base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
        return f"{base_url}?{urlencode(params)}"

    def verify_payment_signature(self, out_sum: float, inv_id: int, signature: str) -> bool:
        """
        Verify payment signature from Robokassa

        Args:
            out_sum: Payment amount
            inv_id: Invoice ID
            signature: Signature from Robokassa

        Returns:
            True if signature is valid
        """
        expected_signature = self._calculate_signature(out_sum, inv_id, self.password2)
        return signature.lower() == expected_signature.lower()

    def verify_result_signature(self, out_sum: float, inv_id: int, signature: str) -> bool:
        """
        Verify result signature (for ResultURL)

        Args:
            out_sum: Payment amount
            inv_id: Invoice ID
            signature: Signature from Robokassa

        Returns:
            True if signature is valid
        """
        return self.verify_payment_signature(out_sum, inv_id, signature)

    def _calculate_signature(self, amount: float, order_id: int, password: str) -> str:
        """
        Calculate MD5 signature for Robokassa

        Args:
            amount: Payment amount
            order_id: Order ID
            password: Robokassa password (1 or 2)

        Returns:
            MD5 signature
        """
        # Format: MerchantLogin:OutSum:InvId:Password
        signature_string = f"{self.login}:{amount:.2f}:{order_id}:{password}"
        return hashlib.md5(signature_string.encode()).hexdigest()

    def generate_receipt(self, items: list, user_email: str = None, user_phone: str = None) -> Dict:
        """
        Generate receipt data for ФЗ-54 (Russian fiscal law)

        Args:
            items: List of items [{"name": "...", "quantity": 1, "sum": 100.00, "tax": "none"}]
            user_email: User's email
            user_phone: User's phone

        Returns:
            Receipt dictionary
        """
        receipt = {
            "sno": "usn_income",  # Taxation system
            "items": []
        }

        for item in items:
            receipt["items"].append({
                "name": item.get("name", "Обработка изображений"),
                "quantity": item.get("quantity", 1),
                "sum": item.get("sum", 0),
                "payment_method": "full_payment",
                "payment_object": "service",
                "tax": item.get("tax", "none")
            })

        # Add contact info if provided
        if user_email:
            receipt["email"] = user_email
        if user_phone:
            receipt["phone"] = user_phone

        return receipt

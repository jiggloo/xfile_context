# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Notification service for sending alerts and messages."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.functional.test_codebase.core.models.order import Order
    from tests.functional.test_codebase.core.models.user import User


class NotificationType(Enum):
    """Types of notifications."""

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


@dataclass
class Notification:
    """Represents a notification to be sent."""

    recipient_id: str
    notification_type: NotificationType
    subject: str
    message: str
    created_at: datetime = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()


class NotificationHandler(ABC):
    """Abstract base class for notification handlers."""

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Send a notification.

        Args:
            notification: The notification to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        pass


class EmailHandler(NotificationHandler):
    """Handler for email notifications."""

    def send(self, notification: Notification) -> bool:
        """Send an email notification.

        Args:
            notification: The notification to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        # In a real implementation, this would send an actual email
        logging.info(f"Sending email to {notification.recipient_id}: {notification.subject}")
        return True


class SMSHandler(NotificationHandler):
    """Handler for SMS notifications."""

    def send(self, notification: Notification) -> bool:
        """Send an SMS notification.

        Args:
            notification: The notification to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        # In a real implementation, this would send an actual SMS
        logging.info(f"Sending SMS to {notification.recipient_id}: {notification.message[:50]}")
        return True


class NotificationService:
    """Service for managing and sending notifications."""

    def __init__(self) -> None:
        """Initialize the notification service."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.handlers: dict[NotificationType, NotificationHandler] = {
            NotificationType.EMAIL: EmailHandler(),
            NotificationType.SMS: SMSHandler(),
        }
        self.sent_notifications: list[Notification] = []

    def send(
        self,
        recipient_id: str,
        notification_type: NotificationType,
        subject: str,
        message: str,
    ) -> bool:
        """Send a notification.

        Args:
            recipient_id: The recipient's ID.
            notification_type: The type of notification.
            subject: The notification subject.
            message: The notification message.

        Returns:
            True if sent successfully, False otherwise.
        """
        notification = Notification(
            recipient_id=recipient_id,
            notification_type=notification_type,
            subject=subject,
            message=message,
        )

        handler = self.handlers.get(notification_type)
        if not handler:
            self.logger.error(f"No handler for notification type: {notification_type}")
            return False

        success = handler.send(notification)
        if success:
            self.sent_notifications.append(notification)
            self.logger.info(f"Notification sent: {subject} to {recipient_id}")
        else:
            self.logger.error(f"Failed to send notification: {subject} to {recipient_id}")

        return success

    def send_order_confirmation(self, order: Order) -> bool:
        """Send an order confirmation notification.

        Args:
            order: The order that was confirmed.

        Returns:
            True if sent successfully, False otherwise.
        """
        return self.send(
            recipient_id=order.user_id,
            notification_type=NotificationType.EMAIL,
            subject=f"Order Confirmed: {order.id}",
            message=f"Your order {order.id} has been confirmed. Total: {order.formatted_total}",
        )

    def send_order_cancellation(self, order: Order) -> bool:
        """Send an order cancellation notification.

        Args:
            order: The order that was cancelled.

        Returns:
            True if sent successfully, False otherwise.
        """
        return self.send(
            recipient_id=order.user_id,
            notification_type=NotificationType.EMAIL,
            subject=f"Order Cancelled: {order.id}",
            message=f"Your order {order.id} has been cancelled.",
        )

    def send_shipping_notification(self, order: Order) -> bool:
        """Send a shipping notification.

        Args:
            order: The order that was shipped.

        Returns:
            True if sent successfully, False otherwise.
        """
        return self.send(
            recipient_id=order.user_id,
            notification_type=NotificationType.EMAIL,
            subject=f"Order Shipped: {order.id}",
            message=f"Your order {order.id} has been shipped!",
        )

    def send_delivery_notification(self, order: Order) -> bool:
        """Send a delivery notification.

        Args:
            order: The order that was delivered.

        Returns:
            True if sent successfully, False otherwise.
        """
        return self.send(
            recipient_id=order.user_id,
            notification_type=NotificationType.EMAIL,
            subject=f"Order Delivered: {order.id}",
            message=f"Your order {order.id} has been delivered!",
        )

    def send_welcome(self, user: User) -> bool:
        """Send a welcome notification to a new user.

        Args:
            user: The new user.

        Returns:
            True if sent successfully, False otherwise.
        """
        return self.send(
            recipient_id=user.id,
            notification_type=NotificationType.EMAIL,
            subject="Welcome!",
            message=f"Welcome {user.full_name}! Thank you for joining us.",
        )

    def get_recent_notifications(self, count: int = 10) -> list[Notification]:
        """Get recent notifications.

        Args:
            count: The number of recent notifications to return.

        Returns:
            A list of recent notifications.
        """
        return self.sent_notifications[-count:]

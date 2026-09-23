"""Internal notification outbox.

Records that something happened which someone should know about. It does not
deliver anything: no email, no SMS, no HTTP call, no third-party credentials.
Every row is written with status "pending" and stays that way.

The split is deliberate. Recording an event and delivering it have different
failure modes — a health alert must not be lost because a mail server is down,
and a sync must not be slowed down waiting on one. When a channel is chosen
later, it becomes a reader of `pending` rows; nothing here has to change.

    emit_health_alert(alert, event="created")   -> Notification row (pending)
    pending()                                   -> what a sender would pick up
"""

from __future__ import annotations

from models import Notification, db

EVENT_HEALTH_ALERT = "health_alert"

# Which alert events are worth a notification. An alert seen again on a later
# sync is not news; a new one, a recurrence, or one that got worse is.
NOTIFIABLE_EVENTS = frozenset({"created", "reopened", "escalated"})

# Below this, an alert is recorded but no notification is raised. Keeps a
# routine "vaccination due in three weeks" out of the queue.
MIN_NOTIFY_SEVERITY = "moderate"
SEVERITY_ORDER = ["low", "moderate", "high", "critical"]


def should_notify(event: str, severity: str) -> bool:
    return (
        event in NOTIFIABLE_EVENTS
        and SEVERITY_ORDER.index(severity) >= SEVERITY_ORDER.index(MIN_NOTIFY_SEVERITY)
    )


def emit_health_alert(alert, event: str = "created", previous_severity: str | None = None):
    """Queue a notification for an alert, if it clears the bar.

    Adds to the session but does not commit: the caller commits the alert and
    its notification together, so an outbox row can never describe an alert
    that was not saved.
    """
    if not should_notify(event, alert.severity):
        return None

    payload = {
        "type": EVENT_HEALTH_ALERT,
        "event": event,
        "dog_id": alert.dog_id,
        "dog_name": alert.dog.name if alert.dog else None,
        "alert_id": alert.id,
        "severity": alert.severity,
        "category": alert.category,
        "finding_code": alert.finding_code,
        "title": alert.title,
        "reason": alert.reason,
    }
    if previous_severity:
        payload["previous_severity"] = previous_severity

    notification = Notification(
        event_type=EVENT_HEALTH_ALERT,
        dog_id=alert.dog_id,
        alert_id=alert.id,
        severity=alert.severity,
        payload=payload,
        status="pending",
        channel="internal",
    )
    db.session.add(notification)
    return notification


def pending(limit: int | None = None) -> list[Notification]:
    """Undelivered notifications, oldest first — what a future sender reads."""
    query = Notification.query.filter_by(status="pending").order_by(Notification.created_at)
    return query.limit(limit).all() if limit else query.all()

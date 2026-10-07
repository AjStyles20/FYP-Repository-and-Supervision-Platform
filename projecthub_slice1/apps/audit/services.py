from .models import AuditEvent


def log_event(*, actor, action, summary, obj=None, details=None):
    """Append a human-readable action record for the admin audit screen."""
    if (actor is not None and getattr(actor, "is_demo", False)) or (obj is not None and getattr(obj, "is_demo", False)):
        return None
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label if obj is not None else "",
        object_id=str(obj.pk) if obj is not None and obj.pk is not None else "",
        summary=summary,
        details=details or {},
    )

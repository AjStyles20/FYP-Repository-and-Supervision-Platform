"""{% contact_for person as rows %}: the contact details the signed-in viewer may see for `person`."""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def contact_for(context, person):
    request = context.get("request")
    if person is None or request is None:
        return []
    return person.contact_for(request.user)

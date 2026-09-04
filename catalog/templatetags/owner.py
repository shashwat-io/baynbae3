"""`{% owner "what is needed" %}`: the owner-input placeholder, available in every template."""

from django import template

from catalog.placeholders import owner as owner_placeholder

register = template.Library()


@register.simple_tag(name="owner")
def owner_tag(what):
    return owner_placeholder(what)

"""
Visible stand-ins for brand facts the owner has not supplied yet.

The rule (PROJECT.md, owner inputs): a missing value is never guessed. It is
rendered as a `<mark class="todo">` so it is obvious on the page and easy to
grep for, and it stays until the owner provides the real value.
"""

from django.utils.html import format_html


def owner(what):
    """The placeholder for one missing fact, e.g. ``owner("dispatch city")``."""
    return format_html('<mark class="todo">[OWNER: {}]</mark>', what)

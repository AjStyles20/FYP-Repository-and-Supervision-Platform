"""{% semester_codes %}: the semesters already in use, offered as suggestions in every semester box."""

from django import template
from django.utils.html import format_html, format_html_join

from apps.academics.models import Semester

register = template.Library()


@register.simple_tag
def semester_codes():
    options = format_html_join("", '<option value="{}"></option>', ((code,) for code in Semester.objects.values_list("code", flat=True)))
    return format_html('<datalist id="semester-codes">{}</datalist>', options)

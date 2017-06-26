# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-06-26 20:33
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


def add_default_site(apps, schema_editor):
    # We can't import the Person model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Site = apps.get_model('sites', 'Site')
    current = Site.objects.get_current()
    current.name = settings.EVENT_NAME
    current.domain = settings.EVENT_DOMAIN
    current.save()


class Migration(migrations.Migration):
    dependencies = [
        ('register', '0004_add_nulls'),
    ]

    operations = [
        migrations.RunPython(add_default_site),
    ]

# Generated by Django 4.0.3 on 2022-04-05 13:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0010_alter_githubpullrequest_pr_body'),
    ]

    operations = [
        migrations.AddField(
            model_name='githubpullrequest',
            name='pr_owner_username',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
    ]

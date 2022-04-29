# Generated by Django 4.0.4 on 2022-04-28 10:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0018_alter_githubappinstallation_state_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='GithubMarketplaceEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payload', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
# Generated by Django 4.0.3 on 2022-03-30 09:20

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0005_githubpullrequest_repository'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='githubcheckrun',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='githubcheckrun',
            name='repository',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, related_name='checks', to='app.githubrepository'),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='githubcheckrun',
            unique_together={('head_sha', 'repository')},
        ),
        migrations.RemoveField(
            model_name='githubcheckrun',
            name='pull_request',
        ),
    ]

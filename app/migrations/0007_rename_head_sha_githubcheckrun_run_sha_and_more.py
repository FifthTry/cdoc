# Generated by Django 4.0.3 on 2022-03-30 10:40

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0006_alter_githubcheckrun_unique_together_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='githubcheckrun',
            old_name='head_sha',
            new_name='run_sha',
        ),
        migrations.AlterUniqueTogether(
            name='githubcheckrun',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='githubcheckrun',
            name='ref_pull_request',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, related_name='checks', to='app.monitoredpullrequest'),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='githubcheckrun',
            unique_together={('run_sha', 'ref_pull_request')},
        ),
        migrations.RemoveField(
            model_name='githubcheckrun',
            name='repository',
        ),
    ]
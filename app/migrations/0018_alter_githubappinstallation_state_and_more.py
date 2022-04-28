# Generated by Django 4.0.4 on 2022-04-28 09:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0017_prapproval'),
    ]

    operations = [
        migrations.AlterField(
            model_name='githubappinstallation',
            name='state',
            field=models.CharField(choices=[('INSTALLED', 'Installed'), ('UNINSTALLED', 'Uninstalled'), ('SUSPENDED', 'Suspended')], max_length=20),
        ),
        migrations.AlterField(
            model_name='githubrepository',
            name='repo_full_name',
            field=models.CharField(max_length=200),
        ),
        migrations.AlterUniqueTogether(
            name='githubrepository',
            unique_together={('repo_id', 'owner')},
        ),
    ]

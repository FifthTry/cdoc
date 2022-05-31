# Generated by Django 4.0.4 on 2022-05-28 14:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0024_rename_githubrepomap_monitoredrepositorymap_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userrepoaccess',
            name='access',
            field=models.IntegerField(choices=[('50', 'Owner'), ('40', 'Maintainer'), ('30', 'Developer'), ('20', 'Reporter'), ('10', 'Guest'), ('5', 'Minimal'), ('0', 'No Access')], max_length=20),
        ),
    ]
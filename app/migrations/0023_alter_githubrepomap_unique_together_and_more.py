# Generated by Django 4.0.4 on 2022-05-28 10:29

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0022_alter_repository_unique_together_repository_app_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='githubrepomap',
            unique_together={('code_repo', 'documentation_repo')},
        ),
        migrations.RemoveField(
            model_name='githubrepomap',
            name='integration',
        ),
    ]
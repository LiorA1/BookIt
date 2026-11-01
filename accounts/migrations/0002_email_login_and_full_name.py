import accounts.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelManagers(
            name="customuser",
            managers=[
                ("objects", accounts.models.CustomUserManager()),
            ],
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="username",
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="first_name",
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="last_name",
        ),
        migrations.AddField(
            model_name="customuser",
            name="full_name",
            field=models.CharField(default="", max_length=150, verbose_name="full name"),
            preserve_default=False,
        ),
    ]

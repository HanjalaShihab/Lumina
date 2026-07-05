from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("enhancer", "0002_add_user_to_enhancementjob"),
    ]

    operations = [
        migrations.AlterField(
            model_name="enhancementjob",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="enhancements",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

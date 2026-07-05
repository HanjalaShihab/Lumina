from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_job_users(apps, schema_editor):
    User = apps.get_model("auth", "User")
    EnhancementJob = apps.get_model("enhancer", "EnhancementJob")

    user = User.objects.order_by("pk").first()
    if user is None:
        return

    EnhancementJob.objects.filter(user__isnull=True).update(user=user)


class Migration(migrations.Migration):
    dependencies = [
        ("enhancer", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="enhancementjob",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="enhancements",
                null=True,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_job_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="enhancementjob",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="enhancements",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

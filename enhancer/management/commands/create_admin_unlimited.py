from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create/ensure an admin unlimited user (is_staff/is_superuser)."

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, default="user-HMSHIHAB")
        parser.add_argument("--password", type=str, default="Iamshihab1402")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        password = options["password"]

        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured admin unlimited user: {username} (created={created})"
            )
        )


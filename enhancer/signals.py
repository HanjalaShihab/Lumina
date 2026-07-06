from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserCredit


@receiver(post_save, sender=User)
def create_user_credit(sender, instance, created, **kwargs):
    """Auto-create a UserCredit with free tokens when a user signs up."""
    if created:
        UserCredit.objects.create(user=instance)

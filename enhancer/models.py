from django.conf import settings
from django.db import models


class UserCredit(models.Model):
    """Tracks token balance for registered users."""

    FREE_TOKENS = 10

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit",
    )
    tokens = models.PositiveIntegerField(default=FREE_TOKENS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Credit"
        verbose_name_plural = "User Credits"

    def __str__(self):
        return f"{self.user.username}: {self.tokens} tokens"

    def has_tokens(self, amount=1):
        return self.tokens >= amount

    def deduct(self, amount=1):
        if self.tokens >= amount:
            self.tokens -= amount
            self.save(update_fields=["tokens", "updated_at"])
            return True
        return False

    def add_tokens(self, amount):
        self.tokens += amount
        self.save(update_fields=["tokens", "updated_at"])


class AnonymousCredit(models.Model):
    """Token balance for anonymous users, persisted by a cookie-backed client_id."""

    client_id = models.CharField(max_length=64, unique=True, db_index=True)
    tokens = models.PositiveIntegerField(default=UserCredit.FREE_TOKENS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Anonymous Credit"
        verbose_name_plural = "Anonymous Credits"

    def __str__(self):
        return f"anon:{self.client_id} -> {self.tokens} tokens"


class EnhancementJob(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enhancements",
        null=True,
        blank=True,
    )
    MODE_MANUAL = "manual"
    MODE_AI = "ai"
    MODE_BATCH = "batch"
    MODE_BACKGROUND = "background"

    MODE_CHOICES = [
        (MODE_MANUAL, "Manual"),
        (MODE_AI, "AI Enhanced"),
        (MODE_BATCH, "Batch"),
        (MODE_BACKGROUND, "Background Removal"),
    ]

    title = models.CharField(max_length=120, blank=True)
    original = models.ImageField(upload_to="uploads/originals/")
    enhanced = models.ImageField(upload_to="uploads/enhanced/", blank=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_AI)
    brightness = models.FloatField(default=1.0)
    contrast = models.FloatField(default=1.0)
    sharpness = models.FloatField(default=1.0)
    saturation = models.FloatField(default=1.0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Enhancement #{self.pk}"


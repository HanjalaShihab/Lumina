from django.db import models


class EnhancementJob(models.Model):
    MODE_MANUAL = "manual"
    MODE_AI = "ai"
    MODE_BATCH = "batch"

    MODE_CHOICES = [
        (MODE_MANUAL, "Manual"),
        (MODE_AI, "AI Enhanced"),
        (MODE_BATCH, "Batch"),
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

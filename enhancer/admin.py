from django.contrib import admin

from .models import EnhancementJob


@admin.register(EnhancementJob)
class EnhancementJobAdmin(admin.ModelAdmin):
    list_display = ("title", "mode", "created_at")
    list_filter = ("mode", "created_at")
    search_fields = ("title", "notes")
    readonly_fields = ("created_at",)

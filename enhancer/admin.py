from django.contrib import admin

from .models import EnhancementJob, UserCredit


@admin.register(UserCredit)
class UserCreditAdmin(admin.ModelAdmin):
    list_display = ("user", "tokens", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(EnhancementJob)
class EnhancementJobAdmin(admin.ModelAdmin):
    list_display = ("title", "mode", "user", "created_at")
    list_filter = ("mode", "created_at")
    search_fields = ("title", "notes", "user__username")
    readonly_fields = ("created_at",)

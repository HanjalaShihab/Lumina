from django.urls import path

from . import views


app_name = "enhancer"

urlpatterns = [
    path("", views.home, name="home"),
    path("manual/", views.manual, name="manual"),
    path("ai/", views.ai_enhancer, name="ai_enhancer"),
    path("batch/", views.batch, name="batch"),
    path("history/", views.history, name="history"),
    path("history/<int:pk>/", views.detail, name="detail"),
]

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "enhancer"

urlpatterns = [
    # Main Pages
    path("", views.home, name="home"),
    path("manual/", views.manual, name="manual"),
    path("ai/", views.ai_enhancer, name="ai_enhancer"),
    path("batch/", views.batch, name="batch"),
    path("background/", views.background_remover, name="background_remover"),
    path("history/", views.history, name="history"),
    path("history/<int:pk>/", views.detail, name="detail"),
    path("upgrade/", views.upgrade, name="upgrade"),
    path("delete/<int:pk>/", views.delete_enhancement, name="delete_enhancement"),
    
    # Authentication - Using registration folder
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(
        template_name="registration/login.html"
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="enhancer:home"), name="logout"),
]
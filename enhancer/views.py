from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .ai_engine import enhance_image
from .forms import BatchEnhancementForm, ImageUploadForm, ManualEnhancementForm
from .models import EnhancementJob


def upgrade(request):
    return render(request, "enhancer/upgrade.html")


def home(request):
    recent_jobs = EnhancementJob.objects.all()[:6]
    return render(request, "enhancer/home.html", {"recent_jobs": recent_jobs})


def manual(request):
    result = None
    if request.method == "POST":
        form = ManualEnhancementForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save(commit=False)
            job.mode = EnhancementJob.MODE_MANUAL
            job.save()
            result = enhance_image(job, mode="manual")
            messages.success(request, "Manual enhancement complete.")
    else:
        form = ManualEnhancementForm()
    return render(request, "enhancer/manual.html", {"form": form, "result": result})


def ai_enhancer(request):
    result = None
    if request.method == "POST":
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save(commit=False)
            job.mode = EnhancementJob.MODE_AI
            job.save()
            result = enhance_image(job, mode="ai")
            messages.success(request, "AI enhancement complete.")
    else:
        form = ImageUploadForm()
    return render(request, "enhancer/ai_enhancer.html", {"form": form, "result": result})


def batch(request):
    results = []
    if request.method == "POST":
        form = BatchEnhancementForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("images")
            for uploaded in files:
                job = EnhancementJob.objects.create(
                    title=uploaded.name.rsplit(".", 1)[0],
                    original=uploaded,
                    mode=EnhancementJob.MODE_BATCH,
                )
                results.append(enhance_image(job, mode="ai"))
            messages.success(request, f"Enhanced {len(results)} image(s).")
    else:
        form = BatchEnhancementForm()
    return render(request, "enhancer/batch.html", {"form": form, "results": results})


def history(request):
    jobs = EnhancementJob.objects.all()
    return render(request, "enhancer/history.html", {"jobs": jobs})


def detail(request, pk):
    job = get_object_or_404(EnhancementJob, pk=pk)
    return render(request, "enhancer/history.html", {"jobs": [job], "focused": job})


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("enhancer:home")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})


def delete_enhancement(request, pk: int):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method"}, status=405)

    job = get_object_or_404(EnhancementJob, pk=pk)
    job.delete()
    return JsonResponse({"success": True})

from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .ai_engine import enhance_image, remove_background
from .forms import BatchEnhancementForm, BackgroundRemovalForm, ImageUploadForm, ManualEnhancementForm
from .models import EnhancementJob


def upgrade(request):
    """Token upgrade page"""
    return render(request, "enhancer/upgrade.html")


def home(request):
    """Home page with recent jobs"""
    if request.user.is_authenticated:
        recent_jobs = EnhancementJob.objects.filter(user=request.user).order_by('-created_at')[:6]
    else:
        recent_jobs = EnhancementJob.objects.none()
    return render(request, "enhancer/home.html", {"recent_jobs": recent_jobs})


def signup(request):
    """User signup view"""
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully! Welcome to Lumina.")
            return redirect("enhancer:home")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def manual(request):
    """Manual enhancement view"""
    result = None
    if request.method == "POST":
        form = ManualEnhancementForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save(commit=False)
            job.user = request.user
            job.mode = EnhancementJob.MODE_MANUAL
            job.save()
            manual_adjustments = {
                "color": request.POST.get("color", "50"),
                "tone": request.POST.get("tone", "50"),
                "contrast": request.POST.get("contrast", "50"),
                "vibrance": request.POST.get("vibrance", "50"),
                "denoise": request.POST.get("denoise", "50"),
                "sharpen": request.POST.get("sharpen", "50"),
                "exposure": request.POST.get("exposure", "50"),
                "warmth": request.POST.get("warmth", "50"),
                "shadows": request.POST.get("shadows", "50"),
                "highlights": request.POST.get("highlights", "50"),
            }
            result = enhance_image(job, mode="manual", adjustments=manual_adjustments)
            messages.success(request, "Manual enhancement complete.")
    else:
        form = ManualEnhancementForm()
    return render(request, "enhancer/manual.html", {"form": form, "result": result})


@login_required
def ai_enhancer(request):
    """AI enhancement view"""
    result = None
    if request.method == "POST":
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save(commit=False)
            job.user = request.user
            job.mode = EnhancementJob.MODE_AI
            job.save()
            result = enhance_image(job, mode="ai")
            messages.success(request, "AI enhancement complete.")
    else:
        form = ImageUploadForm()
    return render(request, "enhancer/ai_enhancer.html", {"form": form, "result": result})


@login_required
def batch(request):
    """Batch enhancement view"""
    results = []
    if request.method == "POST":
        form = BatchEnhancementForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("images")
            for uploaded in files:
                job = EnhancementJob.objects.create(
                    title=uploaded.name.rsplit(".", 1)[0],
                    original=uploaded,
                    user=request.user,
                    mode=EnhancementJob.MODE_BATCH,
                )
                results.append(enhance_image(job, mode="ai"))
            messages.success(request, f"Enhanced {len(results)} image(s).")
    else:
        form = BatchEnhancementForm()
    return render(request, "enhancer/batch.html", {"form": form, "results": results})


@login_required
def background_remover(request):
    """Background removal view"""
    result = None
    if request.method == "POST":
        form = BackgroundRemovalForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save(commit=False)
            job.user = request.user
            job.mode = EnhancementJob.MODE_BACKGROUND
            job.save()
            result = remove_background(job)
            messages.success(request, "Background removal complete.")
    else:
        form = BackgroundRemovalForm()
    return render(request, "enhancer/background_remover.html", {"form": form, "result": result})


@login_required
def history(request):
    """History page with pagination and stats"""
    jobs = EnhancementJob.objects.filter(user=request.user).order_by('-created_at')
    
    # Count by mode for stats
    ai_count = jobs.filter(mode=EnhancementJob.MODE_AI).count()
    manual_count = jobs.filter(mode=EnhancementJob.MODE_MANUAL).count()
    batch_count = jobs.filter(mode=EnhancementJob.MODE_BATCH).count()
    background_count = jobs.filter(mode=EnhancementJob.MODE_BACKGROUND).count()
    
    paginator = Paginator(jobs, 10)  # 10 items per page
    
    page = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    context = {
        'page_obj': page_obj,
        'focused': None,
        'ai_count': ai_count,
        'manual_count': manual_count,
        'batch_count': batch_count,
        'background_count': background_count,
    }
    return render(request, "enhancer/history.html", context)


@login_required
def detail(request, pk):
    """Detail view for a single enhancement"""
    job = get_object_or_404(EnhancementJob, pk=pk, user=request.user)
    
    # Create a single-item page_obj for consistent template
    paginator = Paginator([job], 1)
    page_obj = paginator.page(1)
    
    context = {
        'page_obj': page_obj,
        'focused': job,
        'ai_count': 0,
        'manual_count': 0,
        'batch_count': 0,
    }
    return render(request, "enhancer/history.html", context)


@login_required
def delete_enhancement(request, pk):
    """Delete an enhancement via AJAX"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method"}, status=405)
    
    job = get_object_or_404(EnhancementJob, pk=pk, user=request.user)
    
    # Delete associated files
    if job.original:
        job.original.delete()
    if job.enhanced:
        job.enhanced.delete()
    
    job.delete()
    return JsonResponse({"success": True})
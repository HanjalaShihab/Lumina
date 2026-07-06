from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .ai_engine import enhance_image, remove_background
from .forms import BatchEnhancementForm, BackgroundRemovalForm, ImageUploadForm, ManualEnhancementForm
from .models import AnonymousCredit, EnhancementJob, UserCredit


import uuid

# ── Token constants ──────────────────────────────────────────────
TOKENS_PER_USAGE = 3      # cost per image enhancement
FREE_TOKENS = 10          # free tokens for any user
SESSION_TOKEN_KEY = "lumina_anon_tokens"
ANON_CLIENT_COOKIE = "lumina_anon_client"
ANON_CLIENT_COOKIE_MAX_AGE = 3 * 24 * 60 * 60  # ~3 days



# ── Credit helpers ───────────────────────────────────────────────

def _get_anon_client_id(request):
    client_id = request.COOKIES.get(ANON_CLIENT_COOKIE)
    if not client_id:
        client_id = str(uuid.uuid4())
        request.new_anon_client_id = client_id
    return client_id





def _session_tokens(request):
    """Get anonymous token balance.

    Uses persistent AnonymousCredit keyed by cookie client_id.
    """
    client_id = _get_anon_client_id(request)
    credit, _ = AnonymousCredit.objects.get_or_create(client_id=client_id)
    return max(0, credit.tokens)




def _deduct_session_tokens(request, amount):
    """Deduct tokens from persistent AnonymousCredit."""
    client_id = _get_anon_client_id(request)
    credit, _ = AnonymousCredit.objects.get_or_create(client_id=client_id)
    if credit.tokens >= amount:
        credit.tokens -= amount
        credit.save(update_fields=["tokens", "updated_at"])
    else:
        credit.tokens = 0
        credit.save(update_fields=["tokens", "updated_at"])
    return credit.tokens




def get_display_tokens(request):
    """Return the visible token count for the navbar.
    Staff/superusers see '∞' (unlimited).
    """
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return "∞"
        credit = UserCredit.objects.filter(user=request.user).first()
        return credit.tokens if credit else 0
    return _session_tokens(request)




def check_credits(request, cost=TOKENS_PER_USAGE):
    """
    Check if the user can afford *cost* tokens.
    Admin/staff users have unlimited access (no token check).
    Returns True if they can, False if they should be redirected.
    Sets a redirect message and you should return the caller early.
    """
    # Staff/superusers have unlimited access
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return True

    if request.user.is_authenticated:
        credit = UserCredit.objects.filter(user=request.user).first()
        if not credit or credit.tokens < cost:
            upgrade_url = reverse("enhancer:upgrade")
            messages.warning(
                request,
                f"You need {cost} tokens for this feature, but you only have "
                f"{credit.tokens if credit else 0}. "
                f"<a href='{upgrade_url}' "
                f"style='color:var(--text-accent);text-decoration:underline;'>Buy more tokens</a>.",
            )
            return False
        return True
    else:
        available = _session_tokens(request)
        if available < cost:
            signup_url = reverse("enhancer:signup")
            messages.info(
                request,
                f"You've used your {FREE_TOKENS} free tokens. "
                f"<a href='{signup_url}' "
                f"style='color:var(--text-accent);text-decoration:underline;'>Sign up</a> "
                f"for more credits.",
            )
            return False
        return True


def deduct_credits(request, cost=TOKENS_PER_USAGE):
    """Deduct *cost* tokens. Staff/superusers are never charged."""
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return  # Unlimited — no deduction
    if request.user.is_authenticated:
        credit = UserCredit.objects.filter(user=request.user).first()
        if credit:
            credit.deduct(cost)
    else:
        _deduct_session_tokens(request, cost)


# ── Context processor for templates ──────────────────────────────

def tokens_context(request):
    """Injects 'available_tokens' into all templates."""
    return {"available_tokens": get_display_tokens(request)}


def _maybe_set_anon_cookie(response, request):
    """Attach anon client_id cookie for ~3 days so tokens persist."""
    client_id = getattr(request, "new_anon_client_id", None)
    if not client_id:
        return response
    response.set_cookie(
        ANON_CLIENT_COOKIE,
        client_id,
        max_age=ANON_CLIENT_COOKIE_MAX_AGE,
        httponly=False,
        samesite="Lax",
    )
    return response



# ── Views ────────────────────────────────────────────────────────


def upgrade(request):
    """Token purchase page."""
    purchase_amount = None
    if request.method == "POST":
        package = request.POST.get("package")
        # package value is the UI token amount; keep mapping as-is.
        mapping = {"10": 12, "50": 100, "100": 250, "250": 500}

        amount = mapping.get(package, 10)

        if request.user.is_authenticated:
            credit, _ = UserCredit.objects.get_or_create(user=request.user)
            credit.add_tokens(amount)

            messages.success(request, f"{amount} tokens added to your account!")
        else:
            signup_url = reverse("enhancer:signup")
            messages.info(
                request,
                f"<a href='{signup_url}' "
                f"style='color:var(--text-accent);text-decoration:underline;'>Sign up</a> "
                f"first to purchase tokens.",
            )
            return redirect("enhancer:signup")
        return redirect("enhancer:home")

    return render(request, "enhancer/upgrade.html")


def home(request):
    """Home page with recent jobs"""
    if request.user.is_authenticated:
        recent_jobs = EnhancementJob.objects.filter(user=request.user).order_by("-created_at")[:6]
    else:
        recent_jobs = EnhancementJob.objects.none()
    return render(request, "enhancer/home.html", {"recent_jobs": recent_jobs})


def signup(request):
    """User signup view — UserCredit is auto-created via signal."""
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


def manual(request):
    """Manual enhancement view"""
    result = None

    if request.method == "POST":
        form = ManualEnhancementForm(request.POST, request.FILES)
        if form.is_valid():
            # ── Credit check ──
            if not check_credits(request):
                return redirect("enhancer:manual")

            job = form.save(commit=False)
            if request.user.is_authenticated:
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

            # ── Deduct credits after successful processing ──
            deduct_credits(request)
            messages.success(request, "Manual enhancement complete.")
    else:
        form = ManualEnhancementForm()

    return render(request, "enhancer/manual.html", {"form": form, "result": result})


def ai_enhancer(request):
    """AI enhancement view"""
    result = None

    if request.method == "POST":
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # ── Credit check ──
            if not check_credits(request):
                return redirect("enhancer:ai_enhancer")

            job = form.save(commit=False)
            if request.user.is_authenticated:
                job.user = request.user
            job.mode = EnhancementJob.MODE_AI
            job.save()
            result = enhance_image(job, mode="ai")

            # ── Deduct credits ──
            deduct_credits(request)
            messages.success(request, "AI enhancement complete.")
    else:
        form = ImageUploadForm()

    return render(request, "enhancer/ai_enhancer.html", {"form": form, "result": result})


def batch(request):
    """Batch enhancement view."""
    results = []

    if request.method == "POST":
        form = BatchEnhancementForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("images")
            cost = len(files) * TOKENS_PER_USAGE

            if not check_credits(request, cost):
                return redirect("enhancer:batch")

            for uploaded in files:
                job = EnhancementJob.objects.create(
                    title=uploaded.name.rsplit(".", 1)[0],
                    original=uploaded,
                    user=request.user,
                    mode=EnhancementJob.MODE_BATCH,
                )
                results.append(enhance_image(job, mode="ai"))

            deduct_credits(request, cost)
            messages.success(request, f"Enhanced {len(results)} image(s).")
    else:
        form = BatchEnhancementForm()

    response = render(
        request,
        "enhancer/batch.html",
        {"form": form, "results": results},
    )
    return _maybe_set_anon_cookie(response, request)





def background_remover(request):
    """Background removal view."""
    result = None

    if request.method == "POST":
        form = BackgroundRemovalForm(request.POST, request.FILES)
        if form.is_valid():
            if not check_credits(request):
                return redirect("enhancer:background_remover")

            job = form.save(commit=False)
            job.user = request.user
            job.mode = EnhancementJob.MODE_BACKGROUND
            job.save()
            result = remove_background(job)

            deduct_credits(request)
            messages.success(request, "Background removal complete.")
    else:
        form = BackgroundRemovalForm()

    response = render(
        request,
        "enhancer/background_remover.html",
        {"form": form, "result": result},
    )
    return _maybe_set_anon_cookie(response, request)




def history(request):
    """History page (login required)."""
    if not request.user.is_authenticated:
        # Render as a green info message when user is not logged in
        messages.add_message(
            request,
            messages.INFO,
            "Please sign up or log in to view your history.",
            extra_tags="locked-history",
        )
        return redirect("enhancer:ai_enhancer")

    jobs = EnhancementJob.objects.filter(user=request.user).order_by("-created_at")



    ai_count = jobs.filter(mode=EnhancementJob.MODE_AI).count()
    manual_count = jobs.filter(mode=EnhancementJob.MODE_MANUAL).count()
    batch_count = jobs.filter(mode=EnhancementJob.MODE_BATCH).count()
    background_count = jobs.filter(mode=EnhancementJob.MODE_BACKGROUND).count()

    paginator = Paginator(jobs, 10)
    page = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "page_obj": page_obj,
        "focused": None,
        "ai_count": ai_count,
        "manual_count": manual_count,
        "batch_count": batch_count,
        "background_count": background_count,
    }
    return render(request, "enhancer/history.html", context)


def detail(request, pk):
    """Detail view for a single enhancement"""
    job = get_object_or_404(EnhancementJob, pk=pk, user=request.user)
    paginator = Paginator([job], 1)
    page_obj = paginator.page(1)
    context = {
        "page_obj": page_obj,
        "focused": job,
        "ai_count": 0,
        "manual_count": 0,
        "batch_count": 0,
    }
    return render(request, "enhancer/history.html", context)


def contact(request):
    from django.conf import settings
    from django.core.mail import send_mail

    CONTACT_TO_EMAIL = "hanjalashihab1@gmail.com"

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        message = request.POST.get("message", "").strip()

        if not message:
            messages.error(request, "Please write a message before sending.")
            return render(request, "enhancer/contact.html")

        # Best-effort email sending (won't crash the page if email isn't configured).
        subject = f"Lumina Contact Form - {name or 'Anonymous'}"
        body = (
            f"Name: {name or 'Anonymous'}\n"
            f"Email: {email or '(not provided)'}\n\n"
            f"Message:\n{message}\n"
        )

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@lumina.local"),
                recipient_list=[CONTACT_TO_EMAIL],
                fail_silently=False,
            )
        except Exception:
            # If SMTP isn't configured, still accept the message.
            pass

        messages.success(request, "Message received. We will contact you soon.")
        return redirect("enhancer:contact")

    return render(request, "enhancer/contact.html")




def delete_enhancement(request, pk):
    """Delete an enhancement via AJAX"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method"}, status=405)

    job = get_object_or_404(EnhancementJob, pk=pk, user=request.user)
    if job.original:
        job.original.delete()
    if job.enhanced:
        job.enhanced.delete()
    job.delete()
    return JsonResponse({"success": True})

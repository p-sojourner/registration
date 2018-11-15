import requests
from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.template.response import TemplateResponse
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode

from app.utils import reverse
from applications import models as a_models
from user import forms, models, tokens
from user.forms import SetPasswordForm, PasswordResetForm
from user.models import User
from user.tokens import account_activation_token, password_reset_token


def login(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('root'))
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        form = forms.LoginForm(request.POST)
        next_ = request.GET.get('next', '/')
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = auth.authenticate(email=email, password=password)
            if user and user.is_active:
                auth.login(request, user)
                resp = HttpResponseRedirect(next_)
                c_domain = getattr(settings, 'LOGGED_IN_COOKIE_DOMAIN', getattr(settings, 'HACKATHON_DOMAIN', None))
                c_key = getattr(settings, 'LOGGED_IN_COOKIE_KEY', None)
                if c_domain and c_key:
                    try:
                        resp.set_cookie(c_key, 'biene', domain=c_domain, max_age=settings.SESSION_COOKIE_AGE)
                    except:
                        # We don't care if this is not set, we are being cool here!
                        pass
                return resp
            else:
                form.add_error(None, 'Wrong Username or Password. Please try again.')

    else:
        form = forms.LoginForm()

    return render(request, 'login.html', {'form': form})


def signup(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('root'))
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        form = forms.RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            name = form.cleaned_data['name']

            if models.User.objects.filter(email=email).first() is not None:
                messages.error(request, 'An account with this email already exists')
            else:
                user = models.User.objects.create_user(email=email, password=password, name=name)
                user = auth.authenticate(email=email, password=password)
                auth.login(request, user)
                return HttpResponseRedirect(reverse('root'))
    else:
        form = forms.RegisterForm()

    return render(request, 'signup.html', {'form': form})


def logout(request):
    auth.logout(request)
    messages.success(request, 'Successfully logged out!')
    resp = HttpResponseRedirect(reverse('account_login'))
    c_domain = getattr(settings, 'LOGGED_IN_COOKIE_DOMAIN', None) or getattr(settings, 'HACKATHON_DOMAIN', None)
    c_key = getattr(settings, 'LOGGED_IN_COOKIE_KEY', None)
    if c_domain and c_key:
        try:
            resp.delete_cookie(c_key, domain=c_domain)
        except:
            # We don't care if this is not deleted, we are being cool here!
            pass
    return resp


def activate(request, uid, token):
    try:
        uid = force_text(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=uid)
        if request.user.is_authenticated and request.user != user:
            messages.warning(request, "Trying to verify wrong user. Log out please!")
            return redirect('root')
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        messages.warning(request, "This user no longer exists. Please sign up again!")
        return redirect('root')

    if account_activation_token.check_token(user, token):
        messages.success(request, "Email verified!")

        user.email_verified = True
        user.save()
        auth.login(request, user)
    else:
        messages.error(request, "Email verification url has expired. Log in so we can send it again!")
    return redirect('root')


def password_reset(request):
    if request.method == "POST":
        form = PasswordResetForm(request.POST, )
        if form.is_valid():
            email = form.cleaned_data.get('email')
            user = User.objects.get(email=email)
            msg = tokens.generate_pw_reset_email(user, request)
            msg.send()
            return HttpResponseRedirect(reverse('password_reset_done'))
        else:
            return TemplateResponse(request, 'password_reset_form.html', {'form': form})
    else:
        form = PasswordResetForm()
    context = {
        'form': form,
    }

    return TemplateResponse(request, 'password_reset_form.html', context)


def password_reset_confirm(request, uid, token):
    """
    View that checks the hash in a password reset link and presents a
    form for entering a new password.
    """
    try:
        uid = force_text(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return TemplateResponse(request, 'password_reset_confirm.html', {'validlink': False})

    if password_reset_token.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(request.POST)
            if form.is_valid():
                form.save(user)
                return HttpResponseRedirect(reverse('password_reset_complete'))
        form = SetPasswordForm()
    else:
        return TemplateResponse(request, 'password_reset_confirm.html', {'validlink': False})

    return TemplateResponse(request, 'password_reset_confirm.html', {'validlink': True, 'form': form})


def password_reset_complete(request):
    return TemplateResponse(request, 'password_reset_complete.html', None)


def password_reset_done(request):
    return TemplateResponse(request, 'password_reset_done.html', None)


@login_required
def verify_email_required(request):
    if request.user.email_verified:
        messages.warning(request, "Your email has already been verified")
        return HttpResponseRedirect(reverse('root'))
    return TemplateResponse(request, 'verify_email_required.html', None)


@login_required
def send_email_verification(request):
    if request.user.email_verified:
        messages.warning(request, "Your email has already been verified")
        return HttpResponseRedirect(reverse('root'))
    msg = tokens.generate_verify_email(request.user)
    msg.send()
    messages.success(request, "Verification email successfully sent")
    return HttpResponseRedirect(reverse('root'))


def callback(request, provider=None):
    if not provider:
        return HttpResponseRedirect(reverse('root'))
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('root'))
    if request.method == 'POST':
        form = SetPasswordForm(request.POST)
        if not form.is_valid():
            return TemplateResponse(request, 'callback.html', {'form': form})
        password = form.cleaned_data['new_password1']

        # MLH provider logic
        if provider == 'mlh':
            conf = settings.OAUTH_PROVIDERS.get('mlh', {})

            # If logic not configured, exit
            if not conf or not conf.get('id', False):
                return HttpResponseRedirect(reverse('root'))

            # Get Auth code from GET request
            conf['code'] = request.GET.get('code', None)
            if not conf['code']:
                messages.error(request, 'Missing code, please start again!')
                return HttpResponseRedirect(reverse('root'))

            # Get Bearer token
            conf['redirect_url'] = reverse('callback', request=request, kwargs={'provider': provider})
            token_url = '{token_url}?client_id={id}&client_secret={secret}&code={code}&' \
                        'redirect_uri={redirect_url}&grant_type=authorization_code'.format(**conf).replace('\n', '')
            resp = requests.post(
                token_url
            )
            if resp.json().get('error', None):
                messages.error(request, 'Authentification failed, try again please!')
                return HttpResponseRedirect(reverse('root'))

            # Get user json
            conf['access_token'] = resp.json().get('access_token', None)
            mlhuser = requests.get('{user_url}?access_token={access_token}'.format(**conf)).json()
            if mlhuser.get('status', None).lower() != 'ok':
                messages.error(request, 'Authentification failed, try again please!')
                return HttpResponseRedirect(reverse('root'))

            # Create user
            email = mlhuser.get('data', {}).get('email', None)
            name = mlhuser.get('data', {}).get('first_name', '') + ' ' + mlhuser.get('data', {}).get('last_name', None)
            if models.User.objects.filter(email=email).first() is not None:
                messages.error(request, 'An account with this email already exists')
                return HttpResponseRedirect(reverse('root'))
            else:
                user = models.User.objects.create_user(email=email, password=password, name=name)

            # Auth user
            user = auth.authenticate(email=email, password=password)
            auth.login(request, user)

            # Save extra info
            draft = a_models.DraftApplication()
            draft.user = user
            mlhdiet = mlhuser.get('data', {}).get('dietary_restrictions', '')
            diet = mlhdiet if mlhdiet in dict(a_models.DIETS).keys() else 'Others'
            draft.save_dict({
                'degree': mlhuser.get('data', {}).get('major', ''),
                'university': mlhuser.get('data', {}).get('school', {}).get('name', ''),
                'phone_number': mlhuser.get('data', {}).get('phone_number', ''),
                'tshirt_size': mlhuser.get('data', {}).get('shirt_size', ''),
                'diet': mlhdiet,
                'other_diet': mlhdiet if diet == 'Others' else '',
            })
            draft.save()
            return HttpResponseRedirect(reverse('root'))
    else:
        c = {'form': SetPasswordForm()}
        if not request.GET.get('code', None):
            c['error'] = request.GET.get('error_description', 'Callback parameters missing.')
        return TemplateResponse(request, 'callback.html', c, status=200 if request.GET.get('code', None) else 400)

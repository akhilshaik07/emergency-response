"""Django settings for Emergency Response Platform project."""

import os
import sys
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name, default=False):
    """Read a boolean environment variable using explicit true/false values."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name, default):
    """Read a comma-separated environment variable into a trimmed list."""
    value = os.getenv(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(',') if item.strip()]


IS_TESTING = 'test' in sys.argv or _env_bool('DJANGO_TESTING')
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if IS_TESTING:
        SECRET_KEY = 'test-only-secret-key'
    else:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set outside tests.')

DEBUG = _env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', ['localhost', '127.0.0.1'])

# Application definition
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party packages
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    
    # Local apps
    'apps.accounts',
    'apps.societies',
    'apps.alerts',
]

# Custom User Model as required by mentor checklist
AUTH_USER_MODEL = 'accounts.Profile'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database configuration (PostgreSQL for development/production, in-memory SQLite for tests).
if IS_TESTING:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB', 'community_response_db'),
            'USER': os.getenv('POSTGRES_USER', 'erp_app_user'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
        }
    }


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# SimpleJWT Configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = _env_list(
    'CORS_ALLOWED_ORIGINS',
    ['http://localhost:3000'],
)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = _env_list(
    'CSRF_TRUSTED_ORIGINS',
    ['http://localhost:3000'],
)

# Opt into deployment-specific security headers without breaking local HTTP development.
SECURE_SSL_REDIRECT = _env_bool('DJANGO_SECURE_SSL_REDIRECT')
SESSION_COOKIE_SECURE = _env_bool('DJANGO_SESSION_COOKIE_SECURE')
CSRF_COOKIE_SECURE = _env_bool('DJANGO_CSRF_COOKIE_SECURE')

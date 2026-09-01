"""Profile (Custom User) model matching mentor assignment schema."""

from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager, Group


class ProfileManager(BaseUserManager):
    """Custom manager supporting email and mobile identifier lookup."""

    def create_user(self, email, mobile, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        if not mobile:
            raise ValueError('Mobile number is required')
        
        email = self.normalize_email(email)
        username = extra_fields.get('username') or email
        extra_fields.setdefault('username', username)
        
        user = self.model(email=email, mobile=mobile, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, mobile, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, mobile, password, **extra_fields)


class Profile(AbstractUser):
    """Profile model extending Django's auth user.

    Table name: profile
    Fields:
      - username, password (hashed), first_name, last_name, email, mobile,
        is_active, is_staff, is_superuser, date_joined, last_login
      - group_id (FK to auth_group)
      - gated_society_id (FK to gated_society)
      - emergency_contact1, emergency_contact2, emergency_contact3 (JSON: {"name": ..., "mobile": ..., "relationship": ...})
      - medical_condition (restricted visibility)
    """
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, db_index=True)
    mobile = models.CharField(max_length=15, unique=True, db_index=True)
    
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='group_id',
        related_name='profiles',
    )
    gated_society = models.ForeignKey(
        'societies.GatedSociety',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='gated_society_id',
        related_name='members',
    )
    
    # Emergency contacts (3 distinct JSON fields per mentor spec)
    emergency_contact1 = models.JSONField(default=dict, blank=True)
    emergency_contact2 = models.JSONField(default=dict, blank=True)
    emergency_contact3 = models.JSONField(default=dict, blank=True)
    
    # Medical condition data (visibility restricted)
    medical_condition = models.JSONField(null=True, blank=True, default=dict)

    objects = ProfileManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['mobile']

    class Meta:
        db_table = 'profile'
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.email} ({self.mobile})"

    @property
    def role_id(self):
        return self.group_id

    @property
    def role_name(self):
        return self.group.name if self.group else "No Role"

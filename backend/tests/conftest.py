import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.test_settings')

import pytest
from django.contrib.auth.models import User


@pytest.fixture
def test_user(db):
    user = User.objects.create_user(
        username='test_trader',
        email='test@dutchkem.com',
        password='testpass123'
    )
    return user

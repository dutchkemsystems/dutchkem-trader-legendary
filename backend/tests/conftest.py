import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['DATABASE_URL'] = 'sqlite:///test_db.sqlite3'

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

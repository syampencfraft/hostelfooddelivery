from django.test import TestCase, Client
from django.urls import reverse
from .models import CustomUser

class ResidentApprovalTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.warden = CustomUser.objects.create_user(
            username='warden1',
            password='password123',
            user_type='warden',
            is_approved=True
        )
        self.resident = CustomUser.objects.create_user(
            username='resident1',
            password='password123',
            user_type='resident',
            warden=self.warden,
            is_approved=False
        )

    def test_unapproved_resident_cannot_login(self):
        # Attempt to login
        response = self.client.post(reverse('login'), {
            'username': 'resident1',
            'password': 'password123'
        })
        
        # Check if login failed (remains on login page or shows error)
        # Based on views.py: return render(request, 'food_delivery/login.html')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your account is pending Warden approval.')
        
        # Verify user is not authenticated in the session
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_approved_resident_can_login(self):
        # Approve the resident
        self.resident.is_approved = True
        self.resident.save()
        
        # Attempt to login
        response = self.client.post(reverse('login'), {
            'username': 'resident1',
            'password': 'password123'
        })
        
        # Check if redirect to dashboard (indicates success)
        self.assertRedirects(response, reverse('dashboard'))
        
        # Verify user is authenticated
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_warden_approval_workflow(self):
        # Warden logins
        self.client.login(username='warden1', password='password123')
        
        # Warden manages users and approves resident1
        # Based on warden_manage_users view:
        # action = 'approve', user_id = ...
        response = self.client.post(reverse('warden_manage_users'), {
            'user_id': self.resident.id,
            'action': 'approve'
        })
        
        # Check if redirect back to manage users
        self.assertRedirects(response, reverse('warden_manage_users'))
        
        # Verify resident is now approved
        self.resident.refresh_from_db()
        self.assertTrue(self.resident.is_approved)

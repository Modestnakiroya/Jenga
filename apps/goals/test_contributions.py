from django.test import override_settings
from rest_framework.test import APITestCase
from apps.accounts.models import User
from apps.goals.models import Goal


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ContributionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("+256700555555", "Secure123!")
        self.goal = Goal.objects.create(user=self.user, name="Equipment", goal_type="business_growth", target_amount=100, current_saved_amount=20)
        self.url = f"/api/v1/goals/{self.goal.pk}/add-savings/"
        self.client.force_authenticate(self.user)

    def test_contributions_add_and_complete(self):
        response = self.client.post(self.url, {"amount":"30.50"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["current_saved_amount"], "50.50")
        response = self.client.post(self.url, {"amount":"50"}, format="json")
        self.assertEqual(response.data["current_saved_amount"], "100.50")
        self.assertEqual(response.data["status"], "completed")

    def test_invalid_amounts_and_other_users(self):
        for amount in ["0", "-1", "abc", "1.001", "9999999999.99"]:
            self.assertEqual(self.client.post(self.url, {"amount":amount}, format="json").status_code, 400)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_saved_amount, 20)
        other = User.objects.create_user("+256700666666", "Secure123!")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(self.url, {"amount":"5"}, format="json").status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url, {"amount":"5"}, format="json").status_code, 401)

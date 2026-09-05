from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.goals.models import Goal


class GoalAPITests(APITestCase):
    list_url = reverse("goal-list")

    def setUp(self):
        self.user_a = User.objects.create_user(
            phone_number="+256700555001",
            password="SecurePass123!",
            full_name="Goal Owner",
        )
        self.user_b = User.objects.create_user(
            phone_number="+256700555002",
            password="SecurePass123!",
            full_name="Other Owner",
        )

    def authenticate(self, user):
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": user.phone_number, "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def create_goal(self, **overrides):
        payload = {
            "name": "School fees",
            "goal_type": "personal",
            "target_amount": "500000.00",
            "current_saved_amount": "100000.00",
        }
        payload.update(overrides)
        return self.client.post(self.list_url, payload, format="json")

    def test_create_and_list_goals(self):
        self.authenticate(self.user_a)
        created = self.create_goal()
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["name"], "School fees")
        self.assertEqual(created.data["status"], "active")
        self.assertEqual(created.data["progress_percentage"], "20.00")

        listed = self.client.get(self.list_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["id"], created.data["id"])

    def test_retrieve_includes_progress_percentage(self):
        self.authenticate(self.user_a)
        created = self.create_goal(current_saved_amount="250000.00")
        detail = self.client.get(reverse("goal-detail", args=[created.data["id"]]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["progress_percentage"], "50.00")

    def test_progress_percentage_capped_at_100(self):
        self.authenticate(self.user_a)
        created = self.create_goal(
            target_amount="100000.00",
            current_saved_amount="150000.00",
        )
        self.assertEqual(created.data["progress_percentage"], "100.00")

        detail = self.client.get(reverse("goal-detail", args=[created.data["id"]]))
        self.assertEqual(detail.data["progress_percentage"], "100.00")
        self.assertGreater(Decimal(detail.data["current_saved_amount"]), Decimal(detail.data["target_amount"]))

    def test_patch_updates_and_adds_to_saved_amount(self):
        self.authenticate(self.user_a)
        created = self.create_goal(current_saved_amount="100000.00")
        url = reverse("goal-detail", args=[created.data["id"]])

        renamed = self.client.patch(url, {"name": "Emergency reserve"}, format="json")
        self.assertEqual(renamed.status_code, status.HTTP_200_OK)
        self.assertEqual(renamed.data["name"], "Emergency reserve")

        added = self.client.patch(url, {"amount_to_add": "25000.00"}, format="json")
        self.assertEqual(added.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(added.data["current_saved_amount"]), Decimal("125000.00"))
        self.assertEqual(added.data["progress_percentage"], "25.00")

    def test_delete_goal(self):
        self.authenticate(self.user_a)
        created = self.create_goal()
        url = reverse("goal-detail", args=[created.data["id"]])
        deleted = self.client.delete(url)
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Goal.objects.filter(id=created.data["id"]).exists())

    def test_ownership_isolation(self):
        self.authenticate(self.user_a)
        created = self.create_goal()
        goal_id = created.data["id"]
        url = reverse("goal-detail", args=[goal_id])

        self.authenticate(self.user_b)
        self.assertEqual(self.client.get(self.list_url).data, [])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(url, {"name": "stolen"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Goal.objects.filter(id=goal_id, user=self.user_a).exists())

    def test_invalid_amounts_rejected(self):
        self.authenticate(self.user_a)
        zero_target = self.create_goal(target_amount="0")
        negative_saved = self.create_goal(current_saved_amount="-10.00")
        self.assertEqual(zero_target.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_amount", zero_target.data)
        self.assertEqual(negative_saved.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("current_saved_amount", negative_saved.data)
        self.assertEqual(Goal.objects.count(), 0)

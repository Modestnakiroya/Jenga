from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.commitments.models import Commitment, CommitmentStatus
from apps.commitments.services import get_due_commitments
from apps.goals.models import Goal


class DueCommitmentsServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+256700666001",
            password="SecurePass123!",
            full_name="Saver",
        )
        self.other = User.objects.create_user(
            phone_number="+256700666002",
            password="SecurePass123!",
            full_name="Other",
        )
        self.today = timezone.localdate()

    def make_commitment(self, user=None, **overrides):
        payload = {
            "user": user or self.user,
            "target_amount": Decimal("10000.00"),
            "saved_amount": Decimal("0.00"),
            "period_start": self.today - timedelta(days=7),
            "period_end": self.today - timedelta(days=1),
            "status": CommitmentStatus.PENDING,
        }
        payload.update(overrides)
        return Commitment.objects.create(**payload)

    def test_due_commitments_are_pending_and_overdue(self):
        due = self.make_commitment()
        self.make_commitment(period_end=self.today)
        self.make_commitment(period_end=self.today + timedelta(days=2))
        self.make_commitment(status=CommitmentStatus.FULFILLED)
        self.make_commitment(status=CommitmentStatus.PARTIAL)
        self.make_commitment(user=self.other)

        results = list(get_due_commitments(self.user, reference_date=self.today))
        self.assertEqual(results, [due])

    def test_due_list_empty_when_nothing_overdue(self):
        self.make_commitment(period_end=self.today + timedelta(days=3))
        self.assertEqual(list(get_due_commitments(self.user, reference_date=self.today)), [])


class CommitmentAPITests(APITestCase):
    list_url = reverse("commitment-list")

    def setUp(self):
        self.user_a = User.objects.create_user(
            phone_number="+256700666003",
            password="SecurePass123!",
            full_name="Owner",
        )
        self.user_b = User.objects.create_user(
            phone_number="+256700666004",
            password="SecurePass123!",
            full_name="Stranger",
        )
        self.today = timezone.localdate()

    def authenticate(self, user):
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": user.phone_number, "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def payload(self, **overrides):
        data = {
            "target_amount": "10000.00",
            "period_start": (self.today - timedelta(days=7)).isoformat(),
            "period_end": (self.today - timedelta(days=1)).isoformat(),
        }
        data.update(overrides)
        return data

    def create_commitment(self, **overrides):
        return self.client.post(self.list_url, self.payload(**overrides), format="json")

    def test_create_list_retrieve_and_pending_filter(self):
        self.authenticate(self.user_a)
        created = self.create_commitment()
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["status"], CommitmentStatus.PENDING)
        self.assertEqual(Decimal(created.data["saved_amount"]), Decimal("0.00"))

        listed = self.client.get(self.list_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data), 1)

        pending = self.client.get(self.list_url, {"status": "pending"})
        self.assertEqual(len(pending.data), 1)

        detail = self.client.get(reverse("commitment-detail", args=[created.data["id"]]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["id"], created.data["id"])

    def test_confirm_sets_fulfilled_or_partial(self):
        self.authenticate(self.user_a)
        first = self.create_commitment()
        fulfilled = self.client.patch(
            reverse("commitment-confirm", args=[first.data["id"]]),
            {"saved_amount": "10000.00"},
            format="json",
        )
        self.assertEqual(fulfilled.status_code, status.HTTP_200_OK)
        self.assertEqual(fulfilled.data["status"], CommitmentStatus.FULFILLED)
        self.assertEqual(Decimal(fulfilled.data["saved_amount"]), Decimal("10000.00"))

        second = self.create_commitment(target_amount="20000.00")
        partial = self.client.patch(
            reverse("commitment-confirm", args=[second.data["id"]]),
            {"saved_amount": "5000.00"},
            format="json",
        )
        self.assertEqual(partial.status_code, status.HTTP_200_OK)
        self.assertEqual(partial.data["status"], CommitmentStatus.PARTIAL)
        self.assertEqual(Decimal(partial.data["saved_amount"]), Decimal("5000.00"))

        pending = self.client.get(self.list_url, {"status": "pending"})
        self.assertEqual(pending.data, [])

    def test_adjust_updates_target_and_resets_to_pending(self):
        self.authenticate(self.user_a)
        created = self.create_commitment()
        self.client.patch(
            reverse("commitment-confirm", args=[created.data["id"]]),
            {"saved_amount": "2000.00"},
            format="json",
        )
        adjusted = self.client.patch(
            reverse("commitment-adjust", args=[created.data["id"]]),
            {"reason": "Sales were slower this week", "new_target_amount": "6000.00"},
            format="json",
        )
        self.assertEqual(adjusted.status_code, status.HTTP_200_OK)
        self.assertEqual(adjusted.data["status"], CommitmentStatus.PENDING)
        self.assertEqual(Decimal(adjusted.data["target_amount"]), Decimal("6000.00"))
        self.assertEqual(adjusted.data["adjustment_reason"], "Sales were slower this week")

    def test_full_lifecycle_and_due_filter(self):
        self.authenticate(self.user_a)
        created = self.create_commitment()
        commitment_id = created.data["id"]
        due = get_due_commitments(self.user_a)
        self.assertEqual(due.count(), 1)
        self.assertEqual(due.get().id, commitment_id)

        self.client.patch(
            reverse("commitment-confirm", args=[commitment_id]),
            {"saved_amount": "4000.00"},
            format="json",
        )
        self.assertEqual(get_due_commitments(self.user_a).count(), 0)

        self.client.patch(
            reverse("commitment-adjust", args=[commitment_id]),
            {"reason": "Lower the target", "new_target_amount": "4000.00"},
            format="json",
        )
        self.assertEqual(get_due_commitments(self.user_a).count(), 1)

        done = self.client.patch(
            reverse("commitment-confirm", args=[commitment_id]),
            {"saved_amount": "4000.00"},
            format="json",
        )
        self.assertEqual(done.data["status"], CommitmentStatus.FULFILLED)
        self.assertEqual(get_due_commitments(self.user_a).count(), 0)

    def test_ownership_isolation(self):
        self.authenticate(self.user_a)
        created = self.create_commitment()
        commitment_id = created.data["id"]
        url = reverse("commitment-detail", args=[commitment_id])
        confirm_url = reverse("commitment-confirm", args=[commitment_id])
        adjust_url = reverse("commitment-adjust", args=[commitment_id])

        self.authenticate(self.user_b)
        self.assertEqual(self.client.get(self.list_url).data, [])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(confirm_url, {"saved_amount": "1.00"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(
                adjust_url,
                {"reason": "stolen", "new_target_amount": "1.00"},
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertTrue(Commitment.objects.filter(id=commitment_id, user=self.user_a).exists())

    def test_cannot_attach_another_users_goal(self):
        other_goal = Goal.objects.create(
            user=self.user_b,
            name="Other goal",
            goal_type="personal",
            target_amount=Decimal("50000.00"),
        )
        self.authenticate(self.user_a)
        response = self.create_commitment(goal=other_goal.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("goal", response.data)

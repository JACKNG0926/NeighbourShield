from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import (
    Area,
    BroadcastRecipient,
    Device,
    Incident,
    Property,
    SafetyPost,
    User,
)
from core.services import dispatch_emergency_broadcast


class EmergencyBroadcastServiceTests(APITestCase):
    def setUp(self):
        # Create areas
        self.area_a = Area.objects.create(
            name="Precinct Alpha",
            center_latitude=Decimal("3.123400"),
            center_longitude=Decimal("101.654300"),
            radius_m=500,
        )
        self.area_b = Area.objects.create(
            name="Precinct Beta",
            center_latitude=Decimal("3.134500"),
            center_longitude=Decimal("101.665400"),
            radius_m=600,
        )

        # Property in Area A
        self.property_a = Property.objects.create(
            area=self.area_a,
            unit_number="A-01-01",
            address_line="100 Alpha Road",
            postal_code="50000",
            property_type="house",
            latitude=Decimal("3.123450"),
            longitude=Decimal("101.654350"),
        )

        # Users
        self.admin = User.objects.create_superuser(
            username="admin_user",
            email="admin@example.com",
            password="AdminPassword123!",
            role="admin",
        )
        self.user_area_a = User.objects.create_user(
            username="resident_a",
            email="resident_a@example.com",
            password="TestPassword123!",
            role="resident",
            area=self.area_a,
            is_active=True,
        )
        self.user_property_a = User.objects.create_user(
            username="resident_prop_a",
            email="resident_prop_a@example.com",
            password="TestPassword123!",
            role="resident",
            residence=self.property_a,
            is_active=True,
        )
        self.user_area_b = User.objects.create_user(
            username="resident_b",
            email="resident_b@example.com",
            password="TestPassword123!",
            role="resident",
            area=self.area_b,
            is_active=True,
        )
        self.inactive_user_a = User.objects.create_user(
            username="inactive_a",
            email="inactive_a@example.com",
            password="TestPassword123!",
            role="resident",
            area=self.area_a,
            is_active=False,
        )

        # Active devices
        Device.objects.create(
            user=self.user_area_a,
            fcm_token="token_area_a_1",
            platform="android",
            is_active=True,
        )
        Device.objects.create(
            user=self.user_property_a,
            fcm_token="token_prop_a_1",
            platform="ios",
            is_active=True,
        )
        Device.objects.create(
            user=self.user_area_b,
            fcm_token="token_area_b_1",
            platform="android",
            is_active=True,
        )
        Device.objects.create(
            user=self.inactive_user_a,
            fcm_token="token_inactive_1",
            platform="android",
            is_active=True,
        )

    def test_dispatch_emergency_broadcast_affected_areas(self):
        """Verifies only active users in selected areas are targeted."""
        broadcast = SafetyPost.objects.create(
            author=self.admin,
            post_type="broadcast",
            category="flood",
            severity="critical",
            title="Flash Flood Evacuation Notice",
            description="Rising water in Precinct Alpha. Move vehicles to higher ground.",
            status="open",
        )
        broadcast.affected_areas.add(self.area_a)

        stats = dispatch_emergency_broadcast(broadcast)

        # Expect user_area_a and user_property_a (via residence in area_a) to be targeted
        self.assertEqual(stats["total_users"], 2)
        self.assertEqual(stats["tokens_count"], 2)
        self.assertEqual(stats["recipients_created"], 2)
        self.assertEqual(stats["payload"]["type"], "emergency_broadcast")
        self.assertEqual(stats["payload"]["severity"], "critical")
        self.assertEqual(stats["payload"]["broadcast_id"], str(broadcast.id))

        # Check BroadcastRecipient records in DB
        recipient_user_ids = list(
            BroadcastRecipient.objects.filter(post=broadcast).values_list("user_id", flat=True)
        )
        self.assertIn(self.user_area_a.id, recipient_user_ids)
        self.assertIn(self.user_property_a.id, recipient_user_ids)
        self.assertNotIn(self.user_area_b.id, recipient_user_ids)
        self.assertNotIn(self.inactive_user_a.id, recipient_user_ids)

    def test_dispatch_emergency_broadcast_township_wide(self):
        """Verifies all active users across the township are targeted when no areas selected."""
        broadcast = SafetyPost.objects.create(
            author=self.admin,
            post_type="broadcast",
            category="maintenance",
            severity="info",
            title="Township Power Maintenance",
            description="Scheduled power maintenance tonight.",
            status="open",
        )
        # No affected_areas attached -> Township-wide

        stats = dispatch_emergency_broadcast(broadcast)

        # All active users (admin, user_area_a, user_property_a, user_area_b) = 4
        self.assertEqual(stats["total_users"], 4)
        self.assertEqual(stats["tokens_count"], 3)  # user_a, prop_a, user_b have active devices
        self.assertEqual(stats["payload"]["severity"], "info")

        recipients_count = BroadcastRecipient.objects.filter(post=broadcast).count()
        self.assertEqual(recipients_count, 4)


class DeviceRegistrationAPITests(APITestCase):
    def setUp(self):
        self.resident = User.objects.create_user(
            username="device_tester",
            password="Password123!",
            role="resident",
            is_active=True,
        )
        self.client.force_authenticate(user=self.resident)

    def test_device_registration_idempotency(self):
        """Verifies re-registering an existing fcm_token updates the record without raising errors."""
        url = "/api/devices/"
        payload = {"fcm_token": "fcm_unique_token_999", "platform": "android"}

        # 1. Initial creation
        response1 = self.client.post(url, payload, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Device.objects.filter(fcm_token="fcm_unique_token_999").count(), 1)
        device = Device.objects.get(fcm_token="fcm_unique_token_999")
        self.assertEqual(device.platform, "android")
        self.assertEqual(device.user, self.resident)

        # 2. Re-registration with platform update
        payload_update = {"fcm_token": "fcm_unique_token_999", "platform": "ios"}
        response2 = self.client.post(url, payload_update, format="json")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(Device.objects.filter(fcm_token="fcm_unique_token_999").count(), 1)
        device.refresh_from_db()
        self.assertEqual(device.platform, "ios")

    def test_device_registration_missing_token(self):
        url = "/api/devices/"
        response = self.client.post(url, {"platform": "android"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SafetyPostAPITests(APITestCase):
    def setUp(self):
        self.resident = User.objects.create_user(
            username="hazard_poster",
            password="Password123!",
            role="resident",
            is_active=True,
        )
        self.client.force_authenticate(user=self.resident)

    def test_resident_can_create_hazard_safetypost(self):
        """Verifies non-admin residents can post hazard reports via JSON."""
        url = "/api/posts/"
        payload = {
            "post_type": "hazard",
            "category": "road",
            "title": "Broken pavement on block 3",
            "description": "Deep hole near parking bay 12",
            "latitude": "3.123456",
            "longitude": "101.654321",
            "severity": "warning",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Broken pavement on block 3")
        self.assertEqual(response.data["author"]["username"], "hazard_poster")

    def test_resident_cannot_create_announcement(self):
        """Verifies residents are barred from creating official announcements."""
        url = "/api/posts/"
        payload = {
            "post_type": "announcement",
            "category": "other",
            "title": "Unofficial Notice",
            "description": "Notice description",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_latest_broadcast_returns_active_broadcast(self):
        """Verifies GET /api/posts/latest_broadcast/ returns the latest active broadcast."""
        admin = User.objects.create_superuser(
            username="admin_broadcast",
            password="AdminPassword123!",
            email="admin@test.com"
        )
        broadcast = SafetyPost.objects.create(
            author=admin,
            post_type="broadcast",
            category="flood",
            severity="critical",
            title="CRITICAL FLOOD WARNING",
            description="Evacuate Sector 4 immediately",
            status="open",
        )

        url = "/api/posts/latest_broadcast/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["broadcast"])
        self.assertEqual(response.data["broadcast"]["id"], broadcast.id)
        self.assertEqual(response.data["broadcast"]["severity"], "critical")
        self.assertEqual(response.data["broadcast"]["title"], "CRITICAL FLOOD WARNING")

    def test_latest_broadcast_returns_null_when_none_open(self):
        """Verifies GET /api/posts/latest_broadcast/ returns null when no open broadcast exists."""
        url = "/api/posts/latest_broadcast/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["broadcast"])


class IncidentAPITests(APITestCase):
    def setUp(self):
        self.resident = User.objects.create_user(
            username="sos_user",
            password="Password123!",
            role="resident",
            is_active=True,
        )
        self.client.force_authenticate(user=self.resident)

    def test_sos_incident_creation_defaults(self):
        """Verifies quick SOS creates incident with coordinate-only payload."""
        url = "/api/incidents/"
        payload = {
            "latitude": "3.123456",
            "longitude": "101.654321",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["user"]["username"], "sos_user")

        incident = Incident.objects.get(id=response.data["id"])
        self.assertEqual(incident.message, "")
        self.assertEqual(incident.incident_type, "other")


class UserProfileAndRegistrationAPITests(APITestCase):
    def setUp(self):
        self.resident = User.objects.create_user(
            username="profile_user",
            password="Password123!",
            role="resident",
            unit_address="Unit B-05",
            is_active=True,
        )
        self.client.force_authenticate(user=self.resident)

    def test_volunteer_opt_in_update(self):
        """Verifies is_volunteer_opted_in can be toggled by resident via PATCH /api/me/."""
        url = "/api/me/"
        response = self.client.patch(url, {"is_volunteer_opted_in": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.resident.refresh_from_db()
        self.assertTrue(self.resident.is_volunteer_opted_in)

    def test_is_verified_volunteer_is_read_only(self):
        """Verifies is_verified_volunteer cannot be escalated by resident via PATCH /api/me/."""
        url = "/api/me/"
        response = self.client.patch(url, {"is_verified_volunteer": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.resident.refresh_from_db()
        self.assertFalse(self.resident.is_verified_volunteer)

    def test_registration_with_unit_address(self):
        """Verifies resident registration supports optional unit_address."""
        self.client.logout()
        url = "/api/auth/register/"
        payload = {
            "username": "new_resident_1",
            "password": "SecurePassword123!",
            "email": "new_res@example.com",
            "unit_address": "Block C-10-02",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["unit_address"], "Block C-10-02")


class SafetyReportsWebViewTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin_reporter",
            email="admin_rep@example.com",
            password="AdminPassword123!",
            role="admin",
        )
        self.resident = User.objects.create_user(
            username="resident_reporter",
            password="Password123!",
            role="resident",
            unit_address="A-01-01",
            is_active=True,
        )
        self.volunteer = User.objects.create_user(
            username="volunteer_reporter",
            password="Password123!",
            role="volunteer",
            is_verified_volunteer=True,
            is_volunteer_opted_in=True,
            unit_address="B-02-02",
            is_active=True,
        )

        self.hazard1 = SafetyPost.objects.create(
            author=self.resident,
            post_type="hazard",
            category="broken_light",
            severity="warning",
            title="Broken street lamp near Block A",
            description="The street light is completely dark at night.",
            latitude=Decimal("3.123456"),
            longitude=Decimal("101.654321"),
            status="open",
        )
        self.hazard2 = SafetyPost.objects.create(
            author=self.volunteer,
            post_type="hazard",
            category="road",
            severity="critical",
            title="Pothole on Main Boulevard",
            description="Large pothole damaging cars.",
            latitude=Decimal("3.123500"),
            longitude=Decimal("101.654400"),
            status="in_progress",
        )

    def test_unauthenticated_redirects_to_login(self):
        url = "/community/reports/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("/admin/login/", response.url)

    def test_admin_can_access_safety_reports_view(self):
        self.client.force_login(self.admin)
        url = "/community/reports/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, "core/safety_reports.html")
        self.assertIn("reports", response.context)
        self.assertEqual(response.context["stats"]["total"], 2)
        self.assertEqual(response.context["stats"]["open"], 1)
        self.assertEqual(response.context["stats"]["in_progress"], 1)

    def test_filter_by_status(self):
        self.client.force_login(self.admin)
        url = "/community/reports/?status=open"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reports = list(response.context["reports"])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].id, self.hazard1.id)

    def test_filter_by_role(self):
        self.client.force_login(self.admin)
        url = "/community/reports/?role=volunteer"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reports = list(response.context["reports"])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].id, self.hazard2.id)

    def test_admin_update_status_action(self):
        self.client.force_login(self.admin)
        url = "/community/reports/"
        payload = {
            "action": "update_status",
            "report_id": self.hazard1.id,
            "status": "resolved",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.hazard1.refresh_from_db()
        self.assertEqual(self.hazard1.status, "resolved")
        self.assertIsNotNone(self.hazard1.resolved_at)

    def test_admin_verify_action(self):
        self.client.force_login(self.admin)
        url = "/community/reports/"
        payload = {
            "action": "verify",
            "report_id": self.hazard1.id,
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.hazard1.refresh_from_db()
        self.assertTrue(self.hazard1.is_verified)
        self.assertEqual(self.hazard1.verified_by, self.admin)
        self.assertIsNotNone(self.hazard1.verified_at)

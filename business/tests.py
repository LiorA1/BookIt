from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Role

from .models import Business, Category

User = get_user_model()


class BusinessListApiTests(APITestCase):
    url = reverse("business-list")

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="S3cure-pass!", full_name="Yossi Cohen", role=Role.BusinessOwner
        )
        self.client.force_authenticate(self.owner)

    def create_businesses(self, count):
        Business.objects.bulk_create(
            Business(name=f"Business {i}", owner=self.owner, category=Category.Barbers) for i in range(count)
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def get_with_bearer(self, token):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return self.client.get(self.url)

    def test_valid_access_token_is_accepted(self):
        response = self.get_with_bearer(AccessToken.for_user(self.owner))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_malformed_token_returns_401(self):
        response = self.get_with_bearer("not-a-jwt")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_with_wrong_signature_returns_401(self):
        payload = dict(AccessToken.for_user(self.owner).payload)
        forged = TokenBackend("HS256", signing_key="a-different-signing-key-of-sufficient-length").encode(payload)

        response = self.get_with_bearer(forged)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token_returns_401(self):
        token = AccessToken.for_user(self.owner)
        token.set_exp(lifetime=-timedelta(seconds=1))

        response = self.get_with_bearer(token)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_paginated_envelope(self):
        business = Business.objects.create(name="Fade Masters", owner=self.owner, category=Category.Barbers)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 1)
        self.assertIsNone(response.data["next"])
        self.assertEqual(
            response.data["results"],
            [
                {
                    "id": business.id,
                    "name": "Fade Masters",
                    "category": "Barbers",
                    "owner": {"id": self.owner.id, "full_name": "Yossi Cohen"},
                }
            ],
        )

    def test_default_page_size(self):
        self.create_businesses(25)

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_second_page(self):
        self.create_businesses(25)

        response = self.client.get(self.url, {"page": 2})

        self.assertEqual(len(response.data["results"]), 5)
        self.assertEqual(response.data["results"][0]["name"], "Business 20")
        self.assertIsNone(response.data["next"])
        self.assertIsNotNone(response.data["previous"])

    def test_custom_page_size_is_capped(self):
        self.create_businesses(105)

        self.assertEqual(len(self.client.get(self.url, {"page_size": 5}).data["results"]), 5)
        self.assertEqual(len(self.client.get(self.url, {"page_size": 500}).data["results"]), 100)

    def test_out_of_range_page_returns_404(self):
        self.create_businesses(3)

        response = self.client.get(self.url, {"page": 99})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_category(self):
        Business.objects.create(name="Fade Masters", owner=self.owner, category=Category.Barbers)
        Business.objects.create(name="Math Pro", owner=self.owner, category=Category.Tutors)

        response = self.client.get(self.url, {"category": "Tutors"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([b["name"] for b in response.data["results"]], ["Math Pro"])

    def test_invalid_category_returns_400(self):
        response = self.client.get(self.url, {"category": "Plumbers"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_search_by_name_is_case_insensitive_substring(self):
        Business.objects.create(name="Fade Masters", owner=self.owner, category=Category.Barbers)
        Business.objects.create(name="Math Pro", owner=self.owner, category=Category.Tutors)

        response = self.client.get(self.url, {"search": "fade"})

        self.assertEqual([b["name"] for b in response.data["results"]], ["Fade Masters"])

    def test_filters_combine_and_paginate_over_filtered_set(self):
        self.create_businesses(25)
        Business.objects.bulk_create(
            Business(name=f"Tutor {i}", owner=self.owner, category=Category.Tutors) for i in range(3)
        )

        Business.objects.create(name="Tutor Barbershop", owner=self.owner, category=Category.Barbers)
        params = {"category": "Barbers", "search": "business", "page_size": 10}

        response = self.client.get(self.url, params)

        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIn("category=Barbers", response.data["next"])
        self.assertIn("search=business", response.data["next"])
        self.assertIn("page=2", response.data["next"])

        last_page = self.client.get(self.url, {**params, "page": 3})
        self.assertEqual(len(last_page.data["results"]), 5)
        self.assertIsNone(last_page.data["next"])

    def test_multi_word_search_requires_all_terms(self):
        Business.objects.create(name="Fade Masters Barbershop", owner=self.owner, category=Category.Barbers)
        Business.objects.create(name="Fade Studio", owner=self.owner, category=Category.Barbers)

        response = self.client.get(self.url, {"search": "masters fade"})

        self.assertEqual([b["name"] for b in response.data["results"]], ["Fade Masters Barbershop"])

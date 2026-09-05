from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.retirement.models import RetirementProfile
from apps.retirement.projection import PROJECTION_DISCLAIMER, calculate_retirement_projection
from apps.retirement.serializers import RetirementProfileSerializer, RetirementProjectionSerializer


class RetirementProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_object_or_404(RetirementProfile, user=request.user)
        return Response(RetirementProfileSerializer(profile).data)

    def post(self, request):
        existing = RetirementProfile.objects.filter(user=request.user).first()
        serializer = RetirementProfileSerializer(instance=existing, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        status_code = status.HTTP_200_OK if existing else status.HTTP_201_CREATED
        return Response(serializer.data, status=status_code)


class RetirementProjectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_object_or_404(RetirementProfile, user=request.user)
        projection = calculate_retirement_projection(profile)
        payload = {
            **projection,
            "disclaimer": PROJECTION_DISCLAIMER,
        }
        return Response(RetirementProjectionSerializer(payload).data)

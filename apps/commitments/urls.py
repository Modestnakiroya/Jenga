from rest_framework.routers import DefaultRouter

from apps.commitments.views import CommitmentViewSet

router = DefaultRouter()
router.register("commitments", CommitmentViewSet, basename="commitment")

urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from apps.goals.views import GoalViewSet

router = DefaultRouter()
router.register("goals", GoalViewSet, basename="goal")

urlpatterns = router.urls

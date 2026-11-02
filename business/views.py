from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView

from .models import Business
from .pagination import StandardPageNumberPagination
from .serializers import BusinessListQuerySerializer, BusinessResponseSerializer


class BusinessListView(ListAPIView):
    """GET /api/businesses - paginated list of businesses (?page=, ?page_size=, ?category=, ?search=)."""

    serializer_class = BusinessResponseSerializer
    pagination_class = StandardPageNumberPagination
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def get_queryset(self):
        query = BusinessListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)

        # A deterministic ordering keeps pages stable and avoids DRF's UnorderedObjectListWarning.
        queryset = Business.objects.select_related("owner").order_by("id")
        if "category" in query.validated_data:
            queryset = queryset.filter(category=query.validated_data["category"])
        return queryset

from rest_framework import serializers

from .models import Business, Category


class BusinessListQuerySerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.names, required=False)

    def validate_category(self, value):
        return Category[value]


class BusinessOwnerSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class BusinessResponseSerializer(serializers.ModelSerializer):
    owner = BusinessOwnerSerializer(read_only=True)
    category = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = ["id", "name", "category", "owner"]
        read_only_fields = fields

    def get_category(self, business):
        return Category(business.category).label

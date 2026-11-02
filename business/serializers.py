from django.utils import timezone
from rest_framework import serializers

from .models import Appointment, AppointmentStatus, Business, Category, Service


def public_name(member) -> str:
    """The API spelling of a choice: its member name in lowercase, used in query strings and responses alike."""
    return member.name.lower()


class EnumNameField(serializers.ChoiceField):
    """Query-string choice written as the lowercase member name; validation returns the enum member."""

    def __init__(self, enum, **kwargs):
        self.members = {public_name(member): member for member in enum}
        super().__init__(choices=list(self.members), **kwargs)

    def to_internal_value(self, data):
        return self.members[super().to_internal_value(data)]


class BusinessListQuerySerializer(serializers.Serializer):
    category = EnumNameField(Category, required=False)


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
        return public_name(Category(business.category))


class AwareDateTimeField(serializers.DateTimeField):
    """ISO 8601 datetime that must carry a UTC offset, so the instant is never guessed."""

    default_error_messages = {
        "naive": "A timezone offset is required, for example 2026-11-10T10:00:00Z or 2026-11-10T12:00:00+02:00.",
    }

    def enforce_timezone(self, value):
        if timezone.is_naive(value):
            self.fail("naive")
        return super().enforce_timezone(value)


class AppointmentCreateRequestSerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.select_related("business"),
        error_messages={
            "does_not_exist": "Service not found.",
            "incorrect_type": "Service must be an integer id.",
        },
    )
    start_time = AwareDateTimeField()


class AppointmentListQuerySerializer(serializers.Serializer):
    """Query parameters ?from=, ?to=, ?status=; validated_data uses AppointmentService.list_for_user's names.

    `start_time` and `end_time` are the inclusive lower and upper bounds of the appointments' start_time
    (?from= and ?to=); `end_time` does not filter on Appointment.end_time.
    """

    start_time = AwareDateTimeField(required=False, source="start_time")
    end_time = AwareDateTimeField(required=False, source="end_time")
    statuses = serializers.ListField(
        child=EnumNameField(AppointmentStatus),
        required=False,
        allow_empty=False,
        source="statuses",
    )

    def get_fields(self):
        fields = super().get_fields()
        # Expose the public query names; "from" is a Python keyword, so it cannot be a declared attribute.
        # Each field keeps its explicit source, so validated_data keys stay start_time/end_time/statuses.
        return {
            "from": fields["start_time"],
            "to": fields["end_time"],
            "status": fields["statuses"],
        }

    def validate_status(self, value):
        return sorted(set(value))

    def validate(self, attrs):
        start_time, end_time = attrs.get("start_time"), attrs.get("end_time")
        if start_time is not None and end_time is not None and start_time > end_time:
            raise serializers.ValidationError({"to": "Must not be earlier than from."})
        return attrs


class AppointmentServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "duration_minutes", "price"]
        read_only_fields = fields


class AppointmentBusinessSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = ["id", "name", "category"]
        read_only_fields = fields

    def get_category(self, business):
        return public_name(Category(business.category))


class AppointmentClientSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class AppointmentResponseSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    service = AppointmentServiceSerializer(read_only=True)
    business = AppointmentBusinessSerializer(source="service.business", read_only=True)
    client = AppointmentClientSerializer(read_only=True)

    class Meta:
        model = Appointment
        fields = ["id", "status", "start_time", "end_time", "service", "business", "client"]
        read_only_fields = fields

    def get_status(self, appointment):
        return public_name(AppointmentStatus(appointment.status))

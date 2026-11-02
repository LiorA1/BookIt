from django.contrib.postgres.fields import BigIntegerRangeField, DateTimeRangeField
from django.db.models import Func


class TsTzRange(Func):
    """tstzrange(lower, upper, bounds): the time span an appointment occupies."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class BigIntPointRange(Func):
    """int8range(key, key, '[]'): a one-point range, so `&&` between two of them means `key = key`.

    This lets an exclusion constraint compare a key for equality alongside another range without
    installing the btree_gist extension.
    """

    function = "INT8RANGE"
    output_field = BigIntegerRangeField()

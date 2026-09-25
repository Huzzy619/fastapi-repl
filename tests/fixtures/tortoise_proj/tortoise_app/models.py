from tortoise import fields
from tortoise.models import Model


class TimestampMixin(Model):
    created = fields.DatetimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Tournament(TimestampMixin):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=100)


class Event(TimestampMixin):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=100)
    tournament = fields.ForeignKeyField("models.Tournament", related_name="events")

from typing import Any
from tortoise.models import Model
from tortoise import fields


class ActionLog(Model):
    id = fields.IntField(primary_key=True, unique=True)
    related_to_user = fields.IntField()  # users discord id
    related_to_game = fields.TextField()

    action_occurred_at = fields.DatetimeField(auto_now=True)  # defaulted to now
    minutes_added = fields.IntField()

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return (
            f"Logged Action "
            f"[ "
            f"User: {self.related_to_user}; Occurred At: {self.action_occurred_at}; Added: {self.minutes_added}m.; "
            f"Game: {self.related_to_game}."
            f" ]"
            )

    @classmethod
    async def create_action_log(cls, game_name: str, user_id: int, minutes: int):
        await cls.create(related_to_game=game_name, related_to_user=user_id, minutes_added=minutes)

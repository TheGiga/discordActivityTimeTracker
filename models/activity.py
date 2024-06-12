import datetime
from typing import Any, Type

import discord
from tortoise.models import Model
from tortoise import fields

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import ActivityData


class GameData(Model):
    name = fields.TextField(pk=True)
    overall_time = fields.IntField(default=0)

    users = fields.JSONField(default={})

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"GameData(\"{self.name}\", Hours: {self.overall_time / 60})"

    @classmethod
    async def store_activity_data(cls, user: discord.Member, activity_data: 'ActivityData'):
        game_name = activity_data.name
        timedelta = datetime.datetime.utcnow() - activity_data.start

        if timedelta.seconds < 1:
            return

        print(f"Storing {game_name} from {user.name}")

        record, _ = await cls.get_or_create(name=game_name)

        record.overall_time += round(timedelta.seconds / 60)

        all_users_data: dict = record.users.copy()
        if not all_users_data.get(user.id):
            all_users_data[user.id] = round(timedelta.seconds / 60)
        else:
            current_time = all_users_data[user.id]
            all_users_data[user.id] = current_time + round(timedelta / 60)

        record.users = all_users_data

        await record.save()

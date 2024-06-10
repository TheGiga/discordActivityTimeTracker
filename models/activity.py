import datetime
from typing import Any

import discord
from tortoise.models import Model
from tortoise import fields


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
    async def store_activity_data(cls, user: discord.Member, activity_data: tuple[str, datetime.datetime]):
        game_name = activity_data[0]
        timedelta = activity_data[1]
        if game_name == "Spotify":
            return

        print("Storing ", game_name)

        elapsed_time = datetime.datetime.utcnow() - timedelta
        record, _ = await cls.get_or_create(name=game_name)

        record.overall_time += round(elapsed_time.seconds / 60)
        if not record.users.get(user.id):
            record.users[user.id] = 0

        record.users[user.id] += round(elapsed_time.seconds / 60)

        await record.save()

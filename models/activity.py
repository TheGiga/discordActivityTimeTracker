import datetime
import discord
from tortoise.models import Model
from tortoise import fields
from typing import Any

from .action_log import ActionLog

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

        if timedelta.seconds < 60:
            return

        minutes = round(timedelta.seconds / 60)

        print(
            f"{datetime.datetime.utcnow().strftime('%a %H:%M:%S')} | "
            f"Storing {game_name} from {user.name} with {timedelta.seconds / 3600:.2f} hrs."
        )

        record, _ = await cls.get_or_create(name=game_name)

        record.overall_time += minutes

        all_users_data: dict = record.users.copy()
        if not all_users_data.get(str(user.id)):
            all_users_data[str(user.id)] = minutes
        else:
            current_time = all_users_data[str(user.id)]
            all_users_data[str(user.id)] = current_time + minutes

        record.users = all_users_data
        await ActionLog.create_action_log(game_name, user.id, minutes)

        await record.save()

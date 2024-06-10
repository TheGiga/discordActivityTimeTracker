import datetime
import os
import asyncio
import random

import discord
from dotenv import load_dotenv
from tortoise import connections
from discord.ext.tasks import loop

import config
from models import GameData

load_dotenv()

# Any project imports should be used after the load of .env
from database import db_init


async def game_search(ctx: discord.AutocompleteContext):  # AutoComplete for /emojis search, for better UX.
    return [discord.OptionChoice(x.name) for x in await GameData.all() if ctx.value in x.name]


intents = discord.Intents.all()
bot = discord.Bot(intents=intents)

tracking_list = {}


@loop(minutes=10)
async def channel_name_loop():
    await bot.wait_until_ready()

    guild = bot.get_guild(config.GUILD_ID)
    channel = guild.get_channel(config.CHANNEL_ID)

    game_data = await GameData.get_or_none(name=config.GAME_TO_TRACK_IN_CHANNEL_NAME)

    if not game_data:
        return

    await channel.edit(name=f'casino game hours: {game_data.overall_time / 60:.2f}')


@bot.slash_command(name="playtime")
async def playtime_command(
        ctx: discord.ApplicationContext,
        game: discord.Option(description='Game to check playtime leaderboard in', autocomplete=game_search)
):
    await ctx.defer()

    game_data = await GameData.get_or_none(name=game)

    sorted_leaderboard = {k: v for k, v in sorted(game_data.users.items(), key=lambda item: item[1])}

    leaderboard = ""
    for i, x in enumerate(sorted_leaderboard, start=1):
        leaderboard += f"{i}. <@{x}> - {sorted_leaderboard[x] / 60:.2f} hrs\n"

        if i > 10:
            break

    embed = discord.Embed(color=discord.Color.embed_background(), title=game_data.name)
    embed.description = (
        ("**{0}**\n{1}".format(
            "Playtime leaderboard" if game_data.name != "Genshin Impact" else "Wall of shame",
            leaderboard
        ))  # ignore
    )

    embed.set_footer(text=f"Total playtime: {game_data.overall_time / 60:.2f} hours")

    await ctx.respond(embed=embed)


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    if (not before.activity and not after.activity) or before.bot:
        return

    elif not before.activity and after.activity:
        if after.activity.name == "Spotify": return
        tracking_list[after.id] = (after.activity.name, datetime.datetime.utcnow())

    elif before.activity and not after.activity:
        if before.activity.name == "Spotify": return
        try:
            await GameData.store_activity_data(after, tracking_list[after.id])
            tracking_list.pop(after.id)
        except KeyError:
            pass

    elif before.activity.name != after.activity.name:
        if before.activity.name != "Spotify":
            try:
                await GameData.store_activity_data(after, tracking_list[after.id])
            except KeyError:
                pass

        if after.activity.name != "Spotify":
            tracking_list[after.id] = (after.activity.name, datetime.datetime.utcnow())
            return


async def main():
    await db_init()
    await bot.start(os.getenv("TOKEN"))


if __name__ == "__main__":

    event_loop = asyncio.get_event_loop_policy().get_event_loop()

    if config.ENABLE_CHANNEL_NAME_LOOP:
        channel_name_loop.start()

    try:
        event_loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("🛑 Shutting Down")
        event_loop.run_until_complete(bot.close())
        event_loop.run_until_complete(connections.close_all(discard=True))
        event_loop.stop()

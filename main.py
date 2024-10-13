import datetime
import os
import asyncio

import aiohttp
import discord
from discord import ActivityType
from dotenv import load_dotenv
from tortoise import connections
from discord.ext.tasks import loop
from discord.ext.commands import has_permissions, bot_has_permissions

load_dotenv()

# Any project imports should be used after the load of .env

import config
from models import GameData
from database import db_init


async def game_search(ctx: discord.AutocompleteContext):  # AutoComplete for /emojis search, for better UX.
    return [discord.OptionChoice(x.name) for x in await GameData.all() if ctx.value.lower() in x.name.lower()]


intents = discord.Intents.all()
bot = discord.Bot(intents=intents)

emoji_group = bot.create_group(name='emoji')

tracking_list: {int: list['ActivityData']} = {}


class ActivityData:
    def __init__(self, activity: discord.Activity):
        self.name = activity.name
        self.start = datetime.datetime.utcnow()

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"ActivityData({self.name=}, {self.start=})"


def activity_eligibility_check(activity) -> bool:
    if activity.name in config.BANNED_ACTIVITY_NAMES:
        #print(f'activity.name in banned names, {activity.name=}')
        return False

    if hasattr(activity, "type"):
        if activity.type not in [ActivityType.streaming, ActivityType.playing]:
            #print(f'{activity.type=} not playing')
            return False

    return True


def remove_activity_list_duplicates(activities: tuple) -> list[discord.Activity]:
    names: list[str] = []
    to_return: list[discord.Activity] = []

    for act in activities:
        if act.name not in names:
            to_return.append(act)
            names.append(act.name)

    return to_return


def strip_ineligible_activities(activities: tuple) -> list[discord.Activity]:
    to_return: list[discord.Activity] = []
    activities = remove_activity_list_duplicates(activities)

    for activity in activities:
        if not activity_eligibility_check(activity):
            continue

        to_return.append(activity)

    return to_return


def translate_activity_names_list_to_activity_list(name_list: list[str], activities: list):
    to_return = []

    for name in name_list:
        for act in activities:
            if name == act.name:
                to_return.append(act)

    #print(f"translated\n{name_list}\nto\n{to_return}")
    return to_return


def compare_activity_lists_by_names(x, y) -> (bool, set, set):
    """
    Returns:

    - 1: True, if lists are identical by activity names;
    - 2: set of activity names that are in 1st set, but not 2nd;
    - 3: same as 2, but reverse
    :param x:
    :param y:
    :return: bool, set, set
    """

    x = set([act.name for act in x])
    y = set([act.name for act in y])

    if len(x.symmetric_difference(y)) < 1:
        #print("no difference:", x.symmetric_difference(y))
        return True, set(), set()

    return False, x.difference(y), y.difference(x)


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    #print("Presence Update, current tracking list: ", tracking_list)

    #print(after.activities)

    if (not before.activity and not after.activity) or before.bot:
        return

    elif not before.activity and after.activity:
        eligible_activities = strip_ineligible_activities(after.activities)

        if eligible_activities:
            tracking_list[after.id] = [ActivityData(x) for x in eligible_activities]
            #print(1, tracking_list)

    elif before.activity and not after.activity:
        stored_user_data = tracking_list.get(after.id)

        if not stored_user_data:
            return

        tracking_list.pop(after.id)

        for tracked_activity in stored_user_data:
            #print(2, tracked_activity)
            await GameData.store_activity_data(after, tracked_activity)

    elif before.activity and after.activity:
        before_eligible_activities = strip_ineligible_activities(before.activities)
        after_eligible_activities = strip_ineligible_activities(after.activities)

        if len(before_eligible_activities) + len(after_eligible_activities) < 1:
            return

        are_same, to_remove, to_add = \
            compare_activity_lists_by_names(before_eligible_activities, after_eligible_activities)

        if are_same:
            return

        stored_user_data: list = tracking_list.get(after.id)

        #print(f'{to_remove=}, {to_add=}')

        if not stored_user_data:
            if to_add:
                stored_user_data = [
                    ActivityData(x) for x in translate_activity_names_list_to_activity_list(
                        to_add, after_eligible_activities
                    )
                ]
        else:
            for value in stored_user_data:
                if value.name in to_remove:
                    stored_user_data.remove(value)
                    await GameData.store_activity_data(after, value)

            if to_add:
                stored_user_data.extend(
                    [
                        ActivityData(x) for x in
                        translate_activity_names_list_to_activity_list(to_add, after_eligible_activities)
                        if x.name not in [y.name for y in stored_user_data]
                    ]
                )

        tracking_list[after.id] = stored_user_data

        #print(f'user data after removal and addition: ', stored_user_data)


@loop(minutes=10)
async def channel_name_loop():
    await bot.wait_until_ready()

    guild = bot.get_guild(config.GUILD_ID)
    channel = guild.get_channel(config.CHANNEL_ID)

    game_data = await GameData.get_or_none(name=config.GAME_TO_TRACK_IN_CHANNEL_NAME)

    if not game_data:
        return

    await channel.edit(name=f'casino game hours: {game_data.overall_time / 60:.2f}')


async def send_error_response(ctx, error, custom_message: str = None):
    try:
        await ctx.respond(content=error if not custom_message else custom_message)
    except discord.NotFound:
        await ctx.send(content=error if not custom_message else custom_message)
    except discord.HTTPException:
        pass


@bot.event
async def on_command_error(ctx: discord.ApplicationContext, error):
    if isinstance(error, discord.ext.commands.MissingPermissions):
        return await send_error_response(
            ctx, error, f"Bot lacks permissions: `{error.missing_permissions}`"
        )

    await send_error_response(ctx, error)


@bot.slash_command(name='move_all')
async def move_all_command(
        ctx: discord.ApplicationContext,
        secondary_channel: discord.VoiceChannel,
        primary_channel: discord.Option(discord.VoiceChannel, required=False) = None
):
    await ctx.defer(ephemeral=True)

    if not primary_channel:
        if getattr(ctx.user, "voice", None):
            primary_channel = ctx.user.voice.channel
        else:
            return await ctx.respond("You have to be in voice channel or specify the `primary_channel` attribute.")

    if len(primary_channel.members) < 1:
        return await ctx.respond(f":x: There is no one in {primary_channel.mention}.")

    for member in primary_channel.members:
        try:
            await member.move_to(secondary_channel)
        except discord.HTTPException:
            continue

    await ctx.send_followup("✅ Done!")


@bot.slash_command(name='wake_up')
@has_permissions(move_members=True)
async def fast_move_command(
        ctx: discord.ApplicationContext,
        user: discord.Member,
        secondary_channel: discord.VoiceChannel,
        primary_channel: discord.Option(
            discord.VoiceChannel, description="will use voice channel the user or command user is in, if available",
            required=False
        ) = None,
        number_of_moves: discord.Option(int, required=False, min_value=1, max_value=10) = 5
):
    await ctx.defer(ephemeral=True)

    if not user.voice.channel:
        return await ctx.respond("User not in voice channel, unlucko.", ephemeral=True)

    if not primary_channel:
        primary_channel = user.voice.channel

    await ctx.respond(
        f"� Working on it... Moving {user.mention} {number_of_moves} times from and to {primary_channel.mention}",
        ephemeral=True
    )

    try:
        for i in range(number_of_moves):
            await user.move_to(secondary_channel)
            await asyncio.sleep(config.SLEEP_DURATION_BETWEEN_MOVES)

            await user.move_to(primary_channel)
            await asyncio.sleep(config.SLEEP_DURATION_BETWEEN_MOVES)

    except discord.HTTPException as e:
        print(f"/{ctx.command.qualified_name} | {e}")
        pass

    await ctx.send_followup("✅ Done!")


@emoji_group.command(name='add_from_url')
@has_permissions(manage_emojis=True)
@bot_has_permissions(manage_emojis=True)
async def emoji_add_from_url_command(
        ctx: discord.ApplicationContext,
        name: discord.Option(str, description='name'),
        url: discord.Option(str, description="url (webp, png, jpg...)")
):
    await ctx.defer()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                response_bytes = await r.content.read()
    except aiohttp.InvalidURL:
        return await ctx.respond(f"Invalid URL! `{url}`")

    try:
        created_emoji = await ctx.guild.create_custom_emoji(name=name, image=response_bytes)
    except (discord.HTTPException, discord.InvalidArgument) as e:
        return await ctx.respond(f"Failed, `{e}`")

    await ctx.respond(f"Successfully created emoji {created_emoji}")


@bot.slash_command(name="playtime")
async def playtime_command(
        ctx: discord.ApplicationContext,
        game: discord.Option(description='Game to check playtime leaderboard in', autocomplete=game_search),
        user: discord.Option(discord.Member, required=False) = None
):
    await ctx.defer()

    game_data = await GameData.get_or_none(name=game)

    if not game_data:
        await ctx.respond(f"Activity `{game}` has no available records.")
        return

    if user:
        playtime = game_data.users.get(str(user.id))

        if not playtime:
            content = f"**{user.display_name}** has no playtime in `{game_data.name}`"
        else:
            content = f"**{user.display_name}** has **{playtime / 60:.2f} hrs** on record in `{game_data.name}`"

        await ctx.respond(content)
        return

    leaders = {k: v for k, v in sorted(game_data.users.items(), key=lambda item: item[1], reverse=True)}

    if not leaders:
        await ctx.respond(f"There is no recorded user playtime in `{game_data.name}`")
        return

    embed = discord.Embed(
        title=f"{game_data.name}" if game_data.name != "Genshin Impact" else "Wall of Shame (GI)",
        color=discord.Color.embed_background()
    )

    description = ""

    for pos, leader in enumerate(leaders, start=1):
        description += f'{pos}. <@{leader}> - {leaders[leader] / 60:.2f} hrs.\n'

        if pos > 10:
            break

    embed.description = description
    embed.set_footer(text=f"Overall playtime: {game_data.overall_time / 60:.2f} hrs")

    await ctx.respond(embed=embed)


async def main():
    await db_init()
    await bot.start(os.getenv("TOKEN"))


if __name__ == "__main__":

    event_loop = asyncio.get_event_loop_policy().get_event_loop()

    if config.ENABLE_CHANNEL_NAME_LOOP and os.getenv("INDEV") != 1:
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
